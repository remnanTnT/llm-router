from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
import requests
from django.utils import timezone

from router.models import Model, RequestRecord, Server
from router.repositories.requests import RequestRepository
from router.repositories.servers import ServerRepository
from router.route_algorithm.base import ServerSelectionContext
from router.services.proxy import ProxyService


class _ChooserOnce:
    def __init__(self, server):
        self._server = server

    def choose(self, candidates, context, attempted):
        if self._server.id in attempted:
            return None
        return self._server

    def on_response(self, server, context, status_code):
        return None


def _ctx(record_id: int = 1):
    return ServerSelectionContext(
        request_id=record_id,
        ip_id=None,
        model_id=None,
        model_name="m",
        path="chat/completions",
        method="POST",
        is_stream=False,
        body=b"{}",
    )


def test_increment_and_decrement_workload_are_atomic():
    server = Server.objects.create(base_url="http://w1.example", is_online=True)
    assert server.workload == 0

    ServerRepository.increment_workload(server)
    ServerRepository.increment_workload(server)
    server.refresh_from_db()
    assert server.workload == 2

    ServerRepository.decrement_workload(server)
    server.refresh_from_db()
    assert server.workload == 1


def test_decrement_workload_never_goes_below_zero():
    server = Server.objects.create(base_url="http://w2.example", is_online=True)

    ServerRepository.decrement_workload(server)

    server.refresh_from_db()
    assert server.workload == 0


def _make_upstream(status: int = 200, body: bytes = b"{}"):
    upstream = MagicMock()
    upstream.status_code = status
    upstream.reason = "OK" if status == 200 else "Bad"
    upstream.content = body
    upstream.headers = {}
    return upstream


def test_workload_decremented_after_normal_success(monkeypatch):
    Model.objects.create(model_name="m")
    server = Server.objects.create(model_id=None, base_url="http://norm.example", is_online=True)

    service = ProxyService(chooser=_ChooserOnce(server))

    def fake_request(self_inner, method, url, **kwargs):
        server.refresh_from_db()
        assert server.workload == 1
        return _make_upstream(200, b'{"usage": {"prompt_tokens": 1, "completion_tokens": 2}}')

    monkeypatch.setattr(
        "router.services.cancellable_upstream.CancellableUpstreamRequest.request",
        fake_request,
    )

    django_request = MagicMock()
    django_request.method = "POST"
    django_request.headers = {}
    django_request.META = {"QUERY_STRING": ""}
    django_request.client_disconnect_tracker = None

    parsed = MagicMock(stream=False, body=b"{}", model_name="m")
    service.forward(django_request, "chat/completions", parsed, None, None, None)

    server.refresh_from_db()
    assert server.workload == 0


def test_workload_decremented_after_normal_request_exception(monkeypatch):
    Model.objects.create(model_name="m")
    server = Server.objects.create(model_id=None, base_url="http://normfail.example", is_online=True)

    service = ProxyService(chooser=_ChooserOnce(server))

    def boom(self_inner, method, url, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(
        "router.services.cancellable_upstream.CancellableUpstreamRequest.request",
        boom,
    )

    django_request = MagicMock()
    django_request.method = "POST"
    django_request.headers = {}
    django_request.META = {"QUERY_STRING": ""}
    django_request.client_disconnect_tracker = None

    parsed = MagicMock(stream=False, body=b"{}", model_name="m")
    service.forward(django_request, "chat/completions", parsed, None, None, None)

    server.refresh_from_db()
    assert server.workload == 0


def test_workload_decremented_after_stream_error_response(monkeypatch):
    Model.objects.create(model_name="m")
    server = Server.objects.create(model_id=None, base_url="http://streamerr.example", is_online=True)

    service = ProxyService(chooser=_ChooserOnce(server))

    def fake_request(method, url, **kwargs):
        server.refresh_from_db()
        assert server.workload == 1
        upstream = _make_upstream(400, b'{"error": {"message": "bad"}}')
        return upstream

    monkeypatch.setattr("router.services.proxy._SHARED_SESSION.request", fake_request)

    django_request = MagicMock()
    django_request.method = "POST"
    django_request.headers = {}
    django_request.META = {"QUERY_STRING": ""}
    django_request.client_disconnect_tracker = None

    parsed = MagicMock(stream=True, body=b"{}", model_name="m")
    service.forward(django_request, "chat/completions", parsed, None, None, None)

    server.refresh_from_db()
    assert server.workload == 0


def test_workload_kept_until_stream_generator_completes(monkeypatch):
    Model.objects.create(model_name="m")
    server = Server.objects.create(model_id=None, base_url="http://streamok.example", is_online=True)

    service = ProxyService(chooser=_ChooserOnce(server))

    chunks = [b"data: hello\n\n", b"data: [DONE]\n\n"]

    def fake_request(method, url, **kwargs):
        upstream = MagicMock()
        upstream.status_code = 200
        upstream.reason = "OK"
        upstream.headers = {}
        upstream.iter_content = lambda chunk_size=8192: iter(chunks)
        return upstream

    monkeypatch.setattr("router.services.proxy._SHARED_SESSION.request", fake_request)

    django_request = MagicMock()
    django_request.method = "POST"
    django_request.headers = {}
    django_request.META = {"QUERY_STRING": ""}
    django_request.client_disconnect_tracker = None

    parsed = MagicMock(stream=True, body=b"{}", model_name="m")
    response = service.forward(django_request, "chat/completions", parsed, None, None, None)

    server.refresh_from_db()
    assert server.workload == 1

    list(response.streaming_content)

    server.refresh_from_db()
    assert server.workload == 0


def _make_stale_processing(target_pod_ip: str, model_id: int, minutes_ago: int = 30) -> RequestRecord:
    record = RequestRepository.create_processing(ip_id=1, model_id=model_id, is_stream=False, user_agent="t")
    stale_time = timezone.now() - timedelta(minutes=minutes_ago)
    RequestRecord.objects.filter(id=record.id).update(send_time=stale_time, target_pod_ip=target_pod_ip)
    record.refresh_from_db()
    return record


def test_cleanup_stale_releases_workload_for_stale_targets():
    server_a = Server.objects.create(base_url="http://a.example", is_online=True, workload=3)
    server_b = Server.objects.create(base_url="http://b.example", is_online=True, workload=1)

    _make_stale_processing("http://a.example", model_id=1)
    _make_stale_processing("http://a.example", model_id=1)
    _make_stale_processing("http://b.example", model_id=1)

    updated = RequestRepository.cleanup_stale(threshold_minutes=20)

    assert updated == 3
    server_a.refresh_from_db()
    server_b.refresh_from_db()
    assert server_a.workload == 1
    assert server_b.workload == 0


def test_cleanup_stale_clamps_workload_at_zero_when_counter_already_drained():
    server = Server.objects.create(base_url="http://drained.example", is_online=True, workload=0)
    _make_stale_processing("http://drained.example", model_id=1)
    _make_stale_processing("http://drained.example", model_id=1)

    RequestRepository.cleanup_stale(threshold_minutes=20)

    server.refresh_from_db()
    assert server.workload == 0


def test_cleanup_stale_ignores_records_without_target():
    server = Server.objects.create(base_url="http://t.example", is_online=True, workload=2)
    record = RequestRepository.create_processing(ip_id=1, model_id=1, is_stream=False, user_agent="t")
    RequestRecord.objects.filter(id=record.id).update(
        send_time=timezone.now() - timedelta(minutes=30),
        target_pod_ip=None,
    )

    updated = RequestRepository.cleanup_stale(threshold_minutes=20)

    assert updated == 1
    server.refresh_from_db()
    assert server.workload == 2


def test_cleanup_stale_only_releases_filtered_model():
    server = Server.objects.create(base_url="http://m.example", is_online=True, workload=2)
    _make_stale_processing("http://m.example", model_id=1)
    _make_stale_processing("http://m.example", model_id=2)

    RequestRepository.cleanup_stale(model_id=1, threshold_minutes=20)

    server.refresh_from_db()
    assert server.workload == 1
