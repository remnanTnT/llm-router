import json

from router.services.parser import RequestParser


def test_parser_injects_stream_options_and_default_max_tokens():
    parsed = RequestParser(default_max_tokens=8528).parse(b'{"model":"m1","stream":true}')
    data = json.loads(parsed.body.decode())
    assert parsed.model_name == "m1"
    assert parsed.stream is True
    assert parsed.max_tokens == 8528
    assert data["stream_options"] == {"include_usage": True}
    assert data["max_tokens"] == 8528


def test_parser_leaves_non_json_unchanged():
    parsed = RequestParser().parse(b"not-json")
    assert parsed.body == b"not-json"
    assert parsed.is_json is False
    assert parsed.model_name is None
