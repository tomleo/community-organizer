from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.template.loader import render_to_string

from core.env import template_dirs
from organization.contrast import contrast_ratio, css_colors


def test_template_dirs():
    base = Path("/app/templates")
    assert template_dirs("", base) == [base]
    assert template_dirs("/srv/custom", base) == [Path("/srv/custom"), base]


@pytest.mark.django_db
def test_custom_templates_override_pages_and_emails(settings, tmp_path, client):
    (tmp_path / "emails" / "reminder").mkdir(parents=True)
    (tmp_path / "home.html").write_text("CUSTOM HOME")
    (tmp_path / "emails" / "reminder" / "subject.txt").write_text("Custom reminder subject")
    templates = [dict(settings.TEMPLATES[0])]
    templates[0]["DIRS"] = template_dirs(str(tmp_path), settings.TEMPLATES[0]["DIRS"][-1])
    settings.TEMPLATES = templates

    assert client.get("/").content.decode() == "CUSTOM HOME"
    assert render_to_string("emails/reminder/subject.txt", {}) == "Custom reminder subject"


def test_contrast_ratio():
    assert round(contrast_ratio("#000000"), 1) == 21.0
    assert round(contrast_ratio("#ffffff"), 1) == 1.0
    assert round(contrast_ratio("#0d6efd"), 2) == 4.50
    assert round(contrast_ratio("#fff"), 1) == 1.0  # short hex


def test_css_colors():
    css = (
        ":root{--bs-primary:#0b5ed7;--bs-link-color:#0a58ca}"
        "[data-bs-theme=dark]{--bs-link-color:#6ea8fe}"
    )
    assert css_colors(css) == {"primary": "#0b5ed7", "link": "#0a58ca"}


def test_command_passes_and_fails(tmp_path, capsys):
    good = tmp_path / "good.css"
    good.write_text(":root{--bs-primary:#0a58ca;--bs-link-color:#0a58ca}")
    call_command("check_brand_contrast", css=str(good))
    out = capsys.readouterr().out
    assert "AA: pass" in out and "AAA: fail" in out

    bad = tmp_path / "bad.css"
    bad.write_text(":root{--bs-primary:#ffc107;--bs-link-color:#0a58ca}")
    with pytest.raises(CommandError, match="primary"):
        call_command("check_brand_contrast", css=str(bad))


def test_command_missing_file(tmp_path):
    with pytest.raises(CommandError, match="Build the frontend"):
        call_command("check_brand_contrast", css=str(tmp_path / "missing.css"))


def test_css_colors_named_and_alpha():
    # The minifier writes colors as names when shorter (e.g. #800000 -> maroon).
    assert css_colors(":root{--bs-primary:maroon;--bs-link-color:#0a58caff}") == {
        "primary": "#800000",
        "link": "#0a58ca",
    }


@pytest.mark.parametrize(
    "css",
    [
        ":root{--bs-primary:#0a58ca;--bs-link-color:rebeccapurple}",  # unknown name
        ":root{--bs-primary:#0a58ca}",  # link color missing
    ],
)
def test_command_rejects_unreadable_colors(tmp_path, css):
    path = tmp_path / "main.css"
    path.write_text(css)
    with pytest.raises(CommandError):
        call_command("check_brand_contrast", css=str(path))
