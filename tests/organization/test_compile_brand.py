import json
import os
import sys

import pytest
from django.core.management import CommandError, call_command

SASS_STUB = """#!{python}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
source, out = Path(args[-2]), Path(args[-1])
with open(os.environ["SASS_LOG"], "w") as log:
    json.dump({{"args": args, "brand": (source.parent / "_brand.scss").read_text()}}, log)
if os.environ.get("SASS_FAIL"):
    print("Error: undefined variable", file=sys.stderr)
    sys.exit(65)
out.write_text("compiled")
"""


@pytest.fixture
def sass(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "sass"
    stub.write_text(SASS_STUB.format(python=sys.executable))
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("SASS_LOG", str(tmp_path / "sass.json"))
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.scss").write_text('@import "brand";')
    (source / "_brand.scss").write_text("// stock")
    out = tmp_path / "dist" / "main.css"
    out.parent.mkdir()
    out.write_text("stock css")
    return {"log": tmp_path / "sass.json", "source": source, "out": out, "root": tmp_path}


def compile_brand(sass, brand):
    call_command(
        "compile_brand",
        brand=str(brand),
        source=str(sass["source"]),
        load_path="/opt/node_modules",
        out=str(sass["out"]),
    )


def test_without_brand_file_keeps_css(sass):
    compile_brand(sass, sass["root"] / "missing.scss")
    assert sass["out"].read_text() == "stock css"
    assert not sass["log"].exists()


def test_without_brand_file_restores_stock_css(sass):
    # setup containers are reused, so CSS compiled on an earlier run must not linger.
    stock = sass["root"] / "stock.css"
    stock.write_text("stock css")
    sass["out"].write_text("old branded css")
    call_command(
        "compile_brand",
        brand=str(sass["root"] / "missing.scss"),
        stock=str(stock),
        out=str(sass["out"]),
    )
    assert sass["out"].read_text() == "stock css"


def test_with_brand_file(sass):
    brand = sass["root"] / "_brand.scss"
    brand.write_text("$primary: #0a58ca;")
    compile_brand(sass, brand)
    assert sass["out"].read_text() == "compiled"
    call = json.loads(sass["log"].read_text())
    assert call["brand"] == "$primary: #0a58ca;"
    assert "--load-path=/opt/node_modules" in call["args"]
    assert "--style=compressed" in call["args"]
    assert (sass["source"] / "_brand.scss").read_text() == "// stock"  # source untouched


def test_compile_error(sass, monkeypatch):
    brand = sass["root"] / "_brand.scss"
    brand.write_text("$primary: $nope;")
    monkeypatch.setenv("SASS_FAIL", "1")
    with pytest.raises(CommandError, match="undefined variable"):
        compile_brand(sass, brand)
    assert sass["out"].read_text() == "stock css"
