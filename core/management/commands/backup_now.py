from django.core.management.base import BaseCommand, CommandError

from core.backups import backup_once, configured
from organization.models import BackupRun


class Command(BaseCommand):
    help = "Back up the database and media files now."

    def handle(self, *args, **options):
        if not configured():
            raise CommandError(
                "Backups aren't configured: set RESTIC_REPOSITORY and RESTIC_PASSWORD."
            )
        record = backup_once(BackupRun.Kind.MANUAL, echo=self.stdout.write)
        if not record.ok:
            raise CommandError(f"Backup failed at {record.step}: {record.message}")
