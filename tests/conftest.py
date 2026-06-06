import os

os.environ.setdefault("USE_SQLITE_FOR_TESTS", "1")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "router_project.settings")

import django
import pytest
from django.db import connection


django.setup()

from router.models import IP, Model, RequestRecord, Server, Whitelist, ServerOperation, MrLiveReview, CodehubReview


@pytest.fixture(scope="session", autouse=True)
def api_test_tables():
    existing_tables = connection.introspection.table_names()
    with connection.schema_editor() as schema_editor:
        for model in (IP, Model, RequestRecord, Server, Whitelist, ServerOperation, MrLiveReview, CodehubReview):
            if model._meta.db_table not in existing_tables:
                schema_editor.create_model(model)
        if IP._meta.db_table in connection.introspection.table_names() and not has_column("ips", "vip"):
            schema_editor.add_field(IP, IP._meta.get_field("vip"))
        if RequestRecord._meta.db_table in connection.introspection.table_names() and not has_column("requests", "last_match"):
            schema_editor.add_field(RequestRecord, RequestRecord._meta.get_field("last_match"))
        if RequestRecord._meta.db_table in connection.introspection.table_names() and not has_column("requests", "final_prefix_cache"):
            schema_editor.add_field(RequestRecord, RequestRecord._meta.get_field("final_prefix_cache"))
        # Circuit breaker columns
        for col in ("circuit_state", "consecutive_failures", "last_state_change_at", "cooldown_seconds", "workload"):
            if Server._meta.db_table in connection.introspection.table_names() and not has_column("servers", col):
                schema_editor.add_field(Server, Server._meta.get_field(col))
        # VIP columns
        for col in ("vip", "vip_cooldown"):
            if Server._meta.db_table in connection.introspection.table_names() and not has_column("servers", col):
                schema_editor.add_field(Server, Server._meta.get_field(col))
        if Model._meta.db_table in connection.introspection.table_names() and not has_column("models", "vip"):
            schema_editor.add_field(Model, Model._meta.get_field("vip"))
        if Model._meta.db_table in connection.introspection.table_names() and not has_column("models", "deprecation"):
            schema_editor.add_field(Model, Model._meta.get_field("deprecation"))
        # New router fields
        if Model._meta.db_table in connection.introspection.table_names() and not has_column("models", "is_routing_model"):
            schema_editor.add_field(Model, Model._meta.get_field("is_routing_model"))
        if Model._meta.db_table in connection.introspection.table_names() and not has_column("models", "max_context_window"):
            schema_editor.add_field(Model, Model._meta.get_field("max_context_window"))
        if RequestRecord._meta.db_table in connection.introspection.table_names() and not has_column("requests", "router_result"):
            schema_editor.add_field(RequestRecord, RequestRecord._meta.get_field("router_result"))
        if RequestRecord._meta.db_table in connection.introspection.table_names() and not has_column("requests", "estimate_tokens"):
            schema_editor.add_field(RequestRecord, RequestRecord._meta.get_field("estimate_tokens"))
        if Server._meta.db_table in connection.introspection.table_names() and not has_column("servers", "context_window"):
            schema_editor.add_field(Server, Server._meta.get_field("context_window"))
    yield


def has_column(table, column):
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return column in {item.name for item in description}


@pytest.fixture(autouse=True)
def clean_api_tables(api_test_tables):
    RequestRecord.objects.all().delete()
    IP.objects.all().delete()
    Server.objects.all().delete()
    Whitelist.objects.all().delete()
    Model.objects.all().delete()
    ServerOperation.objects.all().delete()
    MrLiveReview.objects.all().delete()
    CodehubReview.objects.all().delete()
