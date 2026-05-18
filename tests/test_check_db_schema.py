import pytest
from django.apps import apps
from django.core.management import call_command
from django.db import connection


@pytest.fixture(scope="module", autouse=True)
def all_router_tables():
    models = list(apps.get_app_config("router").get_models())
    existing_tables = connection.introspection.table_names()
    with connection.schema_editor() as schema_editor:
        for model in models:
            if model._meta.db_table not in existing_tables:
                schema_editor.create_model(model)
    yield


@pytest.fixture(autouse=True)
def remove_metrics_port():
    drop_metrics_port()
    yield
    drop_metrics_port()


def drop_metrics_port():
    if has_column("servers", "metrics_port"):
        with connection.schema_editor() as schema_editor:
            schema_editor.execute('ALTER TABLE "servers" DROP COLUMN "metrics_port";')


def add_metrics_port():
    with connection.cursor() as cursor:
        cursor.execute('ALTER TABLE "servers" ADD COLUMN "metrics_port" INTEGER;')


def has_column(table, column):
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return column in {item.name for item in description}


def test_check_db_schema_succeeds_when_schema_matches(capsys):
    call_command("check_db_schema")

    output = capsys.readouterr()
    assert "Database schema matches Django model definitions" in output.out


def test_user_visit_counts_is_not_required(capsys):
    assert "user_visit_counts" not in connection.introspection.table_names()

    call_command("check_db_schema")

    output = capsys.readouterr()
    assert "Database schema matches Django model definitions" in output.out


def test_check_db_schema_reports_extra_column(capsys):
    add_metrics_port()

    with pytest.raises(SystemExit):
        call_command("check_db_schema")

    output = capsys.readouterr()
    assert "Extra columns in servers: metrics_port" in output.err
    assert has_column("servers", "metrics_port")


def test_check_db_schema_dry_run_does_not_drop_extra_column(capsys):
    add_metrics_port()

    with pytest.raises(SystemExit):
        call_command("check_db_schema", "--fix", "--dry-run")

    output = capsys.readouterr()
    assert "Extra columns in servers: metrics_port" in output.err
    assert 'ALTER TABLE "servers" DROP COLUMN "metrics_port";' in output.out
    assert has_column("servers", "metrics_port")


def test_check_db_schema_fix_drops_extra_column(capsys):
    add_metrics_port()

    call_command("check_db_schema", "--fix")

    output = capsys.readouterr()
    assert "Extra columns in servers: metrics_port" in output.err
    assert 'ALTER TABLE "servers" DROP COLUMN "metrics_port";' in output.out
    assert not has_column("servers", "metrics_port")
