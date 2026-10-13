from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from organization.contrast import contrast_ratio, css_colors

AA, AAA = 4.5, 7.0


class Command(BaseCommand):
    help = "Check the brand colors in the built CSS against WCAG contrast on white."

    def add_arguments(self, parser):
        parser.add_argument(
            "--css", default=str(Path(settings.BASE_DIR) / "static" / "dist" / "main.css")
        )

    def handle(self, *args, css, **options):
        path = Path(css)
        if not path.is_file():
            raise CommandError(f"{path} not found. Build the frontend first.")
        try:
            colors = css_colors(path.read_text())
        except ValueError as exc:
            raise CommandError(f"{path}: {exc}") from None
        failing = []
        for name, color in colors.items():
            ratio = contrast_ratio(color)
            aa = "pass" if ratio >= AA else "fail"
            aaa = "pass" if ratio >= AAA else "fail"
            self.stdout.write(f"{name} {color} on white: {ratio:.2f}:1 — AA: {aa}, AAA: {aaa}")
            if ratio < AA:
                failing.append(name)
        if failing:
            raise CommandError(f"Below WCAG AA (4.5:1): {', '.join(failing)}")
