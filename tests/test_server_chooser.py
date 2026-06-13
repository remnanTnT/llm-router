from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from router.route_algorithm.base import ServerSelectionContext
from router.route_algorithm.least_connection import LeastConnectionServerChooser
from router.route_algorithm.prefix_cache_preble import PrefixCachePrebleServerChooser


from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_redis():
    with patch("redis.Redis") as mock:
        client = MagicMock()
        mock.return_value = client
        # Simple in-memory storage for the mock
        storage = {}

        def mock_set(key, val, ex=None):
            storage[key] = val
            return True

        def mock_mget(keys):
            return [storage.get(k) for k in keys]

        client.set.side_effect = mock_set
        client.mget.side_effect = mock_mget
        
        # Pipeline mock
        pipe = MagicMock()
        client.pipeline.return_value = pipe
        pipe.set.side_effect = mock_set
        
        PrefixCachePrebleServerChooser._redis_client = client
        yield client
        PrefixCachePrebleServerChooser._redis_client = None


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


def test_least_connection_chooser_randomly_selects_among_tied_least_loaded_servers(monkeypatch):
    chooser = LeastConnectionServerChooser(
        lambda targets: {
            "http://10.0.0.1:8000": 0,
            "http://10.0.0.2:8000": 0,
            "http://10.0.0.3:8000": 1,
        }
    )
    candidates = [
        make_server(1, "http://10.0.0.1:8000"),
        make_server(2, "http://10.0.0.2:8000"),
        make_server(3, "http://10.0.0.3:8000"),
    ]
    choices = []

    def choose(options):
        choices.append(list(options))
        return options[1]

    monkeypatch.setattr("router.route_algorithm.least_connection.random.choice", choose)

    selected = chooser.choose(candidates, make_context(), set())

    assert selected.id == 2
    assert [[server.id for server in options] for options in choices] == [[1, 2]]


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
    chooser = PrefixCachePrebleServerChooser(
        lambda targets: {"http://10.0.0.1:8000": 3, "http://10.0.0.2:8000": 1, "http://10.0.0.3:8000": 0},
        prefix_block_chars=1,
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
    assert context.prefix_cache > 0.9
    assert context.last_match == 102


def test_prefix_cache_medium_match_chooses_least_loaded_overall_server():
    chooser = PrefixCachePrebleServerChooser(
        lambda targets: {"http://10.0.0.1:8000": 0, "http://10.0.0.2:8000": 1, "http://10.0.0.3:8000": 0},
        prefix_block_chars=1,
    )
    candidates = [
        make_server(1, "http://10.0.0.1:8000"),
        make_server(2, "http://10.0.0.2:8000"),
        make_server(3, "http://10.0.0.3:8000"),
    ]
    chooser.on_response(candidates[1], make_context(make_body([str(i) for i in range(60)]), request_id=201), 200)

    context = make_context(make_body([str(i) for i in range(60)] + [f"new-{i}" for i in range(20)]))
    selected = chooser.choose(candidates, context, set())

    assert selected.id == 2
    assert context.prefix_cache > 0.5
    assert context.last_match == 201


def test_prefix_cache_last_match_tracks_best_match_request_id():
    chooser = PrefixCachePrebleServerChooser(lambda targets: {}, prefix_block_chars=1)
    candidates = [make_server(1, "http://10.0.0.1:8000")]
    chooser.on_response(candidates[0], make_context(make_body(["a", "b", "x"]), request_id=301), 200)
    chooser.on_response(candidates[0], make_context(make_body(["a", "b", "c", "d"]), request_id=302), 200)

    context = make_context(make_body(["a", "b", "c", "new"]))
    chooser.choose(candidates, context, set())

    assert context.prefix_cache > 0.5
    assert context.last_match == 302


def test_prefix_cache_last_match_is_none_without_common_prefix():
    chooser = PrefixCachePrebleServerChooser(lambda targets: {}, prefix_block_chars=1)
    candidates = [make_server(1, "http://10.0.0.1:8000")]
    chooser.on_response(candidates[0], make_context(b"hello world", request_id=401), 200)

    context = make_context(b"goodbye world")
    chooser.choose(candidates, context, set())

    assert context.prefix_cache == 0.0
    assert context.last_match is None


def test_prefix_cache_response_hook_only_marks_successful_responses():
    chooser = PrefixCachePrebleServerChooser(lambda targets: {}, prefix_block_chars=1)
    server = make_server(1, "http://10.0.0.1:8000")
    context = make_context(make_body(["hello", "world"]))

    chooser.on_response(server, context, 500)
    # Check that nothing was saved to Redis
    pipe = PrefixCachePrebleServerChooser._redis_client.pipeline.return_value
    assert pipe.set.call_count == 0

    chooser.on_response(server, context, 200)
    assert pipe.set.call_count > 0


def test_prefix_cache_max_prefix_chars_default():
    chooser = PrefixCachePrebleServerChooser(lambda targets: {}, max_prefix_chars=10)

    assert chooser.max_prefix_chars == 10


def test_prefix_cache_chunks_chinese_text_by_character():
    chooser = PrefixCachePrebleServerChooser(lambda targets: {}, prefix_block_chars=2)
    prefix_chars = chooser._prefix_chars_from_body(
        json.dumps({"prompt": "你好，世界。再"}, ensure_ascii=False).encode("utf-8")
    )

    assert prefix_chars == "你好，世界。再"
    hashes = chooser._get_prefix_hashes(prefix_chars)
    # Block size 2, text length 7
    # 0:2 -> "你好" (2)
    # 2:4 -> "你好，世" (4)
    # 4:6 -> "你好，世界。" (6)
    # 6:7 -> "你好，世界。再" (7)
    assert [length for _, length in hashes] == [2, 4, 6, 7]


def test_prefix_cache_uses_renamed_threshold_arguments():
    chooser = PrefixCachePrebleServerChooser(
        lambda targets: {},
        primary_match_threshold=0.91,
        secondary_match_threshold=0.41,
    )

    assert chooser.primary_match_threshold == 0.91
    assert chooser.secondary_match_threshold == 0.41


# Trie-specific memory and pruning tests removed.
