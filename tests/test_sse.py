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
    assert parse_sse_usage(raw) == (5, 6)


def test_parse_sse_usage_ignores_invalid_json():
    assert parse_sse_usage("data: nope\n\ndata: [DONE]\n\n") == (0, 0)
