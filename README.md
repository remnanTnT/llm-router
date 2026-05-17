# llm-router

A Django-based LLM router/gateway for OpenAI-compatible `/v1/*` APIs.

The router sits between clients and an upstream LLM service. It proxies requests, records request metadata, checks admission rules, enforces model token/concurrency limits, and keeps the CMDB integration as a dummy module that can be replaced later.

## Current Scope

Implemented in this phase:

- `/healthy` health check
- `/v1/<path>` reverse proxy
- Streaming and non-streaming upstream responses
- Request body parsing and injection
  - injects `stream_options.include_usage=true` for streaming requests
  - injects default `max_tokens` when missing
- Existing-schema database models with `managed = False`
- IP get-or-create
- Permission check through `user_ips`, `departments`, and `whitelist`
- opencode User-Agent compatibility behavior
  - blocks `opencode/<=1.2.26`
  - delays upstream HTTP 400 responses for `opencode/<=1.2.27`
- Model `max_tokens` validation
- Per-IP/per-model concurrency check
- Request lifecycle recording in the existing `requests` table
- Dummy CMDB service and `/api/refresh_user_info`
- Whitelist update API

Not implemented in this phase:

- Statistics APIs
- Admin UI
- Download API
- Database schema migrations that alter tables
- Real CMDB integration
- Redis-based concurrency counters

## Requirements

- Python 3.11+
- PostgreSQL with the existing schema already created
- Upstream OpenAI-compatible LLM service

Python packages are listed in `requirements.txt`.

## Database Schema

The database schema is intentionally not managed by this project.

The router expects these existing tables:

- `ips`
- `departments`
- `user_ips`
- `user_visit_counts`
- `models`
- `requests`
- `whitelist`

Django models are unmanaged (`managed = False`) and no schema-changing migrations should be generated or applied.

## Configuration

Default configuration is in `config.yaml`.

Important settings:

```yaml
proxy_url: http://localhost:8051
log_path: ./logs/requests

proxy:
  default_max_tokens: 8528
  unknown_model_max_tokens: 20480
  stream_connect_timeout_seconds: 30
  stream_read_timeout_seconds: 900
  stream_total_timeout_seconds: 900
  normal_connect_timeout_seconds: 5
  normal_read_timeout_seconds: 900
  client_disconnect_check_interval_seconds: 0.5
  stale_processing_minutes: 20
  opencode_400_delay_seconds: 180

opencode:
  enabled: true
  block_max_version: "1.2.26"
  delay_400_max_version: "1.2.27"

database:
  host: localhost
  port: 5432
  user: postgres
  password: postgres
  name: postgres
  sslmode: disable
```

You can point the router to another config file with:

```bash
export LLM_ROUTER_CONFIG=/path/to/config.yaml
```

Database values can also be overridden with environment variables:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=postgres
export DB_NAME=postgres
export DB_SSLMODE=disable
```

Other useful environment variables:

```bash
export DJANGO_SECRET_KEY='change-me'
export DJANGO_DEBUG=0
export PROXY_URL=http://localhost:8051
```

## Local Setup

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Validate that Django can load:

```bash
python manage.py check
```

Validate database connectivity and required tables:

```bash
python manage.py init_db
```

Check schema presence without changing anything:

```bash
python manage.py check_db_schema --dry-run
```

## Run Locally With Django Dev Server

```bash
python manage.py runserver 0.0.0.0:8001
```

Health check:

```bash
curl http://localhost:8001/healthy
```

Expected response:

```json
{"status": "healthy"}
```

## Run With Gunicorn

Gunicorn is the recommended way to run the router outside local development.

Basic command:

```bash
gunicorn router_project.wsgi:application \
  --bind 0.0.0.0:8001 \
  --workers 8 \
  --threads 32 \
  --worker-class gthread \
  --timeout 960 \
  --graceful-timeout 1200 \
  --max-requests 1000 \
  --max-requests-jitter 200 \
  --access-logfile - \
  --error-logfile -
```

With an explicit config file:

```bash
LLM_ROUTER_CONFIG=/path/to/config.yaml \
gunicorn router_project.wsgi:application \
  --bind 0.0.0.0:8001 \
  --workers 8 \
  --threads 32 \
  --worker-class gthread \
  --timeout 960 \
  --graceful-timeout 1200
```

The `gthread` worker is important because the router includes client-disconnect tracking designed for the Gunicorn threaded worker model. For non-stream requests, the router watches the downstream client socket and closes the upstream LLM connection when the client disconnects; vLLM should then stop the abandoned request when it observes the closed connection.

## API Endpoints

### Health

```http
GET /healthy
```

Returns `200` when the app and database are healthy. Returns `503` when the database check fails.

### Proxy

```http
/v1/<path>
```

All `/v1/*` requests are proxied to `proxy_url` with the same path and query string.

Example:

```bash
curl -i http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"test-model","messages":[{"role":"user","content":"hi"}]}'
```

### Whitelist Update

```http
POST /api/whitelist/update
```

JSON example:

```bash
curl -i -X POST http://localhost:8001/api/whitelist/update \
  -H 'Content-Type: application/json' \
  -d '{"employee_no":"E001","is_allowed":1}'
```

### Refresh User Info

```http
POST /api/refresh_user_info
```

Starts the dummy CMDB refresh flow in a background thread:

```bash
curl -i -X POST http://localhost:8001/api/refresh_user_info
```

The current CMDB implementation is a no-op placeholder. It preserves the API and call flow so real corporate CMDB code can be added later.

## Management Commands

Validate required tables:

```bash
python manage.py init_db
```

Check schema presence:

```bash
python manage.py check_db_schema --dry-run
```

Clean stale processing requests:

```bash
python manage.py cleanup_stale_processing --threshold 20
```

Dry run:

```bash
python manage.py cleanup_stale_processing --threshold 20 --dry-run
```

## Tests

Run unit tests:

```bash
python -m pytest tests
```

Current tests cover:

- Request parser injection
- opencode version policy
- Header filtering
- SSE usage parsing
- OpenAI-compatible error response shape

## Notes

- Do not run `makemigrations` for schema changes unless the database ownership model changes.
- Do not add Statistics APIs in the router-only phase.
- Do not commit real database passwords, upstream API keys, or corporate CMDB credentials.
