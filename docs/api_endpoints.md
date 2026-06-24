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

Prefix cache blocks are measured in Unicode characters with `prefix_cache.prefix_block_chars` (`8` by default). Prefix cache metadata is written only after a successful upstream response.

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

Creates a CodeHub review row. Payload keys must match `CodehubReview` model fields.

## Daily MR Review API

```http
POST /api/daily_mr_review
```

Creates a daily MR review row when `issue_hash` is new. If `issue_hash` already exists, the request is skipped and returns success without modification.

Required fields:

- `project_id`: Project identifier
- `branch`: Target branch name
- `issue_hash`: Unique issue identifier computed from content and location
- `mr_hash`: Merge request identifier
- `file_path`: File path where the issue was found
- `line`: Line number
- `body`: Issue body or code snippet
- `review_comment`: AI-generated review comment
- `severity`: Issue severity level
- `categories`: Issue category labels
- `fix_suggestion`: Suggested fix
- `created_at`: Timestamp string when the issue was created
- `confidence_score`: Review confidence level
- `issue_url`: URL to the issue

Example:

```bash
curl -i -X POST http://localhost:8001/api/daily_mr_review \
  -H 'Content-Type: application/json' \
  -d '{
    "project_id": 123,
    "branch": "main",
    "issue_hash": "abc123def456",
    "mr_hash": "mr789",
    "file_path": "src/utils.py",
    "line": 42,
    "body": "def calculate(): return x / y",
    "review_comment": "Potential division by zero",
    "severity": "high",
    "categories": "bug,safety",
    "fix_suggestion": "Add zero check before division",
    "created_at": "2026-06-25 10:00:00",
    "confidence_score": "0.95",
    "issue_url": "https://gitlab.example.com/issues/123"
  }'
```

## Live Review Request API

```http
POST /api/live_review_requests
```

Creates a live review request record to track MR review sessions. Model ID fields accept either integer model IDs or model name strings, which are automatically resolved to IDs. `duration_seconds` is automatically calculated from `start_time` and `end_time` when both are provided.

Required fields:

- `project_name`: Project name
- `merge_requests_id`: Merge request ID
- `merge_url`: URL to the merge request
- `start_time`: Review start time (format: `YYYY-MM-DD HH:mm:ss`)

Optional fields:

- `end_time`: Review end time (format: `YYYY-MM-DD HH:mm:ss`)
- `expert_model_id`: Model ID or name used in expert review phase
- `reflect_model_id`: Model ID or name used in reflection phase
- `review_file_num`: Number of files reviewed (default: `0`)
- `diff_part_num`: Number of diff parts analyzed (default: `0`)
- `review_num`: Number of review comments generated (default: `0`)

Example with model names:

```bash
curl -i -X POST http://localhost:8001/api/live_review_requests \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name": "llm-router",
    "merge_requests_id": 456,
    "merge_url": "https://gitlab.example.com/project/llm-router/-/merge_requests/456",
    "start_time": "2026-06-25 09:00:00",
    "end_time": "2026-06-25 09:15:00",
    "expert_model_id": "gpt-4",
    "reflect_model_id": "claude-3-opus",
    "review_file_num": 5,
    "diff_part_num": 12,
    "review_num": 8
  }'
```

Example with model IDs:

```bash
curl -i -X POST http://localhost:8001/api/live_review_requests \
  -H 'Content-Type: application/json' \
  -d '{
    "project_name": "llm-router",
    "merge_requests_id": 457,
    "merge_url": "https://gitlab.example.com/project/llm-router/-/merge_requests/457",
    "start_time": "2026-06-25 10:00:00",
    "expert_model_id": 1,
    "reflect_model_id": 2
  }'
```

## Concurrent Multiplier Update API

```http
POST /api/concurrent_multiplier/update
```

Updates the `concurrent_multiplier` field for an IP address. Requires either `employee_no` or `ip` (not both), and `concurrent_multiplier` (must be >= 1.0).

```bash
curl -i -X POST http://localhost:8001/api/concurrent_multiplier/update \
  -H 'Content-Type: application/json' \
  -d '{"employee_no":"E001","concurrent_multiplier":2.0}'
```

Or by IP:

```bash
curl -i -X POST http://localhost:8001/api/concurrent_multiplier/update \
  -H 'Content-Type: application/json' \
  -d '{"ip":"192.168.1.100","concurrent_multiplier":1.5}'
```

## AI Assistant User Feedback API

```http
POST /api/ai_assistant_user_feedback
```

Creates an AI Assistant user feedback record. Required fields: `domain` (one of: 知识管理, 辅助设计, 代码分析, 问题定位, Agent), `issue_description`, `reporter`, `reported_at`, `status` (one of: open, close, cancel). Optional fields include `tool_version`, `priority` (高/中/低), `assignee`, `estimated_resolution_at`, `actual_resolution_at`, `bugfix_version`, `progress_tracking`, and `remarks`.

```bash
curl -i -X POST http://localhost:8001/api/ai_assistant_user_feedback \
  -H 'Content-Type: application/json' \
  -d '{
    "domain": "代码分析",
    "issue_description": "代码分析功能响应缓慢",
    "reporter": "张三",
    "reported_at": "2026-06-25 10:00:00",
    "status": "open",
    "priority": "高"
  }'
```
