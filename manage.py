#!/usr/bin/env python
import os
import sys


DB_PORTS = {"prod": "5431", "test": "5432"}


def configure_database_environment():
    env_name = None
    if len(sys.argv) > 1 and sys.argv[1] in DB_PORTS:
        env_name = sys.argv.pop(1)
    else:
        env_name = os.environ.get("LLM_ROUTER_ENV")

    if env_name in DB_PORTS:
        os.environ["LLM_ROUTER_ENV"] = env_name
        os.environ.setdefault("DB_PORT", DB_PORTS[env_name])


if __name__ == "__main__":
    configure_database_environment()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "router_project.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
