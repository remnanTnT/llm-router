# Setup

## Requirements

- Python 3.11+
- PostgreSQL with the existing schema already created (see [Database Schema](database_schema.md))
- Redis server for prefix-cache storage
- Upstream OpenAI-compatible LLM service

Python packages are listed in `requirements.txt`.

## Local Setup

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Validate that Django can load:

```bash
python manage.py test check
```

Validate database connectivity and required tables:

```bash
python manage.py test init_db
```

Check schema presence without changing anything:

```bash
python manage.py test check_db_schema --dry-run
```

## Run Locally With Django Dev Server

```bash
python manage.py test runserver 0.0.0.0:8001
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

Production start script:

```bash
./start_prod.sh
```

Defaults:

- HTTP port: `8001`
- VIP port: `8008`
- Redis port: `6379`
- Database host: `localhost`
- Database port: `5431`
- Workers: `8`
- Threads per worker: `64`

Test start script:

```bash
./start_test.sh
```

Defaults:

- HTTP port: `9000`
- VIP port: `9001`
- Redis port: `6380`
- Database host: `localhost`
- Database port: `5432`
- Workers: `1`
- Threads per worker: `8`

Both scripts check Redis with `redis-cli ping` when `REDIS_HOST` is local. If Redis is not running, they try to start the system Redis service for the default local port, then fall back to starting `redis-server` with `nohup` on the selected `REDIS_PORT`. Runtime files for the `nohup` path are written under `.runtime/redis-prod` or `.runtime/redis-test` by default.

Both scripts use `config.yaml` by default and can be overridden with environment variables:

```bash
DB_HOST=127.0.0.1 \
DB_PORT=5433 \
REDIS_PORT=6381 \
LLM_ROUTER_CONFIG=/path/to/config.yaml \
LLM_ROUTER_LOG_PATH=/data/router_log \
GUNICORN_WORKERS=4 \
GUNICORN_THREADS=16 \
./start_prod.sh
```

`start_prod.sh` defaults request logs to `/data/router_log` and disables verbose request logging. `start_test.sh` defaults request logs to `.logs/requests`, enables verbose request logging, and writes a `user_request` event into the per-request log file.

Equivalent production Gunicorn command:

```bash
gunicorn router_project.wsgi:application \
  --bind 0.0.0.0:8001 \
  --workers 8 \
  --threads 64 \
  --worker-class gthread \
  --timeout 960 \
  --graceful-timeout 1200 \
  --max-requests 1000 \
  --max-requests-jitter 200 \
  --access-logfile - \
  --error-logfile -
```

The `gthread` worker is important because the router includes client-disconnect tracking designed for the Gunicorn threaded worker model. For non-stream requests, the router watches the downstream client socket and closes the upstream LLM connection when the client disconnects; vLLM should then stop the abandoned request when it observes the closed connection.
