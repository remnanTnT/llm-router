#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5431}"
export LLM_ROUTER_CONFIG="${LLM_ROUTER_CONFIG:-$(pwd)/config.yaml}"
export VIP_PORT="${VIP_PORT:-8008}"

exec gunicorn router_project.wsgi:application \
  --bind 0.0.0.0:8001 \
  --bind "0.0.0.0:${VIP_PORT}" \
  --workers "${GUNICORN_WORKERS:-8}" \
  --threads "${GUNICORN_THREADS:-64}" \
  --worker-class gthread \
  --timeout "${GUNICORN_TIMEOUT:-960}" \
  --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-1200}" \
  --max-requests "${GUNICORN_MAX_REQUESTS:-1000}" \
  --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-200}" \
  --access-logfile - \
  --error-logfile -
