from __future__ import annotations

def error_payload(message: str, error_type: str, code: str | None = None) -> dict:
    return {"error": {"message": message, "type": error_type, "code": code}}


def error_response(status: int, message: str, error_type: str, code: str | None = None):
    from django.http import JsonResponse

    return JsonResponse(error_payload(message, error_type, code), status=status)


def timeout_sse_event() -> bytes:
    payload = error_payload("request timeout, please try again later", "gateway_timeout_error")
    import json

    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\ndata: [DONE]\n\n".encode("utf-8")
