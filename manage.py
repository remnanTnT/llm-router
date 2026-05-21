#!/usr/bin/env python
import os
import sys


DB_PORTS = {"prod": "5431", "test": "5432"}
HELP_TOKENS = {"help", "--help", "-h"}


def configure_database_environment():
    if len(sys.argv) <= 1 or sys.argv[1] in HELP_TOKENS:
        return

    if sys.argv[1] not in DB_PORTS:
        sys.stderr.write(
            f"manage.py requires '{ '|'.join(DB_PORTS) }' as the first argument "
            f"(got {sys.argv[1]!r}).\n"
            f"Example: python manage.py test migrate\n"
        )
        sys.exit(2)

    env_name = sys.argv.pop(1)
    os.environ["LLM_ROUTER_ENV"] = env_name
    os.environ.setdefault("DB_PORT", DB_PORTS[env_name])


if __name__ == "__main__":
    configure_database_environment()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "router_project.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
