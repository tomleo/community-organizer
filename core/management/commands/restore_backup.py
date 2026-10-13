from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.backups import BackupError, configured, describe_snapshot, restore, site_is_up


class Command(BaseCommand):
    help = "Replace the database and media files with a backup snapshot."

    def add_arguments(self, parser):
        parser.add_argument("snapshot", nargs="?", default="latest")
        parser.add_argument(
            "--yes-i-am-sure",
            metavar="DOMAIN",
            help="Confirm without a prompt by giving the site's domain.",
        )

    def handle(self, *args, snapshot, yes_i_am_sure=None, **options):
        if not configured():
            raise CommandError(
                "Backups aren't configured: set RESTIC_REPOSITORY and RESTIC_PASSWORD."
            )
        if site_is_up():
            raise CommandError(
                "The site is still running. Stop it first: docker compose stop web worker beat"
            )
        domain = urlsplit(settings.SITE_URL).hostname
        try:
            found = describe_snapshot(snapshot)
            self.stdout.write(f"Snapshot {found['id']} from {found['time']}.")
            answer = yes_i_am_sure or input(
                f"This replaces ALL data on {domain} with this snapshot. Type {domain} to confirm: "
            )
            if answer.strip() != domain:
                raise CommandError("The domain didn't match; nothing was changed.")
            restore(found["id"], echo=self.stdout.write)
        except BackupError as exc:
            raise CommandError(f"Restore failed: {exc}") from exc
        self.stdout.write("Restored. Start the site again with: docker compose up -d")
