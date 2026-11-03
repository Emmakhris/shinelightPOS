from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import Product


class Command(BaseCommand):
    help = "Load sample products, tables and a customer (only into an empty catalog)."

    def handle(self, *args, **options):
        if Product.objects.exists():
            raise CommandError("The catalog already has products; demo data was not loaded.")
        from apps.business.demo import load_demo_data

        load_demo_data()
        self.stdout.write(self.style.SUCCESS("Demo data loaded."))
