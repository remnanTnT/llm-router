from __future__ import annotations

import importlib
import json
import threading
import time
from urllib.parse import urljoin

from django.http import HttpResponse, StreamingHttpResponse
import requests

from router.config import APP_CONFIG
from router.repositories.models import ModelRepository
from router.repositories.requests import RequestRepository
from router.repositories.servers import ServerRepository
from router.services.cancellable_upstream import CancellableUpstreamRequest
from router.services.disconnect import DisconnectWatcher
from router.services.opencode import OpencodeVersionService
from router.services.request_logger import append_request_log
from router.services.server_chooser import LeastConnectionServerChooser, ServerSelectionContext
from router.utils.errors import error_payload, timeout_sse_event
from router.utils.headers import filter_request_headers, filter_response_headers
from router.utils.sse import parse_sse_usage


class ProxyService:
    def __init__(self, chooser=None):
        proxy_config = APP_CONFIG.get("proxy", {})
        lb_config = APP_CONFIG.get("load_balancer", {})
        self.proxy_url = str(APP_CONFIG.get("proxy_url", "http://localhost:8051")).rstrip("/") + "/"
        self.load_balancer_enabled = bool(lb_config.get("enabled", True))
        self.max_attempts_per_request = int(lb_config.get("max_attempts_per_request", 3))
        self.retry_status_codes = {int(code) for code in lb_config.get("retry_status_codes", [502, 503, 504])}
        self.mark_unhealthy_status_codes = {int(code) for code in lb_config.get("mark_unhealthy_status_codes", [502, 503, 504])}
        self.chooser = chooser or self._load_chooser(str(lb_config.get("chooser_class", "router.services.server_chooser.LeastConnectionServerChooser")))
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
        headers = filter_request_headers(dict(django_request.headers), django_request.method)
        model_id = model.id if model else None
        context = ServerSelectionContext(
            request_id=record.id,
            ip_id=ip_id,
            model_id=model_id,
            model_name=parsed.model_name,
            path=path,
            method=django_request.method,
            is_stream=parsed.stream,
            body=parsed.body,
        )
        if self.load_balancer_enabled:
            candidates = ServerRepository.list_by_model_id(model_id)
            if not candidates:
                RequestRepository.finish(record, 503, "Service Unavailable")
                return HttpResponse(
                    json.dumps(error_payload("no online upstream server available", "service_unavailable")),
                    status=503,
                    content_type="application/json",
                )
        else:
            candidates = [self._legacy_server()]

        if parsed.stream:
            return self._handle_stream(django_request, path, headers, parsed.body, record, parsed.model_name, user_agent, candidates, context)
        return self._handle_normal(django_request, path, headers, parsed.body, record, parsed.model_name, user_agent, candidates, context)

    def _build_url(self, base_url: str, path: str, query_string: str) -> str:
        url = urljoin(base_url.rstrip("/") + "/", f"v1/{path}")
        if query_string:
            url = f"{url}?{query_string}"
        return url

    def _handle_normal(self, django_request, path, headers, body, record, model_name, user_agent, candidates, context):
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

        attempted_server_ids: set[int] = set()
        attempts = 0
        last_server = None
        last_status = 502
        last_reason = "Bad Gateway"
        try:
            while attempts < min(self.max_attempts_per_request, len(candidates)):
                server = self.chooser.choose(candidates, context, attempted_server_ids)
                if server is None:
                    break
                last_server = server
                attempted_server_ids.add(server.id)
                attempts += 1
                upstream_url = self._build_url(server.base_url, path, django_request.META.get("QUERY_STRING", ""))
                target_pod_ip = self._target_identifier(server)
                RequestRepository.record_attempt(record, target_pod_ip, attempts)
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

                    last_status = upstream.status_code
                    last_reason = upstream.reason or ""
                    retry = upstream.status_code in self.retry_status_codes and attempts < min(self.max_attempts_per_request, len(candidates))
                    self._log_attempt(record.id, attempts, server, "status", retry, status=upstream.status_code)
                    if upstream.status_code in self.mark_unhealthy_status_codes:
                        self._mark_unhealthy(server)
                    if retry:
                        upstream.close()
                        continue

                    self._maybe_log_multi_server_route(record.id, attempted_server_ids, server.id)
                    self._maybe_delay_opencode_400(user_agent, upstream.status_code)
                    input_tokens, output_tokens = self._parse_json_usage(content)
                    final_model_id = self._ensure_model_after_success(model_name, upstream.status_code)
                    RequestRepository.finish(
                        record,
                        upstream.status_code,
                        upstream.reason or "",
                        input_tokens,
                        output_tokens,
                        target_pod_ip,
                        final_model_id,
                        attempt_count=attempts,
                    )
                    response = HttpResponse(content, status=upstream.status_code)
                    for key, value in filter_response_headers(dict(upstream.headers)).items():
                        response[key] = value
                    return response
                except requests.exceptions.ReadTimeout:
                    if disconnect_event.is_set():
                        return self._client_closed_response(record)
                    last_status = 504
                    last_reason = "Gateway Timeout"
                    self._mark_unhealthy(server)
                    self._log_attempt(record.id, attempts, server, "read_timeout", False, reason="ReadTimeout")
                    break
                except requests.RequestException as exc:
                    if disconnect_event.is_set():
                        return self._client_closed_response(record)
                    last_status = 502
                    last_reason = "Bad Gateway"
                    retry = attempts < min(self.max_attempts_per_request, len(candidates))
                    self._mark_unhealthy(server)
                    self._log_attempt(record.id, attempts, server, exc.__class__.__name__, retry, reason=str(exc))
                    if retry:
                        continue
                    break

            self._maybe_log_multi_server_route(record.id, attempted_server_ids, last_server.id if last_server else None)
            RequestRepository.finish(record, last_status, last_reason, target_pod_ip=self._target_identifier(last_server) if last_server else None, attempt_count=attempts)
            status = 504 if last_status == 504 else 502
            message = "request timeout, please try again later" if status == 504 else "502 Bad Gateway"
            error_type = "gateway_timeout_error" if status == 504 else "server_error"
            return HttpResponse(json.dumps(error_payload(message, error_type)), status=status, content_type="application/json")
        finally:
            stop_event.set()
            upstream_client.close()
            if watcher:
                watcher.join(timeout=0.1)

    def _handle_stream(self, django_request, path, headers, body, record, model_name, user_agent, candidates, context):
        def generate():
            chunks: list[bytes] = []
            status_code = 502
            reason = "Bad Gateway"
            target_pod_ip = None
            attempted_server_ids: set[int] = set()
            attempts = 0
            last_server = None
            yielded = False
            while attempts < min(self.max_attempts_per_request, len(candidates)):
                server = self.chooser.choose(candidates, context, attempted_server_ids)
                if server is None:
                    break
                last_server = server
                attempted_server_ids.add(server.id)
                attempts += 1
                upstream_url = self._build_url(server.base_url, path, django_request.META.get("QUERY_STRING", ""))
                target_pod_ip = self._target_identifier(server)
                RequestRepository.record_attempt(record, target_pod_ip, attempts)
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
                        target_pod_ip = self._target_identifier(server)
                        retry = status_code in self.retry_status_codes and attempts < min(self.max_attempts_per_request, len(candidates))
                        self._log_attempt(record.id, attempts, server, "status", retry, status=status_code)
                        if status_code in self.mark_unhealthy_status_codes:
                            self._mark_unhealthy(server)
                        if retry:
                            continue
                        self._maybe_log_multi_server_route(record.id, attempted_server_ids, server.id)
                        self._maybe_delay_opencode_400(user_agent, status_code)
                        deadline = time.monotonic() + self.stream_total_timeout
                        for chunk in upstream.iter_content(chunk_size=8192):
                            if time.monotonic() > deadline:
                                yield timeout_sse_event()
                                RequestRepository.finish(record, 504, "Gateway Timeout", target_pod_ip=target_pod_ip, attempt_count=attempts)
                                return
                            tracker = getattr(django_request, "client_disconnect_tracker", None)
                            if tracker and tracker.client_disconnected():
                                RequestRepository.finish(record, 499, "Client Closed Request", target_pod_ip=target_pod_ip, task_status="agent_disconnected", attempt_count=attempts)
                                return
                            if chunk:
                                yielded = True
                                chunks.append(chunk)
                                yield chunk
                        input_tokens, output_tokens = parse_sse_usage(chunks)
                        final_model_id = self._ensure_model_after_success(model_name, status_code)
                        RequestRepository.finish(record, status_code, reason, input_tokens, output_tokens, target_pod_ip, final_model_id, attempt_count=attempts)
                        return
                except requests.exceptions.ReadTimeout:
                    if not yielded and attempts < min(self.max_attempts_per_request, len(candidates)):
                        self._mark_unhealthy(server)
                        self._log_attempt(record.id, attempts, server, "read_timeout", True, reason="ReadTimeout")
                        continue
                    yield timeout_sse_event()
                    self._mark_unhealthy(server)
                    RequestRepository.finish(record, 504, "Gateway Timeout", target_pod_ip=self._target_identifier(server), attempt_count=attempts)
                    return
                except requests.RequestException as exc:
                    if not yielded and attempts < min(self.max_attempts_per_request, len(candidates)):
                        self._mark_unhealthy(server)
                        self._log_attempt(record.id, attempts, server, exc.__class__.__name__, True, reason=str(exc))
                        continue
                    payload = error_payload("502 Bad Gateway", "server_error")
                    yield f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n".encode("utf-8")
                    self._mark_unhealthy(server)
                    RequestRepository.finish(record, 502, "Bad Gateway", target_pod_ip=self._target_identifier(server), attempt_count=attempts)
                    return

            self._maybe_log_multi_server_route(record.id, attempted_server_ids, last_server.id if last_server else None)
            payload = error_payload("502 Bad Gateway", "server_error")
            yield f"data: {json.dumps(payload)}\n\ndata: [DONE]\n\n".encode("utf-8")
            RequestRepository.finish(record, status_code, reason, target_pod_ip=self._target_identifier(last_server) if last_server else None, attempt_count=attempts)

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

    @staticmethod
    def _load_chooser(path: str):
        try:
            module_name, class_name = path.rsplit(".", 1)
            chooser_class = getattr(importlib.import_module(module_name), class_name)
            return chooser_class()
        except (ImportError, AttributeError, ValueError, TypeError):
            return LeastConnectionServerChooser()

    @staticmethod
    def _legacy_server():
        class LegacyServer:
            id = 0
            model_id = None
            base_url = str(APP_CONFIG.get("proxy_url", "http://localhost:8051"))

        return LegacyServer()

    @staticmethod
    def _mark_unhealthy(server) -> None:
        if server.id != 0:
            ServerRepository.mark_unhealthy(server)

    @staticmethod
    def _target_identifier(server) -> str | None:
        if not server:
            return None
        return server.base_url[:500]

    @staticmethod
    def _log_attempt(request_id: int, attempt: int, server, result: str, retry: bool, status: int | None = None, reason: str | None = None) -> None:
        payload = {
            "event": "server_attempt",
            "request_id": request_id,
            "attempt": attempt,
            "server_id": server.id,
            "base_url": server.base_url,
            "model_id": server.model_id,
            "result": result,
            "retry": retry,
        }
        if status is not None:
            payload["status"] = status
        if reason:
            payload["reason"] = reason[:500]
        append_request_log(request_id, json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _maybe_log_multi_server_route(request_id: int, attempted_server_ids: set[int], final_server_id: int | None) -> None:
        if len(attempted_server_ids) <= 1:
            return
        payload = {
            "event": "multi_server_route",
            "request_id": request_id,
            "server_ids": sorted(attempted_server_ids),
            "final_server_id": final_server_id,
            "reason": "retried_after_failure",
        }
        append_request_log(request_id, json.dumps(payload, ensure_ascii=False))
