import json
import time
from unittest.mock import MagicMock, patch
import pytest

from router.route_algorithm.prefix_cache_preble import PrefixCachePrebleServerChooser
from router.route_algorithm.base import ServerSelectionContext

class MockServer:
    def __init__(self, server_id, base_url):
        self.id = server_id
        self.base_url = base_url
        self.cache_time = 3600

@pytest.fixture
def mock_redis():
    with patch("redis.Redis") as mock:
        client = MagicMock()
        mock.return_value = client
        # Simulate MGET returning None by default
        client.mget.return_value = []
        yield client

def test_redis_prefix_cache_flow(mock_redis):
    # Reset class attribute for testing
    PrefixCachePrebleServerChooser._redis_client = mock_redis
    
    # Initialize chooser
    chooser = PrefixCachePrebleServerChooser(
        count_provider=lambda targets: {t: 0 for t in targets},
        block_size=2
    )
    
    candidates = [
        MockServer(1, "http://server1"),
        MockServer(2, "http://server2")
    ]
    
    body = b'{"prompt": "hello world how are you"}'
    context = ServerSelectionContext(
        request_id=1,
        ip_id=1,
        model_id=1,
        model_name="test-model",
        path="/v1/completions",
        method="POST",
        is_stream=False,
        body=body
    )
    
    # 1. on_response - should save to Redis
    chooser.on_response(candidates[0], context, 200)
    
    # Verify Redis SET/pipeline calls
    # tokens are ["hello", "world", "how", "are", "you"]
    # blocks of 2: ["hello", "world"], ["hello", "world", "how", "are"], ["hello", "world", "how", "are", "you"]
    assert mock_redis.pipeline.called
    pipe = mock_redis.pipeline.return_value
    assert pipe.set.call_count == 3
    
    # Capture the keys and values stored
    saved_data = {}
    for call in pipe.set.call_args_list:
        args, kwargs = call
        saved_data[args[0]] = json.loads(args[1])
    
    # 2. choose - should match from Redis
    # Prepare mock MGET response
    # We'll simulate a match for the first two blocks
    mock_redis.mget.return_value = [
        json.dumps(saved_data[list(saved_data.keys())[0]]),
        json.dumps(saved_data[list(saved_data.keys())[1]]),
        None # No match for the full prompt
    ]
    
    new_context = ServerSelectionContext(
        request_id=2,
        ip_id=1,
        model_id=1,
        model_name="test-model",
        path="/v1/completions",
        method="POST",
        is_stream=False,
        body=body
    )
    
    selected = chooser.choose(candidates, new_context, set())
    
    assert selected.id == 1
    # Match ratio for 4 tokens out of 5 = 0.8
    assert new_context.prefix_cache == 0.8
    assert new_context.last_match == 1
