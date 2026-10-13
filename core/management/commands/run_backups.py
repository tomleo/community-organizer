from django.core.management.base import BaseCommand

from core.backups import run_forever


class Command(BaseCommand):
    help = "Run forever, backing up nightly at BACKUP_TIME (the backup service)."

    def handle(self, *args, **options):
        self.stdout.write("Backup service started.")
        run_forever()
