# Database Schema

The database schema is intentionally not owned by Django migrations. Router models use `managed = False`; do not run `makemigrations` for normal schema drift. The live database should be validated with `check_db_schema`.

## Required Tables

`check_db_schema` compares the live database against every model in `router/models.py`. The required tables are:

- `ips`
- `departments`
- `user_ips`
- `models`
- `servers`
- `requests`
- `whitelist`
- `server_operations`
- `mr_live_review`
- `codehub_review`
- `daily_mr_review`
- `live_review_requests`
- `ai_assistant_user_feedback`

## Timezone

Datetime columns should use `TIMESTAMPTZ` on PostgreSQL. The router runs with `TIME_ZONE = Asia/Shanghai` and sets the database connection time zone to `Asia/Shanghai`, so request lifecycle times such as `send_time` and `end_time` are saved and read in Beijing time.

## Core Access Tables

`ips.vip` is admin-managed. Set it to `TRUE` for client IPs allowed to use `server.vip_port`; non-VIP IPs that use the VIP port receive HTTP 503.

```sql
ALTER TABLE ips ADD COLUMN vip BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ips ADD COLUMN concurrent_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0;
```

`departments.is_allowed`, `user_ips.department_id`, and `whitelist.is_allowed` form the permission chain:

```text
user_ips -> departments.is_allowed -> whitelist.is_allowed
```

When `admission.allow_when_user_info_missing` is true, missing `user_ips` data does not block the request.

## `models` Table

Important model columns:

```sql
ALTER TABLE models ADD COLUMN concurrent_limit INTEGER NULL DEFAULT 3;
ALTER TABLE models ADD COLUMN max_tokens INTEGER NOT NULL DEFAULT 20480;
ALTER TABLE models ADD COLUMN vip INTEGER NULL;
ALTER TABLE models ADD COLUMN deprecation VARCHAR(500) NULL;
ALTER TABLE models ADD COLUMN is_routing_model BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE models ADD COLUMN auto BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE models ADD COLUMN max_context_window INTEGER NOT NULL DEFAULT 204800;
ALTER TABLE models ADD COLUMN complexity_min INTEGER NULL;
ALTER TABLE models ADD COLUMN complexity_max INTEGER NULL;
ALTER TABLE models ADD COLUMN multimodal BOOLEAN NOT NULL DEFAULT FALSE;
```

`vip` is admin-managed. Set it to a positive integer to enable VIP routing for that model. The value is the per-active-VIP-server workload threshold above which the router promotes another normal server into the VIP pool. `NULL` or `0` disables VIP routing for the model.

`deprecation` is admin-managed. If it is not `NULL`, the router returns HTTP 400 with this value as the error message.

`is_routing_model` marks models that can receive internal complexity-classification requests and normal-port small-request routing.

`auto` controls auto-routing entry, not target eligibility. Exact `model: auto` requests enter auto routing case-insensitively. On the normal port, requests for a concrete model with `auto = TRUE` also enter auto routing. On the VIP port, concrete model requests keep the requested model.

`complexity_min` and `complexity_max` are text auto-routing target bounds. Both must be non-NULL, between 1 and 10, and `complexity_min <= complexity_max`. A returned complexity score must match exactly one target model; otherwise the router uses `router.fallback_model` where applicable and records the reason in `requests.router_result`.

`multimodal` marks the model as eligible for auto-routed requests that contain `image_url` chat parts.

`max_context_window` is used for context-overflow fallback. When a true auto-selected model returns HTTP 400 and the failure reason contains this value, the router can retry with `router.fallback_model`.

## `servers` Table

Current server columns:

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
    circuit_state VARCHAR(20) NOT NULL DEFAULT 'closed',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_state_change_at TIMESTAMPTZ NULL,
    cooldown_seconds INTEGER NOT NULL DEFAULT 30,
    workload INTEGER NOT NULL DEFAULT 0,
    vip BOOLEAN NOT NULL DEFAULT FALSE,
    vip_cooldown TIMESTAMPTZ NULL,
    context_window INTEGER NULL,
    created_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NULL,
    deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX servers_online_model_idx
    ON servers (is_online, model_id)
    WHERE deleted_at IS NULL;
```

`base_url` should include the upstream API prefix expected by the router, normally `/v1`. The proxy appends the incoming path such as `chat/completions`.

`cache_time` controls how long successful prefix-cache entries for this server stay valid in Redis.

`csb_token`, when present, is injected into upstream requests as the `csb-token` header.

`circuit_state`, `consecutive_failures`, `last_state_change_at`, and `cooldown_seconds` are router-managed circuit-breaker fields. Closed servers are routable. Open servers become half-open after cooldown. Half-open servers are routable for probe traffic.

`workload` is router-managed. It is incremented before an upstream send and decremented when the request finishes or stale processing cleanup runs. Auto-routing classifier servers are selected by this value.

`vip` and `vip_cooldown` are router-managed. The router promotes and demotes servers automatically based on VIP request load.

`context_window` is an optional per-server request-size ceiling. If it is set, candidate selection excludes that server when `requests.estimate_tokens` is larger than the context window.

`weight` is the server's capacity multiplier (default 1). Server selection compares normalized load `workload / weight`, so a server with weight 3 is chosen over a weight-1 server as long as its own workload is below three times the other's. VIP channel candidates are restricted to weight-1 servers.

## `requests` Table

Current request-tracking columns include:

```sql
ALTER TABLE requests ALTER COLUMN target_pod_ip TYPE VARCHAR(500);
ALTER TABLE requests ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE requests ADD COLUMN prefix_cache DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE requests ADD COLUMN final_prefix_cache INTEGER NOT NULL DEFAULT 0;
ALTER TABLE requests ADD COLUMN last_match BIGINT NULL;
ALTER TABLE requests ADD COLUMN router_result VARCHAR(300) NULL;
ALTER TABLE requests ADD COLUMN estimate_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE requests ADD COLUMN model_choosing_latency BIGINT NULL;
ALTER TABLE requests ADD COLUMN ttft BIGINT NULL;
```

`task_status` is one of the request lifecycle states used by the router, including `processing`, `success`, `failed`, `agent_disconnected`, and `incomplete`.

`attempt_count`, `target_pod_ip`, `prefix_cache`, and `last_match` are updated before each upstream attempt.

`final_prefix_cache` stores cached-token usage parsed from successful upstream responses when available.

`router_result` stores auto-routing and small-request-routing decisions, prefixed by the originally requested model name. Examples: `auto:complexity:7`, `AUTO:cache_hit`, `source-model:small_request_routing`, `auto:routing_failed:missing_routing_server:no available routing server`.

`estimate_tokens` stores the fast token estimate from the original request body. It is used for `servers.context_window` filtering.

`model_choosing_latency` stores elapsed milliseconds for model choosing when the request uses true auto selection or small-request routing.

`ttft` stores time-to-first-token in milliseconds. For streaming requests it is measured from the start of the streaming generator to the first non-empty chunk received from the upstream server; for non-streaming requests it is not populated (see `_stream_success` in `proxy.py`).

Internal routing-model calls used to classify auto-routed targets are also recorded in `requests`. These rows use `ip_id = 0`, `user_agent = "llm-choosing"`, `is_stream = FALSE`, and the routing model's `model_id`. Statistics APIs exclude `ip_id = 0` rows.

The required request-table indexes are declared in `RequestRecord._meta.indexes`. Processing partial indexes are important on large `requests` tables because the hot path counts only active `processing` rows.

## Admin And Review Tables

`server_operations` records `/api/add_server` operations:

```sql
CREATE TABLE server_operations (
    id BIGSERIAL PRIMARY KEY,
    server_id INTEGER NULL,
    operation_type VARCHAR(50) NOT NULL,
    request_data JSONB NULL,
    response_data JSONB NULL,
    status VARCHAR(20) NOT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NULL,
    deleted_at TIMESTAMPTZ NULL
);
```

`mr_live_review` stores MR review ingestion and reporting data. `discussion_id` must be unique.

`codehub_review` stores CodeHub review issues.

## `daily_mr_review` Table

`daily_mr_review` stores daily MR review issues. `issue_hash` must be unique and prevents duplicate issue creation.

```sql
CREATE TABLE daily_mr_review (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    branch VARCHAR(200) NOT NULL,
    issue_hash VARCHAR(50) NOT NULL UNIQUE,
    mr_hash VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    line INTEGER NOT NULL,
    body TEXT NOT NULL,
    review_comment TEXT NOT NULL,
    severity VARCHAR(50) NOT NULL,
    categories VARCHAR(200) NOT NULL,
    fix_suggestion TEXT NOT NULL,
    created_at VARCHAR(100) NOT NULL,
    confidence_score VARCHAR(50) NOT NULL,
    issue_url TEXT NOT NULL
);
```

`issue_hash` is the unique identifier computed from the issue content and location. `mr_hash` links the issue to the merge request. `confidence_score` indicates the review confidence level.

## `live_review_requests` Table

`live_review_requests` stores live review request metadata including project name, merge request details, start/end times, duration, model IDs used for expert and reflect phases, and review statistics.

```sql
CREATE TABLE live_review_requests (
    id BIGSERIAL PRIMARY KEY,
    project_name VARCHAR(200) NOT NULL,
    merge_requests_id INTEGER NOT NULL,
    merge_url TEXT NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NULL,
    duration_seconds INTEGER NULL,
    expert_model_id INTEGER NULL,
    reflect_model_id INTEGER NULL,
    review_file_num INTEGER NOT NULL DEFAULT 0,
    diff_part_num INTEGER NOT NULL DEFAULT 0,
    review_num INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NULL,
    deleted_at TIMESTAMPTZ NULL
);
```

`expert_model_id` and `reflect_model_id` reference the models table and track which models were used in the two-phase review process. `duration_seconds` is automatically calculated from `start_time` and `end_time`. `review_file_num`, `diff_part_num`, and `review_num` track review coverage statistics.

## `ai_assistant_user_feedback` Table

`ai_assistant_user_feedback` stores user feedback for AI Assistant tool features. The table tracks issue lifecycle from reporting through resolution.

```sql
CREATE TABLE ai_assistant_user_feedback (
    id BIGSERIAL PRIMARY KEY,
    domain VARCHAR(50) NOT NULL,
    tool_version VARCHAR(100) NULL,
    issue_description TEXT NOT NULL,
    reporter VARCHAR(200) NOT NULL,
    reported_at TIMESTAMPTZ NOT NULL,
    priority VARCHAR(20) NULL,
    assignee VARCHAR(200) NULL,
    status VARCHAR(20) NOT NULL,
    estimated_resolution_at TIMESTAMPTZ NULL,
    actual_resolution_at TIMESTAMPTZ NULL,
    bugfix_version VARCHAR(100) NULL,
    progress_tracking TEXT NULL,
    remarks TEXT NULL,
    created_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NULL,
    deleted_at TIMESTAMPTZ NULL
);
```

`domain` must be one of: `知识管理`, `辅助设计`, `代码分析`, `问题定位`, or `Agent`.

`status` must be one of: `open` (新建), `close` (已关闭), or `cancel` (已取消).

`priority` is optional and must be one of: `高`, `中`, or `低`.

`progress_tracking` is a free-text field for tracking resolution progress and intermediate updates.

The field definitions for these reporting tables are in `router/models.py`; `check_db_schema --dry-run` is the safest way to confirm that a live database matches the current model definitions.

## Schema Validation

Use the management commands to validate schema state:

```bash
python manage.py test init_db
python manage.py test check_db_schema --dry-run
```

`check_db_schema --fix` can create missing tables, add missing columns, drop extra columns/defaults, fix nullable/type/unique mismatches, add missing auto-increment identity, and create missing model-declared indexes. Review the dry-run output before applying fixes to production.
