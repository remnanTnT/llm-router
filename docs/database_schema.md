# Database Schema

The database schema is intentionally not managed by this project. Django models are unmanaged (`managed = False`) and no schema-changing migrations should be generated or applied.

## Required Tables

The router expects these existing tables:

- `ips`
- `departments`
- `user_ips`
- `models`
- `requests`
- `whitelist`
- `servers`

## Timezone

All datetime columns should use `TIMESTAMPTZ`. The router runs with `TIME_ZONE = Asia/Shanghai` and sets the database connection time zone to `Asia/Shanghai`, so request lifecycle times such as `send_time` and `end_time` are saved and read in Beijing time.

## `servers` Table

```sql
CREATE TABLE servers (
    id BIGSERIAL PRIMARY KEY,
    model_id INTEGER NULL,
    base_url VARCHAR(500) NOT NULL UNIQUE,
    is_online BOOLEAN NOT NULL DEFAULT TRUE,
    weight INTEGER NOT NULL DEFAULT 1,
    health_path VARCHAR(200) NOT NULL DEFAULT '/healthy',
    last_checked_at TIMESTAMPTZ NULL,
    last_failure_at TIMESTAMPTZ NULL,
    cache_time INTEGER NOT NULL DEFAULT 3600,
    csb_token VARCHAR(500) NULL,
    vip BOOLEAN NOT NULL DEFAULT FALSE,
    vip_cooldown TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX servers_online_model_idx
    ON servers (is_online, model_id)
    WHERE deleted_at IS NULL;
```

`vip` and `vip_cooldown` are router-managed; do not edit them by hand. The router promotes and demotes servers automatically based on VIP request load.

## `models` Table

```sql
ALTER TABLE models ADD COLUMN vip INTEGER NULL;
```

`vip` is admin-managed. Set it to a positive integer to enable VIP routing for that model: it is the per-active-VIP-server workload threshold above which the router promotes another normal server into the VIP pool. `NULL` or `0` disables VIP routing for the model — VIP-port traffic for it is served from the normal pool.

## Request-Table Indexes

Create the request-table indexes from `sql/requests_indexes.sql` on PostgreSQL. The processing partial indexes are required for the LLM request hot path because the `requests` table can be very large while active `processing` rows are small. Run these outside a transaction because they use `CREATE INDEX CONCURRENTLY`.

## Load-Balancer Columns

The load balancer also records the selected backend and number of backend attempts per request:

```sql
ALTER TABLE servers ADD COLUMN cache_time INTEGER NOT NULL DEFAULT 3600;
ALTER TABLE requests ALTER COLUMN target_pod_ip TYPE VARCHAR(500);
ALTER TABLE requests ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE requests ADD COLUMN prefix_cache DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE requests ADD COLUMN last_match BIGINT NULL;
```

## Schema Validation

Use the management commands to validate schema state without altering tables:

```bash
python manage.py test init_db
python manage.py test check_db_schema --dry-run
```
