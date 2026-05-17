import os

os.environ.setdefault("USE_SQLITE_FOR_TESTS", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "router_project.settings")

import django
import pytest
from django.db import connection


django.setup()

from router.models import Model, RequestRecord, Whitelist


@pytest.fixture(scope="session", autouse=True)
def api_test_tables():
    existing_tables = connection.introspection.table_names()
    with connection.schema_editor() as schema_editor:
        for model in (Model, RequestRecord, Whitelist):
            if model._meta.db_table not in existing_tables:
                schema_editor.create_model(model)
    yield


@pytest.fixture(autouse=True)
def clean_api_tables(api_test_tables):
    RequestRecord.objects.all().delete()
    Whitelist.objects.all().delete()
    Model.objects.all().delete()
