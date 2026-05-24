#!/usr/bin/env bash

redis_cli_ping() {
  local host="$1"
  local port="$2"
  local db="$3"
  local password="${4:-}"
  local response

  if ! command -v redis-cli >/dev/null 2>&1; then
    return 2
  fi

  if [[ -n "$password" ]]; then
    response="$(REDISCLI_AUTH="$password" redis-cli -h "$host" -p "$port" -n "$db" ping 2>/dev/null || true)"
  else
    response="$(redis-cli -h "$host" -p "$port" -n "$db" ping 2>/dev/null || true)"
  fi

  [[ "$response" == "PONG" ]]
}

ensure_local_redis() {
  local instance_name="${1:?missing Redis instance name}"
  local host="${REDIS_HOST:-127.0.0.1}"
  local port="${REDIS_PORT:-6379}"
  local db="${REDIS_DB:-0}"
  local password="${REDIS_PASSWORD:-}"
  local have_redis_cli=0

  if command -v redis-cli >/dev/null 2>&1; then
    have_redis_cli=1
  fi

  case "$host" in
    localhost|127.0.0.1|::1)
      ;;
    *)
      echo "Using external Redis at ${host}:${port}; local Redis startup skipped." >&2
      return 0
      ;;
  esac

  if [[ "$have_redis_cli" == "1" ]] && redis_cli_ping "$host" "$port" "$db" "$password"; then
    echo "Redis is already running at ${host}:${port}." >&2
    return 0
  fi

  if ! command -v redis-server >/dev/null 2>&1; then
    echo "redis-server is required to start local Redis for ${instance_name}." >&2
    echo "Install Redis or set REDIS_HOST/REDIS_PORT to an existing Redis service." >&2
    exit 1
  fi

  local runtime_dir="${REDIS_RUNTIME_DIR:-$(pwd)/.runtime/redis-${instance_name}}"
  local pid_file="${REDIS_PID_FILE:-${runtime_dir}/redis.pid}"
  local log_file="${REDIS_LOG_FILE:-${runtime_dir}/redis.log}"
  local db_file="${REDIS_DB_FILE:-dump.rdb}"

  mkdir -p "$runtime_dir"

  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(<"$pid_file")"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" >/dev/null 2>&1; then
      if [[ "$have_redis_cli" == "1" ]]; then
        echo "Redis pid ${existing_pid} exists for ${instance_name}, but PING failed at ${host}:${port}." >&2
        echo "Check ${log_file}, REDIS_PASSWORD, and REDIS_DB." >&2
        exit 1
      fi
      echo "Redis appears to be running for ${instance_name} with pid ${existing_pid}." >&2
      return 0
    fi
  fi

  echo "Starting local Redis for ${instance_name} at ${host}:${port}." >&2

  local redis_args=(
    redis-server
    --daemonize yes
    --port "$port"
    --dir "$runtime_dir"
    --pidfile "$pid_file"
    --logfile "$log_file"
    --dbfilename "$db_file"
    --save ""
    --appendonly no
    --protected-mode yes
  )

  case "$host" in
    ::1)
      redis_args+=(--bind "::1")
      ;;
    *)
      redis_args+=(--bind "127.0.0.1")
      ;;
  esac

  if [[ -n "$password" ]]; then
    redis_args+=(--requirepass "$password")
  fi

  "${redis_args[@]}"

  if [[ "$have_redis_cli" == "1" ]]; then
    local attempts
    for attempts in {1..20}; do
      if redis_cli_ping "$host" "$port" "$db" "$password"; then
        return 0
      fi
      sleep 0.2
    done
    echo "Redis for ${instance_name} did not become ready at ${host}:${port}. See ${log_file}." >&2
    exit 1
  fi

  if [[ -f "$pid_file" ]]; then
    local started_pid
    started_pid="$(<"$pid_file")"
    if [[ -n "$started_pid" ]] && kill -0 "$started_pid" >/dev/null 2>&1; then
      return 0
    fi
  fi

  echo "Redis for ${instance_name} started but could not be verified. Install redis-cli for readiness checks." >&2
  exit 1
}
