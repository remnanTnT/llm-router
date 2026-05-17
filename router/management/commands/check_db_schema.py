from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Check that required existing tables are present. Does not alter schema."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="Accepted for compatibility; no schema changes are made.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        required = ["ips", "departments", "user_ips", "user_visit_counts", "models", "requests", "whitelist"]
        with connection.cursor() as cursor:
            existing = set(connection.introspection.table_names(cursor))
        missing = [name for name in required if name not in existing]
        if missing:
            self.stderr.write("Missing tables: " + ", ".join(missing))
            raise SystemExit(1)
        if options.get("fix"):
            self.stdout.write("--fix requested, but schema changes are disabled for this project")
        self.stdout.write(self.style.SUCCESS("Required tables are present"))
