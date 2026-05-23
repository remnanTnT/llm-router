from __future__ import annotations

import json


def parse_sse_usage(chunks: bytes | list[bytes] | str) -> tuple[int, int]:
    if isinstance(chunks, list):
        raw = b"".join(chunks).decode("utf-8", errors="ignore")
    elif isinstance(chunks, bytes):
        raw = chunks.decode("utf-8", errors="ignore")
    else:
        raw = chunks

    usage: dict | None = None
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
            break
    if not usage:
        return 0, 0
    return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
