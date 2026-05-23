from router.utils.sse import parse_sse_usage


def test_parse_sse_usage_returns_last_usage_event():
    raw = b"".join(
        [
            b'data: {"choices":[]}\n\n',
            b'data: {"usage":{"prompt_tokens":3,"completion_tokens":4}}\n\n',
            b'data: {"usage":{"prompt_tokens":5,"completion_tokens":6}}\n\n',
            b"data: [DONE]\n\n",
        ]
    )
    assert parse_sse_usage(raw) == (5, 6, 0)


def test_parse_sse_usage_with_cached_tokens():
    raw = b"".join(
        [
            b'data: {"usage":{"prompt_tokens":2006,"completion_tokens":300,"prompt_tokens_details":{"cached_tokens":1920}}}\n\n',
            b"data: [DONE]\n\n",
        ]
    )
    assert parse_sse_usage(raw) == (2006, 300, 1920)


def test_parse_sse_usage_ignores_invalid_json():
    assert parse_sse_usage("data: nope\n\ndata: [DONE]\n\n") == (0, 0, 0)
