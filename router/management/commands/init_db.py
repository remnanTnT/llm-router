from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Validate database connectivity and required existing tables."

    def handle(self, *args, **options):
        required = {"ips", "departments", "user_ips", "user_visit_counts", "models", "requests", "whitelist", "servers"}
        with connection.cursor() as cursor:
            existing = set(connection.introspection.table_names(cursor))
        missing = sorted(required - existing)
        if missing:
            self.stderr.write(f"Missing tables: {', '.join(missing)}")
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Database schema is available"))
