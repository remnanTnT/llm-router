import os
import sys

from django.core.wsgi import get_wsgi_application
from django.db import connection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "router_project.settings")

application = get_wsgi_application()

try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
except Exception as exc:
    print(f"Database connection failed during startup: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
