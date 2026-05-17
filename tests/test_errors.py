from router.utils.errors import error_payload, timeout_sse_event


def test_error_payload_shape():
    payload = error_payload("msg", "version_too_old")
    assert payload == {"error": {"message": "msg", "type": "version_too_old", "code": None}}


def test_timeout_sse_event_uses_error_shape():
    event = timeout_sse_event().decode("utf-8")
    assert '"error": {' in event
    assert '"type": "gateway_timeout_error"' in event
    assert "data: [DONE]" in event
