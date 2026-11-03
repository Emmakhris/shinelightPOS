from django.core.management.base import BaseCommand, CommandError

from apps.business.backups import BackupError, list_backups, restore_backup


class Command(BaseCommand):
    help = "Replace the current data with a backup. Stop the POS server first."

    def add_arguments(self, parser):
        parser.add_argument("name", nargs="?", help="Backup folder name. Leave out to list backups.")
        parser.add_argument("--yes", action="store_true", help="Confirm you want to replace the current data.")

    def handle(self, *args, **options):
        if not options["name"]:
            for b in list_backups():
                self.stdout.write(f"{b['name']}  sales={b.get('sales')}  last={b.get('last_invoice')}")
            return
        if not options["yes"]:
            raise CommandError("This replaces all current data. Add --yes to confirm.")
        try:
            safety = restore_backup(options["name"])
        except BackupError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            f"Restored {options['name']}. The data from before the restore is saved in {safety.name}."
        ))
