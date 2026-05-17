from __future__ import annotations

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

REQUEST_STRIP_HEADERS = HOP_BY_HOP_HEADERS | {"content-length", "host", "content-encoding"}
BODYLESS_METHODS = {"GET", "HEAD", "OPTIONS", "DELETE"}


def filter_request_headers(headers: dict[str, str], method: str) -> dict[str, str]:
    strip = set(REQUEST_STRIP_HEADERS)
    if method.upper() in BODYLESS_METHODS:
        strip.add("content-type")
    return {key: value for key, value in headers.items() if key.lower() not in strip}


def filter_response_headers(headers: dict[str, str]) -> dict[str, str]:
    strip = HOP_BY_HOP_HEADERS | {"content-length", "content-encoding"}
    return {key: value for key, value in headers.items() if key.lower() not in strip}
