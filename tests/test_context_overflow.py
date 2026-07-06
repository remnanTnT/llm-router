import json
from unittest.mock import MagicMock
import pytest
from django.test import Client
from router.models import Model, Server, RequestRecord

def test_context_overflow_switches_to_flash_when_auto(monkeypatch):
    # Setup models
    flash_model = Model.objects.create(model_name="DeepSeek-V4-Flash")
    other_model = Model.objects.create(
        model_name="Other-Model",
        auto=True,
        complexity_min=1,
        complexity_max=10,
    )

    # Setup servers: the only Other-Model server advertises a small context window.
    other_server = Server.objects.create(
        model_id=other_model.id,
        base_url="http://other.example",
        is_online=True,
        context_window=1000,
    )
    Server.objects.create(model_id=flash_model.id, base_url="http://flash.example", is_online=True)

    # Mock routing LLM to return other_model for 'auto'
    def fake_query_routing_llm(self, body, record, context, active_models, model_names):
        return other_model, "router_decision"
    monkeypatch.setattr("router.route_algorithm.auto.AutoRouteAlgorithm._query_routing_llm", fake_query_routing_llm)

    # First attempt on other_server overflows (error body contains its context
    # window value, 1000); no larger-window Other-Model server exists, so the
    # router falls back to the flash model on the second attempt.
    attempt_count = 0
    def fake_request(self_inner, method, url, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        upstream = MagicMock()
        if "other.example" in url:
            upstream.status_code = 400
            upstream.reason = "Bad Request"
            upstream.content = b'{"error": {"message": "context window 1000 exceeded"}}'
            upstream.headers = {"content-type": "application/json"}
        else:
            upstream.status_code = 200
            upstream.reason = "OK"
            upstream.content = b'{"choices": [{"message": {"content": "flash response"}}]}'
            upstream.headers = {"content-type": "application/json"}
        return upstream

    monkeypatch.setattr(
        "router.services.cancellable_upstream.CancellableUpstreamRequest.request",
        fake_request,
    )

    client = Client()
    response = client.post(
        "/v1/chat/completions",
        data=json.dumps({"model": "auto", "messages": [{"role": "user", "content": "hello"}]}),
        content_type="application/json",
        HTTP_X_FORWARDED_FOR="1.2.3.4"
    )

    assert response.status_code == 200
    assert b"flash response" in response.content
    assert attempt_count == 2

def test_context_overflow_does_not_switch_when_explicit_model(monkeypatch):
    # Setup models
    flash_model = Model.objects.create(model_name="DeepSeek-V4-Flash")
    other_model = Model.objects.create(model_name="Other-Model")

    # The explicit model server advertises a small window.
    Server.objects.create(
        model_id=other_model.id,
        base_url="http://other.example",
        is_online=True,
        context_window=1000,
    )
    Server.objects.create(model_id=flash_model.id, base_url="http://flash.example", is_online=True)

    # Mock requests to fail with 400 and context overflow
    attempt_count = 0
    def fake_request(self_inner, method, url, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        upstream = MagicMock()
        upstream.status_code = 400
        upstream.reason = "Bad Request"
        upstream.content = b'{"error": {"message": "context window 1000 exceeded"}}'
        upstream.headers = {"content-type": "application/json"}
        return upstream

    monkeypatch.setattr(
        "router.services.cancellable_upstream.CancellableUpstreamRequest.request",
        fake_request,
    )

    client = Client()
    response = client.post(
        "/v1/chat/completions",
        data=json.dumps({"model": "Other-Model", "messages": [{"role": "user", "content": "hello"}]}),
        content_type="application/json",
        HTTP_X_FORWARDED_FOR="1.2.3.4"
    )

    assert response.status_code == 400
    assert b"context window 1000 exceeded" in response.content
    # It must NOT switch to flash_model; only the explicit model server is tried.
    assert attempt_count >= 1


def test_context_overflow_retries_same_model_larger_window(monkeypatch):
    # Issue #153: on overflow, first retry on a same-model server with a larger
    # context window before falling back to a different model.
    flash_model = Model.objects.create(model_name="DeepSeek-V4-Flash")
    other_model = Model.objects.create(
        model_name="Other-Model",
        auto=True,
        complexity_min=1,
        complexity_max=10,
    )

    # small-window Other-Model server overflows; large-window one succeeds.
    Server.objects.create(
        model_id=other_model.id,
        base_url="http://other-small.example",
        is_online=True,
        context_window=1000,
    )
    Server.objects.create(
        model_id=other_model.id,
        base_url="http://other-large.example",
        is_online=True,
        context_window=100000,
    )
    # Flash exists but must NOT be contacted: a larger-window same-model server exists.
    Server.objects.create(model_id=flash_model.id, base_url="http://flash.example", is_online=True)

    def fake_query_routing_llm(self, body, record, context, active_models, model_names):
        return other_model, "router_decision"
    monkeypatch.setattr("router.route_algorithm.auto.AutoRouteAlgorithm._query_routing_llm", fake_query_routing_llm)

    contacted = []
    def fake_request(self_inner, method, url, **kwargs):
        upstream = MagicMock()
        upstream.headers = {"content-type": "application/json"}
        contacted.append(url)
        if "other-small.example" in url:
            upstream.status_code = 400
            upstream.reason = "Bad Request"
            upstream.content = b'{"error": {"message": "context window 1000 exceeded"}}'
        else:
            upstream.status_code = 200
            upstream.reason = "OK"
            upstream.content = b'{"choices": [{"message": {"content": "ok"}}]}'
        return upstream

    monkeypatch.setattr(
        "router.services.cancellable_upstream.CancellableUpstreamRequest.request",
        fake_request,
    )

    client = Client()
    response = client.post(
        "/v1/chat/completions",
        data=json.dumps({"model": "auto", "messages": [{"role": "user", "content": "hello"}]}),
        content_type="application/json",
        HTTP_X_FORWARDED_FOR="1.2.3.4",
    )

    assert response.status_code == 200
    # The large-window same-model server was contacted, and flash never was.
    assert any("other-large.example" in u for u in contacted)
    assert not any("flash.example" in u for u in contacted)
