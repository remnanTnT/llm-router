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

wait_for_redis_ready() {
  local instance_name="$1"
  local host="$2"
  local port="$3"
  local db="$4"
  local password="${5:-}"
  local log_hint="${6:-Redis logs}"
  local attempts

  for attempts in {1..30}; do
    if redis_cli_ping "$host" "$port" "$db" "$password"; then
      return 0
    fi
    sleep 0.2
  done

  echo "Redis for ${instance_name} did not become ready at ${host}:${port}. See ${log_hint}." >&2
  exit 1
}

try_systemctl_redis() {
  local instance_name="$1"
  local host="$2"
  local port="$3"
  local db="$4"
  local password="${5:-}"
  local service

  if [[ "$port" != "6379" || -n "$password" ]]; then
    return 1
  fi

  case "$host" in
    localhost|127.0.0.1)
      ;;
    *)
      return 1
      ;;
  esac

  if ! command -v systemctl >/dev/null 2>&1; then
    return 1
  fi

  for service in "${REDIS_SYSTEMD_SERVICE:-redis}" redis-server; do
    if systemctl list-unit-files "$service.service" >/dev/null 2>&1; then
      echo "Starting Redis systemd service ${service}.service for ${instance_name}." >&2
      if systemctl start "$service.service" >/dev/null 2>&1; then
        wait_for_redis_ready "$instance_name" "$host" "$port" "$db" "$password" "${service}.service"
        return 0
      fi
    fi
  done

  return 1
}

start_nohup_redis() {
  local instance_name="$1"
  local host="$2"
  local port="$3"
  local db="$4"
  local password="${5:-}"
  local runtime_dir
  local pid_file
  local log_file
  local db_file
  local bind_host
  local redis_args

  if ! command -v redis-server >/dev/null 2>&1; then
    echo "redis-server is required to start local Redis for ${instance_name}." >&2
    echo "Install Redis first, for example: sudo dnf install redis" >&2
    echo "Or set REDIS_HOST/REDIS_PORT to an existing Redis service." >&2
    exit 1
  fi

  runtime_dir="${REDIS_RUNTIME_DIR:-$(pwd)/.runtime/redis-${instance_name}}"
  pid_file="${REDIS_PID_FILE:-${runtime_dir}/redis.pid}"
  log_file="${REDIS_LOG_FILE:-${runtime_dir}/redis.log}"
  db_file="${REDIS_DB_FILE:-dump.rdb}"

  mkdir -p "$runtime_dir"

  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(<"$pid_file")"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" >/dev/null 2>&1; then
      echo "Redis pid ${existing_pid} exists for ${instance_name}, but PING failed at ${host}:${port}." >&2
      echo "Check ${log_file}, REDIS_PASSWORD, and REDIS_DB." >&2
      exit 1
    fi
  fi

  case "$host" in
    ::1)
      bind_host="::1"
      ;;
    *)
      bind_host="127.0.0.1"
      ;;
  esac

  echo "Starting redis-server with nohup for ${instance_name} at ${bind_host}:${port}." >&2
  redis_args=(
    redis-server
    --bind "$bind_host"
    --port "$port"
    --dir "$runtime_dir"
    --dbfilename "$db_file"
    --save ""
    --appendonly no
    --protected-mode yes
  )

  if [[ -n "$password" ]]; then
    redis_args+=(--requirepass "$password")
  fi

  nohup "${redis_args[@]}" >"$log_file" 2>&1 &
  echo "$!" >"$pid_file"
  wait_for_redis_ready "$instance_name" "$host" "$port" "$db" "$password" "$log_file"
}

ensure_local_redis() {
  local instance_name="${1:?missing Redis instance name}"
  local host="${REDIS_HOST:-127.0.0.1}"
  local port="${REDIS_PORT:-6379}"
  local db="${REDIS_DB:-0}"
  local password="${REDIS_PASSWORD:-}"

  case "$host" in
    localhost|127.0.0.1|::1)
      ;;
    *)
      echo "Using external Redis at ${host}:${port}; local Redis startup skipped." >&2
      return 0
      ;;
  esac

  if ! command -v redis-cli >/dev/null 2>&1; then
    echo "redis-cli is required to verify local Redis for ${instance_name}." >&2
    echo "Install Redis first, for example: sudo dnf install redis" >&2
    exit 1
  fi

  if redis_cli_ping "$host" "$port" "$db" "$password"; then
    echo "Redis is already running at ${host}:${port}." >&2
    return 0
  fi

  if try_systemctl_redis "$instance_name" "$host" "$port" "$db" "$password"; then
    return 0
  fi

  start_nohup_redis "$instance_name" "$host" "$port" "$db" "$password"
}
