from __future__ import annotations

import json
import threading
import time
from urllib.parse import urljoin

from django.http import HttpResponse, StreamingHttpResponse
import requests

from router.config import APP_CONFIG
from router.repositories.models import ModelRepository
from router.repositories.requests import RequestRepository
from router.services.cancellable_upstream import CancellableUpstreamRequest
from router.services.disconnect import DisconnectWatcher
from router.services.opencode import OpencodeVersionService
from router.utils.errors import error_payload, timeout_sse_event
from router.utils.headers import filter_request_headers, filter_response_headers
from router.utils.sse import parse_sse_usage


class ProxyService:
    def __init__(self):
        proxy_config = APP_CONFIG.get("proxy", {})
        self.proxy_url = str(APP_CONFIG.get("proxy_url", "http://localhost:8051")).rstrip("/") + "/"
        self.stream_timeout = (
            float(proxy_config.get("stream_connect_timeout_seconds", 30)),
            float(proxy_config.get("stream_read_timeout_seconds", 900)),
        )
        self.normal_timeout = (
            float(proxy_config.get("normal_connect_timeout_seconds", 5)),
            float(proxy_config.get("normal_read_timeout_seconds", 900)),
        )
        self.stream_total_timeout = float(proxy_config.get("stream_total_timeout_seconds", 900))
        self.client_disconnect_check_interval = float(proxy_config.get("client_disconnect_check_interval_seconds", 0.5))
        self.opencode_400_delay = float(proxy_config.get("opencode_400_delay_seconds", 180))

    def forward(self, django_request, path: str, parsed, ip_id: int | None, model, user_agent: str | None):
        record = RequestRepository.create_processing(ip_id, model.id if model else 0, parsed.stream, user_agent)
        upstream_url = self._build_url(path, django_request.META.get("QUERY_STRING", ""))
        headers = filter_request_headers(dict(django_request.headers), django_request.method)
        if parsed.stream:
            return self._handle_stream(django_request, upstream_url, headers, parsed.body, record, parsed.model_name, user_agent)
        return self._handle_normal(django_request, upstream_url, headers, parsed.body, record, parsed.model_name, user_agent)

    def _build_url(self, path: str, query_string: str) -> str:
        url = urljoin(self.proxy_url, f"v1/{path}")
        if query_string:
            url = f"{url}?{query_string}"
        return url

    def _handle_normal(self, django_request, upstream_url, headers, body, record, model_name, user_agent):
        disconnect_event = threading.Event()
        stop_event = threading.Event()
        upstream_client = CancellableUpstreamRequest()
        watcher = None
        tracker = getattr(django_request, "client_disconnect_tracker", None)
        if tracker:
            watcher = DisconnectWatcher(
                tracker,
                disconnect_event,
                stop_event,
                upstream_client.cancel,
                self.client_disconnect_check_interval,
            )
            watcher.start()

        try:
            upstream = upstream_client.request(
                django_request.method,
                upstream_url,
                headers=headers,
                data=body if django_request.method.upper() not in {"GET", "HEAD"} else None,
                timeout=self.normal_timeout,
            )
            if disconnect_event.is_set():
                return self._client_closed_response(record)

            content = upstream.content
            if disconnect_event.is_set():
                return self._client_closed_response(record)

            self._maybe_delay_opencode_400(user_agent, upstream.status_code)
            input_tokens, output_tokens = self._parse_json_usage(content)
            final_model_id = self._ensure_model_after_success(model_name, upstream.status_code)
            RequestRepository.finish(
                record,
                upstream.status_code,
                upstream.reason or "",
                input_tokens,
                output_tokens,
                upstream.headers.get("target-pod-ip"),
                final_model_id,
            )
            response = HttpResponse(content, status=upstream.status_code)
            for key, value in filter_response_headers(dict(upstream.headers)).items():
                response[key] = value
            return response
        except requests.exceptions.ReadTimeout:
            if disconnect_event.is_set():
                return self._client_closed_response(record)
            RequestRepository.finish(record, 504, "Gateway Timeout")
            return HttpResponse(json.dumps(error_payload("request timeout, please try again later", "gateway_timeout_error")), status=504, content_type="application/json")
        except requests.RequestException:
            if disconnect_event.is_set():
                return self._client_closed_response(record)
            RequestRepository.finish(record, 502, "Bad Gateway")
            return HttpResponse(json.dumps(error_payload("502 Bad Gateway", "server_error")), status=502, content_type="application/json")
        finally:
            stop_event.set()
            upstream_client.close()
            if watcher:
                watcher.join(timeout=0.1)

    def _handle_stream(self, django_request, upstream_url, headers, body, record, model_name, user_agent):
        def generate():
            chunks: list[bytes] = []
            status_code = 502
            reason = "Bad Gateway"
            target_pod_ip = None
            try:
                with requests.request(
                    django_request.method,
                    upstream_url,
                    headers=headers,
                    data=body,
                    stream=True,
                    timeout=self.stream_timeout,
                ) as upstream:
                    status_code = upstream.status_code
                    reason = upstream.reason or ""
                    target_pod_ip = upstream.headers.get("target-pod-ip")
                    self._maybe_delay_opencode_400(user_agent, status_code)
                    deadline = time.monotonic() + self.stream_total_timeout
                    for chunk in upstream.iter_content(chunk_size=8192):
                        if time.monotonic() > deadline:
                            yield timeout_sse_event()
                            RequestRepository.finish(record, 504, "Gateway Timeout")
                            return
                        tracker = getattr(django_request, "client_disconnect_tracker", None)
                        if tracker and tracker.client_disconnected():
                            RequestRepository.finish(record, 499, "Client Closed Request", task_status="agent_disconnected")
                            return
                        if chunk:
                            chunks.append(chunk)
                            yield chunk
            except requests.exceptions.ReadTimeout:
                yield timeout_sse_event()
                RequestRepository.finish(record, 504, "Gateway Timeout")
                return
            except requests.RequestException:
                payload = error_payload("502 Bad Gateway", "server_error")
                yield f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n".encode("utf-8")
                RequestRepository.finish(record, 502, "Bad Gateway")
                return
            input_tokens, output_tokens = parse_sse_usage(chunks)
            final_model_id = self._ensure_model_after_success(model_name, status_code)
            RequestRepository.finish(record, status_code, reason, input_tokens, output_tokens, target_pod_ip, final_model_id)

        response = StreamingHttpResponse(generate(), status=200, content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    @staticmethod
    def _client_closed_response(record):
        RequestRepository.finish(record, 499, "Client Closed Request", task_status="agent_disconnected")
        return HttpResponse(status=499)

    def _maybe_delay_opencode_400(self, user_agent: str | None, status_code: int) -> None:
        if self.opencode_400_delay > 0 and OpencodeVersionService.should_delay_upstream_400(user_agent, status_code):
            time.sleep(self.opencode_400_delay)

    @staticmethod
    def _parse_json_usage(content: bytes) -> tuple[int, int]:
        try:
            data = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 0, 0
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return 0, 0
        return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)

    @staticmethod
    def _ensure_model_after_success(model_name: str | None, status_code: int) -> int | None:
        if model_name and 200 <= status_code < 300:
            model, _ = ModelRepository.get_or_create(model_name)
            return model.id
        return None
