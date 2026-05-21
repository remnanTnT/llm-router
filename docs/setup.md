# Setup

## Requirements

- Python 3.11+
- PostgreSQL with the existing schema already created (see [Database Schema](database_schema.md))
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

Production start script:

```bash
./start_prod.sh
```

Defaults:

- HTTP port: `8001`
- Database host: `localhost`
- Database port: `5431`
- Workers: `8`
- Threads per worker: `32`

Test start script:

```bash
./start_test.sh
```

Defaults:

- HTTP port: `9000`
- Database host: `localhost`
- Database port: `5432`
- Workers: `1`
- Threads per worker: `8`

Both scripts use `config.yaml` by default and can be overridden with environment variables:

```bash
DB_HOST=127.0.0.1 \
DB_PORT=5433 \
LLM_ROUTER_CONFIG=/path/to/config.yaml \
GUNICORN_WORKERS=4 \
GUNICORN_THREADS=16 \
./start_prod.sh
```

Equivalent production Gunicorn command:

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

The `gthread` worker is important because the router includes client-disconnect tracking designed for the Gunicorn threaded worker model. For non-stream requests, the router watches the downstream client socket and closes the upstream LLM connection when the client disconnects; vLLM should then stop the abandoned request when it observes the closed connection.
