from __future__ import annotations

import json
from dataclasses import dataclass

from router.route_algorithm.base import ServerSelectionContext
from router.route_algorithm.least_connection import LeastConnectionServerChooser
from router.route_algorithm.prefix_cache_preble import PrefixCachePrebleServerChooser


@dataclass
class Server:
    id: int
    base_url: str
    model_id: int | None = None
    cache_time: int = 3600


def make_server(server_id, base_url, cache_time=3600):
    return Server(id=server_id, base_url=base_url, cache_time=cache_time)


def make_context(body: bytes = b"{}"):
    return ServerSelectionContext(
        request_id=1,
        ip_id=None,
        model_id=None,
        model_name="test-model",
        path="chat/completions",
        method="POST",
        is_stream=False,
        body=body,
    )


def make_body(words):
    return json.dumps({"messages": [{"role": "user", "content": " ".join(words)}]}).encode("utf-8")


def test_least_connection_chooser_selects_server_with_fewest_processing_requests():
    chooser = LeastConnectionServerChooser(lambda targets: {"http://10.0.0.1:8000": 3, "http://10.0.0.2:8000": 1})
    candidates = [make_server(1, "http://10.0.0.1:8000"), make_server(2, "http://10.0.0.2:8000")]

    selected = chooser.choose(candidates, make_context(), set())

    assert selected.id == 2


def test_least_connection_chooser_skips_attempted_servers():
    chooser = LeastConnectionServerChooser(lambda targets: {"http://10.0.0.1:8000": 0, "http://10.0.0.2:8000": 1})
    candidates = [make_server(1, "http://10.0.0.1:8000"), make_server(2, "http://10.0.0.2:8000")]

    selected = chooser.choose(candidates, make_context(), {1})

    assert selected.id == 2


def test_least_connection_chooser_returns_none_when_all_attempted():
    chooser = LeastConnectionServerChooser(lambda targets: {})
    candidates = [make_server(1, "http://10.0.0.1:8000"), make_server(2, "http://10.0.0.2:8000")]

    assert chooser.choose(candidates, make_context(), {1, 2}) is None


def test_prefix_cache_high_match_chooses_least_loaded_cached_server():
    PrefixCachePrebleServerChooser._prefix_cache = {}
    chooser = PrefixCachePrebleServerChooser(
        lambda targets: {"http://10.0.0.1:8000": 3, "http://10.0.0.2:8000": 1, "http://10.0.0.3:8000": 0}
    )
    candidates = [
        make_server(1, "http://10.0.0.1:8000"),
        make_server(2, "http://10.0.0.2:8000"),
        make_server(3, "http://10.0.0.3:8000"),
    ]
    cached_body = make_body([str(i) for i in range(100)])
    chooser.on_response(candidates[0], make_context(cached_body), 200)
    chooser.on_response(candidates[1], make_context(cached_body), 200)

    selected = chooser.choose(candidates, make_context(make_body([str(i) for i in range(99)] + ["new"])), set())

    assert selected.id == 2


def test_prefix_cache_medium_match_chooses_least_loaded_overall_server():
    PrefixCachePrebleServerChooser._prefix_cache = {}
    chooser = PrefixCachePrebleServerChooser(
        lambda targets: {"http://10.0.0.1:8000": 0, "http://10.0.0.2:8000": 1, "http://10.0.0.3:8000": 0}
    )
    candidates = [
        make_server(1, "http://10.0.0.1:8000"),
        make_server(2, "http://10.0.0.2:8000"),
        make_server(3, "http://10.0.0.3:8000"),
    ]
    chooser.on_response(candidates[1], make_context(make_body([str(i) for i in range(60)])), 200)

    selected = chooser.choose(candidates, make_context(make_body([str(i) for i in range(60)] + [f"new-{i}" for i in range(40)])), set())

    assert selected.id == 1


def test_prefix_cache_response_hook_only_marks_successful_responses():
    PrefixCachePrebleServerChooser._prefix_cache = {}
    chooser = PrefixCachePrebleServerChooser(lambda targets: {})
    server = make_server(1, "http://10.0.0.1:8000")
    context = make_context(make_body(["hello", "world"]))

    chooser.on_response(server, context, 500)

    assert PrefixCachePrebleServerChooser._prefix_cache == {}

    chooser.on_response(server, context, 200)

    assert PrefixCachePrebleServerChooser._prefix_cache


def test_prefix_cache_max_prefix_tokens_is_at_least_100k():
    chooser = PrefixCachePrebleServerChooser(lambda targets: {}, max_prefix_tokens=10)

    assert chooser.max_prefix_tokens >= 100000


def test_prefix_cache_uses_renamed_threshold_arguments():
    chooser = PrefixCachePrebleServerChooser(
        lambda targets: {},
        primary_match_threshold=0.91,
        secondary_match_threshold=0.41,
    )

    assert chooser.primary_match_threshold == 0.91
    assert chooser.secondary_match_threshold == 0.41
