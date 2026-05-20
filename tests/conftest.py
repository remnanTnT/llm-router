import os

os.environ.setdefault("USE_SQLITE_FOR_TESTS", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "router_project.settings")

import django
import pytest
from django.db import connection


django.setup()

from router.models import Model, RequestRecord, Server, Whitelist


@pytest.fixture(scope="session", autouse=True)
def api_test_tables():
    existing_tables = connection.introspection.table_names()
    with connection.schema_editor() as schema_editor:
        for model in (Model, RequestRecord, Server, Whitelist):
            if model._meta.db_table not in existing_tables:
                schema_editor.create_model(model)
        if RequestRecord._meta.db_table in connection.introspection.table_names() and not has_column("requests", "last_match"):
            schema_editor.add_field(RequestRecord, RequestRecord._meta.get_field("last_match"))
        # Circuit breaker columns
        for col in ("circuit_state", "consecutive_failures", "last_state_change_at", "cooldown_seconds"):
            if Server._meta.db_table in connection.introspection.table_names() and not has_column("servers", col):
                schema_editor.add_field(Server, Server._meta.get_field(col))
    yield


def has_column(table, column):
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return column in {item.name for item in description}


@pytest.fixture(autouse=True)
def clean_api_tables(api_test_tables):
    RequestRecord.objects.all().delete()
    Server.objects.all().delete()
    Whitelist.objects.all().delete()
    Model.objects.all().delete()
