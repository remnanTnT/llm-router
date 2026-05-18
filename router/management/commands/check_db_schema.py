from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Check required table columns against Django model definitions."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="Drop extra columns and column defaults that are not defined by the models.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        models = list(apps.get_app_config("router").get_models())
        fix = options.get("fix")
        dry_run = options.get("dry_run")

        drift = self._inspect_schema(models)
        self._write_drift(drift)

        if fix:
            for table, columns in drift["extra_columns"].items():
                for column in columns:
                    sql = self._drop_column_sql(table, column)
                    self.stdout.write(sql)
                    if not dry_run:
                        with connection.schema_editor() as schema_editor:
                            schema_editor.execute(sql)

            for table, columns in drift["extra_defaults"].items():
                for column in columns:
                    sql = self._drop_default_sql(table, column)
                    self.stdout.write(sql)
                    if not dry_run:
                        with connection.schema_editor() as schema_editor:
                            schema_editor.execute(sql)

            if not dry_run:
                drift = self._inspect_schema(models)
                self._write_drift(drift)

        if any(drift.values()):
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("Database schema matches Django model definitions"))

    def _inspect_schema(self, models):
        drift = {"missing_tables": [], "missing_columns": {}, "extra_columns": {}, "extra_defaults": {}}
        expected_tables = {model._meta.db_table: model for model in models}

        with connection.cursor() as cursor:
            existing_tables = set(connection.introspection.table_names(cursor))
            for table, model in expected_tables.items():
                if table not in existing_tables:
                    drift["missing_tables"].append(table)
                    continue

                expected_columns = self._expected_columns(model)
                description = connection.introspection.get_table_description(cursor, table)
                actual_columns = {column.name for column in description}
                missing_columns = sorted(expected_columns - actual_columns)
                extra_columns = sorted(actual_columns - expected_columns)

                if missing_columns:
                    drift["missing_columns"][table] = missing_columns
                if extra_columns:
                    drift["extra_columns"][table] = extra_columns

                extra_defaults = self._extra_defaults(cursor, table, model, actual_columns)
                if extra_defaults:
                    drift["extra_defaults"][table] = extra_defaults

        drift["missing_tables"].sort()
        return drift

    def _expected_columns(self, model):
        return {field.column for field in model._meta.local_concrete_fields}

    def _extra_defaults(self, cursor, table, model, actual_columns):
        if connection.vendor != "postgresql":
            return []

        fields_without_defaults = [
            field.column
            for field in model._meta.local_concrete_fields
            if field.column in actual_columns and not field.primary_key and field.default is field.NOT_PROVIDED
        ]
        if not fields_without_defaults:
            return []

        placeholders = ", ".join(["%s"] * len(fields_without_defaults))
        cursor.execute(
            f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name IN ({placeholders})
              AND column_default IS NOT NULL
            """,
            [table, *fields_without_defaults],
        )
        return sorted(row[0] for row in cursor.fetchall())

    def _drop_column_sql(self, table, column):
        quote_name = connection.ops.quote_name
        return f"ALTER TABLE {quote_name(table)} DROP COLUMN {quote_name(column)};"

    def _drop_default_sql(self, table, column):
        quote_name = connection.ops.quote_name
        return f"ALTER TABLE {quote_name(table)} ALTER COLUMN {quote_name(column)} DROP DEFAULT;"

    def _write_drift(self, drift):
        if drift["missing_tables"]:
            self.stderr.write("Missing tables: " + ", ".join(drift["missing_tables"]))

        for table, columns in drift["missing_columns"].items():
            self.stderr.write(f"Missing columns in {table}: {', '.join(columns)}")

        for table, columns in drift["extra_columns"].items():
            self.stderr.write(f"Extra columns in {table}: {', '.join(columns)}")

        for table, columns in drift["extra_defaults"].items():
            self.stderr.write(f"Extra defaults in {table}: {', '.join(columns)}")
