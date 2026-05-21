# Tests

Run the full test suite:

```bash
python -m pytest tests
```

Tests use SQLite when `USE_SQLITE_FOR_TESTS=1` (see `tests/conftest.py`).

## Test Files

| File | Coverage |
|------|----------|
| `test_api_download.py` | `/api/download/ai_assistant` success and 404 paths |
| `test_api_stats.py` | All `/api/*_stats` endpoints, hour/day/month bucketing, boxplot edge cases |
| `test_cancellable_upstream.py` | `CancellableUpstreamRequest.cancel()` shuts down in-flight HTTP via socket close |
| `test_check_db_schema.py` | `check_db_schema` drift detection and `--fix` on PostgreSQL |
| `test_circuit_breaker.py` | Failure counting, threshold, open/half_open transitions, exponential cooldown |
| `test_config.py` | `PREFIX_CACHE_*` env overrides applied by `load_config` |
| `test_disconnect.py` | `DisconnectWatcher` event/callback semantics |
| `test_errors.py` | Error payload shape and SSE timeout event format |
| `test_headers.py` | Request-header filtering (hop-by-hop + bodyless `Content-Type`) |
| `test_management_api.py` | Whitelist upsert messages and `refresh_user_info` thread launch |
| `test_manage.py` | `manage.py prod`/`test` argument parsing and DB port selection |
| `test_opencode.py` | Opencode UA blocking and 400-delay version comparisons |
| `test_parser.py` | JSON body rewriting (stream_options, default max_tokens, non-JSON passthrough) |
| `test_proxy.py` | `GET /v1/models` random-online routing and other proxy paths |
| `test_request_logger.py` | Per-request log file append and relative-path resolution |
| `test_requests_repository.py` | `record_attempt` persists `prefix_cache` / `last_match` |
| `test_server_chooser.py` | Least-connection and prefix-cache-Preble chooser selection logic |
| `test_sse.py` | `parse_sse_usage` extracts the last `usage` block from SSE |
| `test_workload.py` | `servers.workload` increment/decrement and stale cleanup decrements |
