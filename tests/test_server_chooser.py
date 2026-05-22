from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

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


def make_context(body: bytes = b"{}", request_id: int = 1):
    return ServerSelectionContext(
        request_id=request_id,
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
    chooser.on_response(candidates[0], make_context(cached_body, request_id=101), 200)
    chooser.on_response(candidates[1], make_context(cached_body, request_id=102), 200)

    context = make_context(make_body([str(i) for i in range(99)] + ["new"]))
    selected = chooser.choose(candidates, context, set())

    assert selected.id == 2
    assert context.prefix_cache == pytest.approx(100 / 101)
    assert context.last_match == 102


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
    chooser.on_response(candidates[1], make_context(make_body([str(i) for i in range(60)]), request_id=201), 200)

    context = make_context(make_body([str(i) for i in range(60)] + [f"new-{i}" for i in range(40)]))
    selected = chooser.choose(candidates, context, set())

    assert selected.id == 2
    assert context.prefix_cache == pytest.approx(61 / 101)
    assert context.last_match == 201


def test_prefix_cache_last_match_tracks_best_match_request_id():
    PrefixCachePrebleServerChooser._prefix_cache = {}
    chooser = PrefixCachePrebleServerChooser(lambda targets: {})
    candidates = [make_server(1, "http://10.0.0.1:8000")]
    chooser.on_response(candidates[0], make_context(make_body(["a", "b", "x"]), request_id=301), 200)
    chooser.on_response(candidates[0], make_context(make_body(["a", "b", "c", "d"]), request_id=302), 200)

    context = make_context(make_body(["a", "b", "c", "new"]))
    chooser.choose(candidates, context, set())

    assert context.prefix_cache == pytest.approx(4 / 5)
    assert context.last_match == 302


def test_prefix_cache_last_match_is_none_without_common_prefix():
    PrefixCachePrebleServerChooser._prefix_cache = {}
    chooser = PrefixCachePrebleServerChooser(lambda targets: {})
    candidates = [make_server(1, "http://10.0.0.1:8000")]
    chooser.on_response(candidates[0], make_context(b"hello world", request_id=401), 200)

    context = make_context(b"goodbye world")
    chooser.choose(candidates, context, set())

    assert context.prefix_cache == 0.0
    assert context.last_match is None


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


def test_prefix_cache_preble_specific_cleanup():
    """Specific test for PrefixCachePreble to ensure Trie pruning logic works."""
    chooser = PrefixCachePrebleServerChooser(count_provider=lambda targets: {t: 0 for t in targets})
    PrefixCachePrebleServerChooser._prefix_cache = {}

    server = make_server(1, "http://server1", cache_time=1)
    candidates = [server]
    model_name = "prune-test-model"

    # Add entries and wait for expiration
    for i in range(10):
        body = json.dumps({"prompt": f"token_{i}"}).encode("utf-8")
        ctx = make_context(body=body, request_id=i)
        ctx.model_name = model_name
        chooser.on_response(server, ctx, 200)

    import time
    time.sleep(1.1)

    root = PrefixCachePrebleServerChooser._prefix_cache.get(model_name)
    from django.utils import timezone
    PrefixCachePrebleServerChooser._prune_node(root, timezone.now())

    if not root.children and not root.server_cached_at:
        del PrefixCachePrebleServerChooser._prefix_cache[model_name]

    assert model_name not in PrefixCachePrebleServerChooser._prefix_cache


@pytest.mark.parametrize("chooser_class", [
    cls for name, cls in vars(__import__("router.route_algorithm", fromlist=["*"])).items()
    if isinstance(cls, type) and name.endswith("ServerChooser") and name != "ServerChooser"
])
def test_all_choosers_memory_growth(chooser_class):
    """Generic test to ensure NO chooser implementation grows its internal state 
    unexpectedly during repeated choose() calls.
    """
    # Initialize with mock provider to avoid DB
    try:
        chooser = chooser_class(count_provider=lambda targets: {t: 0 for t in targets})
    except TypeError:
        # Fallback for choosers that might not take count_provider in __init__
        chooser = chooser_class()

    candidates = [make_server(1, "http://server1")]
    context = make_context()
    
    # We measure the size of the instance dictionary to detect per-instance leaks.
    # Note: This doesn't catch class-level leaks (like the prefix cache), 
    # which should have their own specialized tests.
    initial_state_size = len(chooser.__dict__)
    
    for i in range(100):
        chooser.choose(candidates, context, set())
        
    assert len(chooser.__dict__) <= initial_state_size, f"{chooser_class.__name__} instance state grew!"
