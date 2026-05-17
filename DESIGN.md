# LLM Router Project Design

## 1. Scope

This project implements only the LLM router/gateway part first.

In scope:

- Health check.
- `/v1/*` reverse proxy to an upstream OpenAI-compatible LLM service.
- Streaming and non-streaming proxy behavior.
- Request parsing and request body injection.
- IP registration.
- CMDB service interface and refresh API, implemented as a dummy/no-op module for now.
- Permission check using the existing database tables.
- opencode User-Agent version check.
- Model `max_tokens` validation.
- Per-IP/per-model concurrency control.
- Request recording.
- Optional per-request log files.
- Whitelist update API because it is part of the router admission path.

Out of scope for the first implementation:

- All Statistics APIs.
- Stats service/query implementation.
- Admin UI.
- New database schema design.
- Database schema changes.
- Redis concurrency counters.

Important constraints:

1. **The database schema cannot be changed.** The implementation must use the schema from `requirement.md` as-is.
2. **CMDB is unavailable outside the corporate environment**, but the CMDB module, API, and call flow must remain. The initial implementation provides a dummy module with the same interface so the real CMDB logic can be filled in later.
3. **Statistics APIs are removed from this phase.** Request data should still be recorded so stats can be added later without changing router behavior.
4. **opencode compatibility behavior is enabled.** `opencode/≤1.2.26` is blocked before proxying. `opencode/≤1.2.27` receives the configured delay when upstream returns HTTP 400.

---

## 2. Recommended Stack

Use the same general runtime model as the existing requirements:

- Python 3.11
- Django
- PostgreSQL
- `requests` for upstream proxying and future CMDB calls
- `PyYAML` for configuration
- `django-cors-headers` if browser clients are expected
- Gunicorn with `gthread` workers

Django is preferred for this rewrite because:

- The required schema is already described in Django-oriented terms.
- The project needs to preserve existing table names and column names.
- The existing request lifecycle depends on WSGI/Gunicorn behavior for client disconnect detection.
- The router must keep current API and logic compatibility, not introduce a new schema.

---

## 3. High-Level Architecture

```text
Client
  |
  | /v1/*
  v
Django LLM Router
  |
  |-- API Layer
  |     |-- /healthy
  |     |-- /v1/<path>
  |     |-- /api/whitelist/update
  |     |-- /api/refresh_user_info
  |
  |-- Request Parser
  |     |-- extract model, stream, max_tokens
  |     |-- inject stream_options.include_usage
  |     |-- inject default max_tokens
  |
  |-- CMDB Service
  |     |-- dummy implementation now
  |     |-- same interface for future real implementation
  |
  |-- Admission Service
  |     |-- permission check
  |     |-- opencode version check
  |     |-- model max_tokens check
  |     |-- concurrency check
  |
  |-- Proxy Service
  |     |-- streaming proxy
  |     |-- non-streaming proxy
  |
  |-- Request Recorder
  |     |-- requests table
  |     |-- optional request log file
  |
  v
Upstream LLM Service
```

---

## 4. API Surface For This Phase

### 4.1 Health Check

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthy` | Check service/database health |

Response:

```json
{"status": "healthy"}
```

If the database is unavailable, return HTTP 503.

---

### 4.2 Reverse Proxy

| Method | Path | Purpose |
|---|---|---|
| `ALL` | `/v1/<path>` | Proxy OpenAI-compatible requests to upstream |

The proxy route is the core of this phase.

Supported behavior:

- Accept all HTTP methods used by OpenAI-compatible APIs.
- Forward request path and query string to configured upstream `proxy_url`.
- Forward request body, possibly modified by `RequestParser`.
- Forward request headers after removing hop-by-hop and invalid proxy headers.
- Support streaming SSE responses.
- Support normal JSON responses.
- Record request lifecycle in the existing `requests` table.

---

### 4.3 Whitelist Update

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/whitelist/update` | Create/update whitelist entry |

Keep this API because router admission logic depends on the `whitelist` table.

Parameters:

- `employee_no`: required string
- `is_allowed`: required integer, `0` or `1`

Supported content types:

- JSON
- Form data

Behavior:

- If the employee number does not exist, create a whitelist row.
- If it exists, update `is_allowed` and `update_time`.
- If value is unchanged, return a success response indicating no effective change.

---

### 4.4 Refresh User Info

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/refresh_user_info` | Trigger CMDB full refresh task |

Keep this API even though CMDB is not currently available.

Current dummy behavior:

- Start a background daemon thread.
- Iterate known IP records.
- Call dummy `CMDBService.fetch_and_save_user(ip)` for each IP.
- The dummy method logs that CMDB is not implemented and returns without modifying data.
- Return immediately:

```json
{
  "code": 200,
  "message": "用户信息刷新任务已启动"
}
```

Future behavior:

- The real corporate CMDB implementation can replace the dummy internals without changing route handlers, admission logic, or call sites.

---

## 5. APIs Removed From This Phase

Do not implement these endpoints in the first router-only phase:

- `/api/request_stats`
- `/api/total_request_count`
- `/api/model_request_stats`
- `/api/all_model_request_stats`
- `/api/models`
- `/api/model_info`
- `/api/request_time_stats`
- `/api/model_request_time_stats`
- `/api/model_request_count_by_period`
- `/api/model_ip_count_by_period`
- `/api/model_latency_boxplot`
- `/api/download/ai_assistant`

The router must still write enough request data for future statistics work.

---

## 6. Database Design

The schema **must not be changed**.

Use the existing seven tables exactly as described in `requirement.md`:

1. `ips`
2. `departments`
3. `user_ips`
4. `user_visit_counts`
5. `models`
6. `requests`
7. `whitelist`

Do not add:

- New tables.
- New columns.
- New foreign keys.
- New indexes beyond the existing required schema.
- Renamed timestamp columns.
- Replacement user/team/upstream tables.

All cross-table relationships remain logical relationships using integer ID columns, because that is how the current schema is defined.

---

## 7. Existing Tables Used By Router

### 7.1 `ips`

Used for:

- Recording every client IP seen by the router.
- Reading `concurrent_multiplier` for concurrency control.

Relevant columns:

| Column | Usage |
|---|---|
| `id` | Logical IP ID |
| `ip` | Client IP string, unique |
| `concurrent_multiplier` | Multiplier applied to model concurrency limit |
| `created_at` / `updated_at` / `deleted_at` | Existing lifecycle columns |

When a request arrives, call `IPRepository.get_or_create(client_ip)`.

---

### 7.2 `departments`

Used for permission checks through `user_ips.department_id`.

Relevant columns:

| Column | Usage |
|---|---|
| `id` | Logical department ID |
| `dept1` - `dept4` | Existing department hierarchy fields |
| `is_allowed` | `1` means allowed; `0` or `NULL` means not explicitly allowed |

Do not replace this table with a new teams table.

---

### 7.3 `user_ips`

Used for IP-to-user mapping.

Relevant columns:

| Column | Usage |
|---|---|
| `id` | Logical user/IP mapping ID |
| `ip_id` | Logical reference to `ips.id` |
| `user_name` | User name from CMDB/future implementation |
| `user_charge` | Responsible user from CMDB/future implementation |
| `department_id` | Logical reference to `departments.id` |
| `employee_no` | Used to match `whitelist.employee_no` |
| `is_valid` | Whether mapping is valid |

In the dummy CMDB phase, this table is not auto-populated unless data already exists or is manually inserted.

---

### 7.4 `models`

Used for:

- Model lookup by request body `model`.
- `max_tokens` limit.
- Per-IP concurrency limit.
- Dynamic model creation after successful response when model did not exist before request.

Relevant columns:

| Column | Usage |
|---|---|
| `id` | Logical model ID |
| `model_name` | Request model name |
| `concurrent_limit` | Per-IP limit; `NULL` means unlimited |
| `max_tokens` | Maximum allowed request `max_tokens` |

No upstream routing columns may be added. The upstream base URL comes from YAML config `proxy_url`.

---

### 7.5 `requests`

Core request lifecycle table.

Use existing columns exactly:

| Column | Usage |
|---|---|
| `id` | Request ID and optional log file name |
| `user_ip_id` | Keep existing behavior; currently hardcoded to `1` unless a safe existing mapping is available |
| `ip_id` | Logical reference to `ips.id` |
| `send_time` | Request start time |
| `end_time` | Request end time |
| `latency` | Latency in milliseconds |
| `model_id` | Logical reference to `models.id`; use `0` while model is unknown if required by existing behavior |
| `input_token_cnt` | Prompt/input token count |
| `output_token_cnt` | Completion/output token count |
| `task_status` | `processing`, `success`, `failed`, `incomplete`, `agent_disconnected` |
| `status` | HTTP status text |
| `fail_reason` | Failure reason, truncated to fit column |
| `is_stream` | Whether request is streaming |
| `user_agent` | Record User-Agent and apply opencode compatibility policy |
| `target_pod_ip` | Value from upstream `target-pod-ip` response header |
| `created_at` / `updated_at` / `deleted_at` | Existing lifecycle columns |

Blocked requests must create `failed` records when enough context is available.

---

### 7.6 `whitelist`

Used as an override in permission checks.

Relevant columns:

| Column | Usage |
|---|---|
| `employee_no` | Matched against `user_ips.employee_no` |
| `user_name` | Optional display value |
| `is_allowed` | `1` means allowed |
| `update_time` | Existing update timestamp column |

Do not rename `update_time`.

---

## 8. Configuration

Use YAML config plus environment variables for secrets.

Example:

```yaml
proxy_url: http://localhost:8051
log_path: ./logs/requests

server:
  bind: 0.0.0.0:8001
  data_upload_max_memory_size_mb: 50

proxy:
  default_max_tokens: 8528
  stream_connect_timeout_seconds: 30
  stream_read_timeout_seconds: 900
  stream_total_timeout_seconds: 900
  normal_connect_timeout_seconds: 5
  normal_read_timeout_seconds: 900
  stale_processing_minutes: 20
  opencode_400_delay_seconds: 180

opencode:
  enabled: true
  block_max_version: "1.2.26"
  delay_400_max_version: "1.2.27"

admission:
  # Keep existing behavior: missing UserIP/Department data allows the request.
  allow_when_user_info_missing: true

cmdb:
  enabled: false
  dummy: true
  refresh_interval_between_ips_seconds: 1

database:
  host: localhost
  port: 5432
  user: postgres
  password: postgres
  name: postgres
  sslmode: disable
```

The opencode policy follows the legacy gateway behavior: block old clients before proxying and delay responses for compatible old clients when upstream returns HTTP 400.

---

## 9. Request Flow

```text
Client request /v1/*
  |
  v
[1] Read request body
  |-- body too large -> 413 + failed request record when possible
  |-- client disconnected while uploading -> 499
  v
[2] Extract client IP and User-Agent
  |
  v
[3] Get or create ips row
  |
  v
[4] Trigger dummy CMDB sync for new IP
  |-- same call site as real CMDB
  |-- no-op outside corporate environment
  v
[5] Permission check
  |-- UserIP missing -> allow
  |-- department missing -> allow
  |-- department.is_allowed == 1 -> allow
  |-- whitelist employee_no allowed -> allow
  |-- otherwise -> 403 + failed request record
  v
[6] opencode User-Agent version check
  |-- UA contains opencode/≤1.2.26 -> 403 + failed request record
  |-- otherwise -> allow
  v
[7] Parse request body
  |-- extract model, stream, max_tokens
  |-- inject stream_options.include_usage for streaming
  |-- inject default max_tokens when missing
  v
[8] Model/max_tokens check
  |-- model exists and max_tokens > model.max_tokens -> 400 + failed request record
  |-- model missing -> use default max_tokens limit 20480
  v
[9] Concurrency check
  |-- cleanup stale processing rows
  |-- model missing -> no concurrency limit
  |-- model.concurrent_limit is NULL -> no concurrency limit
  |-- otherwise enforce ceil(model.concurrent_limit * ip.concurrent_multiplier)
  v
[10] Create processing request record
  |
  v
[11] Forward to upstream
  |-- streaming path
  |-- non-streaming path
  |-- if UA contains opencode/≤1.2.27 and upstream returns 400, delay before returning
  v
[12] Parse token usage and target-pod-ip
  |
  v
[13] Update request record final state
```

The User-Agent version gate applies only to `opencode/<semver>` clients. Missing, malformed, or non-opencode User-Agent values are allowed.

---

## 10. Request Parser

Responsibilities:

- Read request body once.
- Parse JSON body when possible.
- Extract:
  - `model`
  - `stream`
  - `max_tokens`
- For streaming requests, inject:

```json
{
  "stream_options": {
    "include_usage": true
  }
}
```

- If `max_tokens` is missing, inject:

```json
{
  "max_tokens": 8528
}
```

- Serialize the modified body and send it upstream.
- If the body is not JSON, proxy it unchanged and treat model as unknown.

Default values:

| Setting | Value |
|---|---|
| Default injected `max_tokens` | `8528` |
| Unknown model max token limit | `20480` |

---

## 11. Dummy CMDB Module

The CMDB module must exist from the beginning, but its implementation is a dummy/no-op outside the corporate environment.

### 11.1 Required Interface

```text
CMDBService
  fetch_and_save_user(ip: str) -> None
  fetch_all_users() -> None
```

Optional internal methods may be defined for the future real implementation, but route handlers and admission code should only depend on the public interface above.

### 11.2 Dummy Behavior

`fetch_and_save_user(ip)`:

- Ensure the IP row exists or accept an already-created IP.
- Log that CMDB is disabled/not implemented.
- Do not call external services.
- Do not fail the request.
- Do not write fake user data.

`fetch_all_users()`:

- Iterate all non-deleted rows in `ips`.
- Call `fetch_and_save_user(ip)`.
- Sleep for the configured interval between IPs.
- Run in a background daemon thread when triggered by `/api/refresh_user_info`.

### 11.3 Future Real CMDB Behavior

The real implementation can later fill in:

1. Login to corporate CMDB.
2. Query asset/user by IP.
3. Query HR/user details.
4. Get department hierarchy.
5. Upsert `departments`.
6. Create/update `user_ips`.

No router API or admission call flow should need to change when this is implemented.

---

## 12. Permission Check

Keep the existing permission logic.

```text
ip_id
  |
  |-- no UserIP row -> allow
  |
  |-- UserIP.department_id is NULL -> allow
  |
  |-- Department row missing -> allow
  |
  |-- Department.is_allowed == 1 -> allow
  |
  |-- Whitelist has same employee_no and is_allowed == 1 -> allow
  |
  `-- otherwise -> reject 403
```

Design notes:

- This means dummy CMDB does not block unknown users by default.
- If corporate CMDB later populates `user_ips` and `departments`, the same permission logic becomes effective.
- Whitelist remains an override for users in departments that are not allowed.

---

## 13. opencode Version Policy

Apply the legacy opencode User-Agent compatibility behavior after permission check and before request parsing/model validation.

Rules:

| Condition | Behavior |
|---|---|
| User-Agent contains `opencode/≤1.2.26` | Block immediately with HTTP 403 |
| User-Agent contains `opencode/≤1.2.27` and upstream returns HTTP 400 | Delay the response by the configured number of seconds |
| Missing User-Agent | Allow |
| Non-opencode User-Agent | Allow |
| Malformed opencode version | Allow |

Version extraction regex:

```text
opencode/(\d+\.\d+\.\d+)
```

Blocked response:

```json
{
  "error": {
    "message": "Your opencode version ({ver}) is no longer supported. Please upgrade opencode to latest version.",
    "type": "version_too_old",
    "code": null
  }
}
```

The upstream HTTP 400 delay is intentionally configurable so tests and non-corporate deployments can shorten it if needed. The compatibility default is 180 seconds.

---

## 14. Model Validation

Model name comes from the request JSON field `model`.

Behavior:

1. Look up `models.model_name`.
2. If the model exists:
   - Use `models.max_tokens` for validation.
   - Use `models.concurrent_limit` for concurrency.
3. If the model does not exist:
   - Allow the request if `max_tokens <= 20480`.
   - Skip concurrency limiting because there is no model ID/limit yet.
   - If the upstream response succeeds, dynamically create the model record.
   - Update the request record from model ID `0` to the newly created model ID if existing logic supports it.

Reject when:

```text
requested max_tokens > model.max_tokens
```

Return HTTP 400 with OpenAI-compatible error body.

---

## 15. Concurrency Control

Use the existing `requests` table.

Before checking concurrency:

- Mark stale `processing` records older than configured threshold as `incomplete`.
- Default threshold: 20 minutes.

Concurrency rules:

1. If model is unknown, allow.
2. If `models.concurrent_limit` is `NULL`, allow.
3. Compute:

```text
effective_limit = ceil(models.concurrent_limit * ips.concurrent_multiplier)
```

4. Count current rows:

```sql
SELECT COUNT(*)
FROM requests
WHERE ip_id = :ip_id
  AND model_id = :model_id
  AND task_status = 'processing';
```

5. If current count is greater than or equal to effective limit, reject with HTTP 429.
6. Otherwise allow and create a new `processing` request record.

Known limitation:

- The DB count and request-record creation are not fully atomic under high concurrency.
- Do not introduce Redis in this first phase.
- Keep the implementation simple and compatible with the existing schema.

---

## 16. Request Recording

### 15.1 Processing Record

Create a `requests` row immediately before forwarding upstream.

Initial values:

| Field | Value |
|---|---|
| `task_status` | `processing` |
| `send_time` | current time |
| `model_id` | existing model ID or `0` for unknown model |
| `ip_id` | current IP ID |
| `user_ip_id` | keep existing behavior, default `1` |
| `is_stream` | parsed stream flag |
| `user_agent` | request User-Agent |
| `input_token_cnt` | `0` initially |
| `output_token_cnt` | `0` initially |

### 15.2 Final Update

At request completion update:

| Field | Value |
|---|---|
| `end_time` | current time |
| `latency` | milliseconds between `send_time` and `end_time` |
| `task_status` | `success`, `failed`, or `agent_disconnected` |
| `status` | HTTP status text |
| `fail_reason` | truncated failure reason if failed |
| `input_token_cnt` | parsed prompt tokens |
| `output_token_cnt` | parsed completion tokens |
| `target_pod_ip` | upstream response header if present |

### 15.3 Blocked Request Record

Create a `failed` request row for router-side blocks:

- Permission denied.
- `max_tokens` too large.
- Concurrency limit exceeded.
- Request body too large.

Use:

| Field | Value |
|---|---|
| `task_status` | `failed` |
| `latency` | `0` |
| `send_time` / `end_time` | current time |
| `status` | corresponding HTTP status text |
| `fail_reason` | short reason string |

---

## 17. Proxy Header Handling

### 16.1 Request Headers

Forward most client headers, but remove hop-by-hop/proxy-invalid headers:

- `Connection`
- `Keep-Alive`
- `Proxy-Authenticate`
- `Proxy-Authorization`
- `TE`
- `Trailers`
- `Transfer-Encoding`
- `Upgrade`
- `Content-Length`
- `Host`
- `Content-Encoding`

For `GET`, `HEAD`, `OPTIONS`, and `DELETE`, remove `Content-Type`.

The HTTP client library should calculate the final `Content-Length`.

### 16.2 Response Headers

Streaming response:

- Set `Content-Type: text/event-stream`.
- Set `Cache-Control: no-cache`.
- Set `X-Accel-Buffering: no`.

Non-streaming response:

- Preserve upstream `Content-Type` when available.

For both:

- Read upstream `target-pod-ip` response header and store it in `requests.target_pod_ip`.

---

## 18. Streaming Proxy

Streaming requests are detected from JSON body field:

```json
{"stream": true}
```

Behavior:

1. Create `processing` request record.
2. Send upstream request with `stream=True`.
3. Use timeouts:
   - connect timeout: 30 seconds
   - read timeout: 900 seconds
   - total streaming duration: 900 seconds
4. Yield upstream chunks to the client as they arrive.
5. Buffer SSE chunks enough to parse final token usage.
6. If total stream duration exceeds limit:
   - emit a timeout SSE error if possible
   - emit `[DONE]`
   - mark request failed with 504 status
7. If client disconnects:
   - stop reading upstream
   - mark request `agent_disconnected`
8. On stream completion:
   - parse token usage
   - dynamically create missing model after successful response
   - update request record

SSE usage parsing:

- Parse lines beginning with `data:`.
- Ignore blank lines.
- Ignore `data: [DONE]`.
- Decode JSON objects.
- Keep the last object with a `usage` field.
- Extract:
  - `usage.prompt_tokens`
  - `usage.completion_tokens`

If the upstream response status is HTTP 400 and the User-Agent contains `opencode/≤1.2.27`, delay for `proxy.opencode_400_delay_seconds` before returning the upstream response to the client.

---

## 19. Non-Streaming Proxy

Behavior:

1. Create `processing` request record.
2. Send upstream request with timeouts:
   - connect timeout: 5 seconds
   - read timeout: 900 seconds
3. Wait for upstream response.
4. Parse token usage from JSON response if available.
5. Dynamically create missing model after successful response.
6. Update request record.
7. Return upstream body and status code to client.

Failure behavior:

| Scenario | HTTP response | Request status |
|---|---|---|
| Upstream read timeout | 504 | `failed` |
| Upstream connection/proxy exception | 502 | `failed` |
| Client disconnected | empty/connection closed | `agent_disconnected` |
| Upstream non-2xx response | upstream status | `failed` |
| Upstream 2xx response | upstream status | `success` |

If the upstream response status is HTTP 400 and the User-Agent contains `opencode/≤1.2.27`, delay for `proxy.opencode_400_delay_seconds` before returning the upstream response to the client.

---

## 20. Client Disconnect Detection

Keep the existing Gunicorn/gthread-based design when using Django.

Components:

- `ClientDisconnectMiddleware`
- `ClientDisconnectTracker`
- `DisconnectWatcher`

Mechanism:

- Read `gunicorn.socket` from `request.META` when available.
- Use non-blocking socket checks.
- Cache disconnect result after detected.
- For non-streaming requests, use a watcher thread checking every 0.5 seconds.
- For streaming requests, check between chunk yields.

If `gunicorn.socket` is unavailable, the router should still function but may not detect disconnects early.

---

## 21. Error Responses

Use OpenAI-compatible JSON for router-generated errors:

```json
{
  "error": {
    "message": "Access denied, you do not have permission",
    "type": "permission_denied",
    "code": null
  }
}
```

Required errors:

| HTTP | Type | Scenario |
|---|---|---|
| 400 | `invalid_request_error` | `max_tokens` exceeds model limit |
| 403 | `permission_denied` | Permission check failed |
| 403 | `version_too_old` | opencode client version is too old |
| 413 | `request_too_large` | Request body too large |
| 429 | `concurrent_limit_exceeded` | Per-IP/model concurrency exceeded |
| 499 | none | Client disconnected while uploading request |
| 502 | `server_error` | Upstream/proxy exception |
| 504 | `gateway_timeout_error` | Upstream timeout or stream total timeout |

---

## 22. Request Logging

Request logging is optional but recommended because the existing behavior uses per-request logs.

Design:

- Before `request_id` exists, write messages into an in-memory request log buffer.
- After the `requests` row is created, flush the buffer to `{log_path}/{request_id}.log`.
- Append important proxy events:
  - admission result
  - upstream URL
  - upstream status
  - timeout/exception details
  - token usage parsing result
- If a request is blocked before a request ID exists and no DB record can be created, fallback to stdout/application log.

Do not put secrets or full authorization headers into request logs.

---

## 23. Project Structure

```text
llm-router/
  manage.py
  config.yaml
  requirements.txt
  router_project/
    settings.py
    urls.py
    wsgi.py
  router/
    models.py
    urls.py
    views.py
    middleware.py
    repositories/
      ips.py
      departments.py
      user_ips.py
      models.py
      requests.py
      whitelist.py
    services/
      admission.py
      cmdb.py
      proxy.py
      parser.py
      opencode.py
      request_logger.py
      disconnect.py
    utils/
      errors.py
      headers.py
      sse.py
      time.py
    management/
      commands/
        init_db.py
        cleanup_stale_processing.py
  tests/
    test_parser.py
    test_admission.py
    test_proxy_headers.py
    test_sse.py
  DESIGN.md
  requirement.md
```

Do not include stats modules in this phase.

---

## 24. Implementation Phases

### Phase 1: Project Skeleton

- Django project/app setup.
- Config loading.
- Database connection.
- Existing-table models with `managed = False` if tables already exist.
- URL routing.
- Health check.

### Phase 2: Core Proxy

- `/v1/<path>` route.
- Header filtering.
- Upstream URL construction from `proxy_url`.
- Non-streaming proxy.
- Streaming proxy.
- Basic timeout handling.

### Phase 3: Request Parser and Recording

- JSON request parsing.
- `stream_options.include_usage` injection.
- Default `max_tokens` injection.
- `requests` row creation/update.
- Token usage parsing for streaming and non-streaming responses.
- Dynamic model creation after successful unknown-model response.

### Phase 4: Admission Control

- IP get-or-create.
- Dummy CMDB sync call for new IP.
- Permission check using `user_ips`, `departments`, and `whitelist`.
- opencode version check.
- `max_tokens` check.
- Stale processing cleanup.
- Per-IP/model concurrency check.
- Blocked request records.

### Phase 5: CMDB Dummy and Whitelist API

- `CMDBService` dummy implementation.
- `/api/refresh_user_info` endpoint.
- `/api/whitelist/update` endpoint.
- Background refresh thread.

### Phase 6: Operational Hardening

- Client disconnect middleware.
- Per-request log files.
- Management command `init_db`.
- Management command `cleanup_stale_processing`.
- Dockerfile/Gunicorn config.

Stats APIs are not part of these phases. opencode version logic is part of admission/proxy compatibility behavior.

---

## 25. Minimum Viable Router

The minimum useful router should include:

- `/healthy`
- `/v1/<path>` proxy
- Existing DB model mappings
- IP get-or-create
- Dummy CMDB module and call sites
- Permission check
- opencode version check
- Request parser injection
- Request recording
- Streaming proxy
- Non-streaming proxy
- `max_tokens` enforcement
- Concurrency enforcement
- `/api/whitelist/update`
- `/api/refresh_user_info`

Do not implement for MVP:

- Statistics APIs
- Stats SQL queries
- Model admin APIs
- IP admin APIs
- Download API
- Schema migrations that alter existing tables
- Redis concurrency

---

## 26. Key Decisions

| Topic | Decision |
|---|---|
| Database schema | Must remain exactly as required; no redesign |
| CMDB | Keep module/API/call flow, implement dummy no-op now |
| Stats APIs | Remove from this phase |
| opencode version check | Restore existing compatibility behavior from `requirement.md` |
| Framework | Django recommended for compatibility |
| Upstream routing | Single `proxy_url` from YAML for now |
| Unknown IP user info | Allowed when no `user_ips` record exists, matching existing logic |
| Unknown model | Allow within default token limit; create model after success |
| Concurrency | Use existing `requests` table count |
| Request records | Continue writing records for all proxied/blocked requests |
