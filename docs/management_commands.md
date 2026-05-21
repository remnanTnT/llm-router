# Management Commands

All commands are invoked via `python manage.py <command>`. `manage.py` also accepts a leading `prod` or `test` token that selects DB port `5431` / `5432` before delegating to Django.

## `init_db`

Verifies DB connectivity and that all required tables exist; exits non-zero if any are missing.

```bash
python manage.py init_db
```

## `check_db_schema`

Diffs the live PostgreSQL schema against Django model definitions: missing tables/columns, extra columns, default mismatches, NULL/NOT NULL mismatches, type mismatches, and single-column unique-constraint mismatches.

```bash
python manage.py check_db_schema --dry-run
python manage.py check_db_schema --fix
```

## `check_server_health`

Issues HTTP health probes against active servers, updating circuit-breaker state. `--recover-offline` brings passing offline servers back online.

```bash
python manage.py check_server_health --recover-offline
python manage.py check_server_health --server-id 12
```

## `cleanup_stale_processing`

Flips `processing` rows older than the threshold (default 20 minutes) to `incomplete` with `fail_reason="stale processing"` and decrements upstream workload counters.

```bash
python manage.py cleanup_stale_processing --threshold 20
python manage.py cleanup_stale_processing --threshold 20 --dry-run
```
