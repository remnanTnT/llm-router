#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export LLM_ROUTER_CONFIG="${LLM_ROUTER_CONFIG:-$(pwd)/config.yaml}"
export VIP_PORT="${VIP_PORT:-9001}"

exec gunicorn router_project.wsgi:application \
  --bind 0.0.0.0:9000 \
  --bind "0.0.0.0:${VIP_PORT}" \
  --workers "${GUNICORN_WORKERS:-1}" \
  --threads "${GUNICORN_THREADS:-8}" \
  --worker-class gthread \
  --timeout "${GUNICORN_TIMEOUT:-960}" \
  --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-1200}" \
  --access-logfile - \
  --error-logfile -
