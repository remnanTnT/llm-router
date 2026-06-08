#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VERBOSE_REQUEST_LOG="${LLM_ROUTER_VERBOSE_REQUEST_LOG:-0}"
while (($# > 0)); do
  case "$1" in
    --verbose)
      VERBOSE_REQUEST_LOG=1
      ;;
    -h|--help)
      echo "Usage: $0 [--verbose]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--verbose]" >&2
      exit 2
      ;;
  esac
  shift
done

export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5431}"
export LLM_ROUTER_CONFIG="${LLM_ROUTER_CONFIG:-$(pwd)/config.yaml}"
export LLM_ROUTER_VERBOSE_REQUEST_LOG="${VERBOSE_REQUEST_LOG}"
export HTTP_PORT="${HTTP_PORT:-8001}"
export VIP_PORT="${VIP_PORT:-8008}"
export REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
export REDIS_PORT="${REDIS_PORT:-6379}"
export REDIS_DB="${REDIS_DB:-0}"

source ./scripts/local_redis.sh
ensure_local_redis prod

exec gunicorn router_project.wsgi:application \
  --bind "0.0.0.0:${HTTP_PORT}" \
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
