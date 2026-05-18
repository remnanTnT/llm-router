from __future__ import annotations

import os
from pathlib import Path

from router.config import APP_CONFIG, BASE_DIR

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "llm-router-dev-secret-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]
ROOT_URLCONF = "router_project.urls"
WSGI_APPLICATION = "router_project.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "Asia/Shanghai"
DATA_UPLOAD_MAX_MEMORY_SIZE = int(APP_CONFIG["server"].get("data_upload_max_memory_size_mb", 50)) * 1024 * 1024

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "router",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "router.middleware.ClientDisconnectMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOW_METHODS = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": APP_CONFIG["database"].get("name"),
        "USER": APP_CONFIG["database"].get("user"),
        "PASSWORD": APP_CONFIG["database"].get("password"),
        "HOST": APP_CONFIG["database"].get("host"),
        "PORT": APP_CONFIG["database"].get("port"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"sslmode": APP_CONFIG["database"].get("sslmode", "disable")},
        "TIME_ZONE": TIME_ZONE,
    }
}

if os.environ.get("USE_SQLITE_FOR_TESTS") == "1":
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(Path(BASE_DIR) / "test.sqlite3"),
        "TIME_ZONE": TIME_ZONE,
    }

STATIC_URL = "static/"
