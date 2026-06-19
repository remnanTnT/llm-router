# API Endpoints

## Health

```http
GET /healthy
```

Returns `200` when the app and database are healthy. Returns `503` when the database check fails.

## Proxy

```http
ANY /v1/<path>
```

All `/v1/*` requests are proxied to an online upstream server. The router preserves the incoming path and query string and appends them to the selected server `base_url`.

Request handling includes:

- client IP creation from `X-Forwarded-For` or `REMOTE_ADDR`
- permission checks through `user_ips`, `departments`, and `whitelist`
- opencode version blocking
- JSON body parsing, `max_tokens` defaulting, and streaming `include_usage` injection
- exact `model: auto` and concrete-model auto routing
- normal-port small-request routing
- VIP-channel eligibility and pool scaling
- retry, circuit breaker, workload accounting, and request lifecycle logging

Example:

```bash
curl -i http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"test-model","messages":[{"role":"user","content":"hi"}]}'
```

Auto-routing example:

```bash
curl -i http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"auto","messages":[{"role":"user","content":"Summarize this design risk"}]}'
```

`GET /v1/models` is special-cased: when no concrete model is present, the router chooses a random online routable server and forwards the request there.

## Load-Balancer Metadata

The default chooser is `PrefixCachePrebleServerChooser`. Before each backend attempt, the router records:

- `requests.target_pod_ip`: selected server `base_url`
- `requests.attempt_count`: attempt number for the client request
- `requests.prefix_cache`: best prefix-cache match ratio found for that attempt
- `requests.last_match`: historical request id that produced the best match, or `NULL`

If `match_ratio > prefix_cache.primary_match_threshold` (`0.9` by default), the chooser picks the least-loaded cached server. If no primary match exists but some server has `match_ratio > prefix_cache.secondary_match_threshold` (`0.5` by default), it picks the least-loaded server from that secondary set. Otherwise it picks the least-loaded candidate overall.

Prefix cache blocks are measured in Unicode characters with `prefix_cache.prefix_block_chars` (`128` by default). Prefix cache metadata is written only after a successful upstream response.

Candidate servers are filtered by model, VIP pool, online state, soft delete, circuit-breaker state, and optional `servers.context_window >= requests.estimate_tokens`.

## Statistics APIs

All time-range statistics endpoints require Beijing-local query parameters:

```text
start_time=YYYY-MM-DD HH:mm:ss
end_time=YYYY-MM-DD HH:mm:ss
```

The range is inclusive. Bucketed endpoints choose granularity automatically: hour for ranges up to 2 days, day for ranges up to 31 days, and month for longer ranges. Internal routing LLM rows (`ip_id = 0`) are excluded from external request statistics.

| Endpoint | Method | Required params | Optional params | Description |
|----------|--------|-----------------|-----------------|-------------|
| `/api/request_stats` | GET | `start_time`, `end_time` | | Distinct requesting IP count. |
| `/api/total_request_count` | GET | `start_time`, `end_time` | | Successful external request count. |
| `/api/input_token` | GET | `start_time`, `end_time` | `model_name`; use `total` or omit for all models | Sum of input tokens. |
| `/api/output_token` | GET | `start_time`, `end_time` | `model_name`; use `total` or omit for all models | Sum of output tokens. |
| `/api/model_request_stats` | GET | `start_time`, `end_time`, `model_name` | | Successful request count for one model. |
| `/api/all_model_request_stats` | GET | `start_time`, `end_time` | `model_name` | Successful request counts grouped by model, or one model when provided. |
| `/api/request_time_stats` | GET | `start_time`, `end_time` | | Average latency series for all models. |
| `/api/model_request_time_stats` | GET | `start_time`, `end_time`, `model_name` | | Average latency series for one model. |
| `/api/model_request_count_by_period` | GET | `start_time`, `end_time`, `model_name` | | Bucketed successful request count for one model. |
| `/api/model_ip_count_by_period` | GET | `start_time`, `end_time`, `model_name` | | Bucketed distinct IP count for one model. |
| `/api/model_latency_boxplot` | GET | `start_time`, `end_time` | `model_names` comma list | Per-model latency boxplot data. Drops latencies above 890 seconds from quartiles and reports their ratio. |

Example:

```bash
curl 'http://localhost:8001/api/model_request_count_by_period?model_name=test-model&start_time=2026-06-01%2000:00:00&end_time=2026-06-02%2023:59:59'
```

## Model Catalog APIs

```http
GET /api/models
GET /api/model_online_list
GET /api/model_info?model_name=<name>
```

`/api/models` returns all model rows with `id`, `model_name`, and `concurrent_limit`.

`/api/model_online_list` returns model names whose `deprecation` is `NULL`.

`/api/model_info` returns `model_name` and `concurrent_limit` for a single model, or `404` when it is not found.

## AI Assistant Download

```http
GET /api/download/ai_assistant
```

Downloads `/home/AI_Assistant/AI_Assistant.exe` as `application/octet-stream`. Returns `404` when the file is missing.

## Whitelist Update

```http
POST /api/whitelist/update
```

Upserts a whitelist entry by `employee_no`.

```bash
curl -i -X POST http://localhost:8001/api/whitelist/update \
  -H 'Content-Type: application/json' \
  -d '{"employee_no":"E001","is_allowed":1}'
```

`is_allowed` must be `0` or `1`.

## Refresh User Info

```http
POST /api/refresh_user_info
```

Starts the CMDB user refresh flow in a background thread. Requires `cmdb.enabled: true`; otherwise returns `403`.

```bash
curl -i -X POST http://localhost:8001/api/refresh_user_info
```

## Add Server

```http
POST /api/add_server
```

Registers one or more upstream servers. The endpoint verifies that `<base_url>/models` advertises the requested `model_name` before persisting the row. `base_url` must end with `/v1`. All operations are logged to `server_operations`.

Single request body:

```json
{
  "base_url": "http://10.1.2.3:8000/v1",
  "model_name": "gpt-3.5-turbo"
}
```

Multiple request body:

```json
[
  {
    "base_url": "http://10.1.2.3:8000/v1",
    "model_name": "gpt-3.5-turbo"
  },
  {
    "base_url": "http://10.1.2.4:8000/v1",
    "model_name": "gpt-3.5-turbo"
  }
]
```

Duplicate `base_url` values within a single request are rejected before any operation row is created. For list payloads, individual items can succeed or fail independently.

## MR Live Review APIs

```http
POST /api/mr_live_review
GET /api/mr_live_review/stats
GET /api/mr_live_review/stats_by_confidence
GET /api/mr_live_review/stats_by_date
GET /api/mr_live_review/list
GET /api/mr_live_review/list_by_confidence
```

`POST /api/mr_live_review` upserts by unique `discussion_id`. If the row exists and `state` is unchanged, the request is skipped. If `state` changes, all provided fields are updated. Payload keys must match `MrLiveReview` model fields except `id`.

Stats endpoints:

- `/api/mr_live_review/stats?project_name=<project>` groups valid, invalid, no-reply counts and accept rate by `target_branch`.
- `/api/mr_live_review/stats_by_confidence?project_name=<project>` groups by `confidence_score`.
- `/api/mr_live_review/stats_by_date` requires `project_name`, `target_branch`, `stats`, `start_date`, and `end_date`. `stats` must be one of `valid`, `invalid`, `no_reply`, `total`, or `accept_rate`. Dates use `YYYY-MM-DD`.

List endpoints:

- `/api/mr_live_review/list` requires `project_name`, `target_branch`, and `type`.
- `/api/mr_live_review/list_by_confidence` requires `project_name` and `type`; `confidence_score` is optional.
- `type` must be `valid`, `invalid`, or `no_reply`.
- `page` defaults to `1`; `page_size` defaults to `10` and must be at most `100`.

## CodeHub Review API

```http
POST /api/codehub_review
```

Creates a CodeHub review row when `issue_hash` is new. If `issue_hash` already exists, the request is skipped. Payload keys must match `CodehubReview` model fields.
