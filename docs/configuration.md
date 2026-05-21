# Configuration

Default configuration is in `config.yaml`. Values are deep-merged onto built-in defaults in `router/config.py`.

## `config.yaml`

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

load_balancer:
  enabled: true
  max_attempts_per_request: 3
  retry_status_codes: [502, 503, 504]
  mark_unhealthy_status_codes: [502, 503, 504]
  health_check_timeout_seconds: 2
  chooser_class: router.route_algorithm.prefix_cache_preble.PrefixCachePrebleServerChooser

prefix_cache:
  primary_match_threshold: 0.9
  secondary_match_threshold: 0.5
  max_prefix_tokens: 100000

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

Point the router to another config file with:

```bash
export LLM_ROUTER_CONFIG=/path/to/config.yaml
```

## Environment Variables

Database values can be overridden with environment variables:

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
export PREFIX_CACHE_PRIMARY_MATCH_THRESHOLD=0.9
export PREFIX_CACHE_SECONDARY_MATCH_THRESHOLD=0.5
export USE_SQLITE_FOR_TESTS=1
```
