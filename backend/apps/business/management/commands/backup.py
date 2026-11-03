from django.core.management.base import BaseCommand, CommandError

from apps.business.backups import BackupError, create_backup


class Command(BaseCommand):
    help = "Back up the database and product images, then delete backups beyond --keep."

    def add_arguments(self, parser):
        parser.add_argument("--label", default="manual", help="Added to the folder name, e.g. daily.")
        parser.add_argument("--keep", type=int, default=None, help="How many backups to keep (default BACKUP_KEEP).")

    def handle(self, *args, **options):
        try:
            path = create_backup(label=options["label"], keep=options["keep"])
        except BackupError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"Backup written to {path}"))
