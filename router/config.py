from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG: dict[str, Any] = {
    "proxy_url": "http://localhost:8051",
    "log_path": "./logs/requests",
    "server": {"data_upload_max_memory_size_mb": 50},
    "proxy": {
        "default_max_tokens": 8528,
        "unknown_model_max_tokens": 20480,
        "stream_connect_timeout_seconds": 30,
        "stream_read_timeout_seconds": 900,
        "stream_total_timeout_seconds": 900,
        "normal_connect_timeout_seconds": 5,
        "normal_read_timeout_seconds": 900,
        "client_disconnect_check_interval_seconds": 0.5,
        "stale_processing_minutes": 20,
        "opencode_400_delay_seconds": 180,
    },
    "load_balancer": {
        "enabled": True,
        "max_attempts_per_request": 3,
        "retry_status_codes": [502, 503, 504],
        "mark_unhealthy_status_codes": [502, 503, 504],
        "health_check_timeout_seconds": 2,
        "chooser_class": "router.services.server_chooser.LeastConnectionServerChooser",
    },
    "opencode": {
        "enabled": True,
        "block_max_version": "1.2.26",
        "delay_400_max_version": "1.2.27",
    },
    "admission": {"allow_when_user_info_missing": True},
    "cmdb": {"enabled": False, "dummy": True, "refresh_interval_between_ips_seconds": 1},
    "database": {
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "postgres",
        "name": "postgres",
        "sslmode": "disable",
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict[str, Any]:
    config_path = Path(os.environ.get("LLM_ROUTER_CONFIG", BASE_DIR / "config.yaml"))
    data: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    config = _deep_merge(DEFAULT_CONFIG, data)

    database = config.setdefault("database", {})
    for env_key, config_key in {
        "DB_HOST": "host",
        "DB_PORT": "port",
        "DB_USER": "user",
        "DB_PASSWORD": "password",
        "DB_NAME": "name",
        "DB_SSLMODE": "sslmode",
    }.items():
        if env_key in os.environ:
            database[config_key] = os.environ[env_key]
    if "PROXY_URL" in os.environ:
        config["proxy_url"] = os.environ["PROXY_URL"]
    return config


APP_CONFIG = load_config()
