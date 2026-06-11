import json
from router.services.proxy_response import parse_json_usage

def test_parse_json_usage_with_cached_tokens():
    content = json.dumps({
        "usage": {
            "prompt_tokens": 2006,
            "completion_tokens": 300,
            "total_tokens": 2306,
            "prompt_tokens_details": {
                "cached_tokens": 1920
            }
        }
    }).encode("utf-8")
    
    assert parse_json_usage(content) == (2006, 300, 1920)

def test_parse_json_usage_without_cached_tokens():
    content = json.dumps({
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
    }).encode("utf-8")
    
    assert parse_json_usage(content) == (100, 50, 0)

def test_parse_json_usage_invalid_json():
    assert parse_json_usage(b"invalid") == (0, 0, 0)

def test_parse_json_usage_missing_usage():
    assert parse_json_usage(b"{}") == (0, 0, 0)
