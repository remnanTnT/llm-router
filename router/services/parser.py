from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass
class ParsedRequest:
    body: bytes
    model_name: str | None
    stream: bool
    max_tokens: int | None
    is_json: bool


class RequestParser:
    def __init__(self, default_max_tokens: int = 8528):
        self.default_max_tokens = default_max_tokens

    def parse(self, body: bytes) -> ParsedRequest:
        if not body:
            return ParsedRequest(body=body, model_name=None, stream=False, max_tokens=None, is_json=False)
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ParsedRequest(body=body, model_name=None, stream=False, max_tokens=None, is_json=False)
        if not isinstance(data, dict):
            return ParsedRequest(body=body, model_name=None, stream=False, max_tokens=None, is_json=True)

        stream = bool(data.get("stream"))
        if stream:
            options = data.get("stream_options")
            if not isinstance(options, dict):
                options = {}
            options["include_usage"] = True
            data["stream_options"] = options

        if data.get("max_tokens") is None:
            data["max_tokens"] = self.default_max_tokens

        max_tokens = self._safe_int(data.get("max_tokens"))
        new_body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return ParsedRequest(
            body=new_body,
            model_name=data.get("model") if isinstance(data.get("model"), str) else None,
            stream=stream,
            max_tokens=max_tokens,
            is_json=True,
        )

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
