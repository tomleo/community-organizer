import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

BASE_DIR = Path(settings.BASE_DIR)


class Command(BaseCommand):
    help = "Rebuild main.css with a site's _brand.scss (run by the setup service at startup)."

    def add_arguments(self, parser):
        parser.add_argument("--brand", default="/app/brand/_brand.scss")
        parser.add_argument("--source", default=str(BASE_DIR / "frontend" / "src"))
        parser.add_argument("--load-path", default=str(BASE_DIR / "frontend" / "node_modules"))
        parser.add_argument("--out", default=str(BASE_DIR / "static" / "dist" / "main.css"))
        # A copy of the stock CSS: setup containers are reused, so start from it every time.
        parser.add_argument("--stock", default=str(BASE_DIR / "frontend" / "stock" / "main.css"))

    def handle(self, *args, brand, source, load_path, out, stock, **options):
        brand = Path(brand)
        if not brand.is_file():
            if Path(stock).is_file():
                shutil.copyfile(stock, out)
            self.stdout.write("No brand/_brand.scss; using the stock colors.")
            return
        with tempfile.TemporaryDirectory() as tmp:
            sources = Path(tmp) / "src"
            shutil.copytree(source, sources)
            shutil.copyfile(brand, sources / "_brand.scss")
            compiled = Path(tmp) / "main.css"
            result = subprocess.run(
                [
                    "sass",
                    "--no-source-map",
                    "--style=compressed",
                    f"--load-path={load_path}",
                    "--quiet-deps",
                    "--silence-deprecation=import",
                    str(sources / "main.scss"),
                    str(compiled),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise CommandError(f"Couldn't compile {brand}:\n{result.stderr.strip()}")
            shutil.copyfile(compiled, out)
        self.stdout.write(f"Compiled {out} with {brand}.")
