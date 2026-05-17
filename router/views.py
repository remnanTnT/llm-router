from __future__ import annotations

import json
import threading

from django.core.exceptions import RequestDataTooBig
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from router.config import APP_CONFIG
from router.repositories.ips import IPRepository
from router.repositories.models import ModelRepository
from router.repositories.requests import RequestRepository
from router.repositories.whitelist import WhitelistRepository
from router.services.admission import AdmissionService
from router.services.cmdb import CMDBService
from router.services.opencode import OpencodeVersionService
from router.services.parser import RequestParser
from router.services.proxy import ProxyService
from router.utils.errors import error_response


@require_http_methods(["GET"])
def healthy(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unhealthy"}, status=503)
    return JsonResponse({"status": "healthy"})


@csrf_exempt
def proxy(request, path: str):
    user_agent = request.headers.get("User-Agent", "")
    client_ip = _client_ip(request)
    ip = None
    model = None
    parsed = None
    try:
        body = request.body
    except RequestDataTooBig:
        RequestRepository.create_blocked(None, 0, None, user_agent, "413 Request Entity Too Large", "request body too large")
        return error_response(413, "Request body exceeds the maximum allowed size", "request_too_large")
    except Exception:
        return HttpResponse(status=499)

    try:
        ip, created = IPRepository.get_or_create(client_ip)
        if created:
            threading.Thread(target=CMDBService().fetch_and_save_user, args=(client_ip,), daemon=True).start()

        admission = AdmissionService()
        permission = admission.check_permission(ip)
        if not permission.allowed:
            RequestRepository.create_blocked(ip.id, 0, None, user_agent, "403 Forbidden", "permission denied")
            return error_response(permission.status_code, permission.message or "Forbidden", permission.error_type or "permission_denied")

        blocked, version = OpencodeVersionService.should_block(user_agent)
        if blocked:
            message = f"Your opencode version ({version}) is no longer supported. Please upgrade opencode to latest version."
            RequestRepository.create_blocked(ip.id, 0, None, user_agent, "403 Forbidden", "version too old")
            return error_response(403, message, "version_too_old")

        parser = RequestParser(int(APP_CONFIG.get("proxy", {}).get("default_max_tokens", 8528)))
        parsed = parser.parse(body)
        model = ModelRepository.get_by_name(parsed.model_name)

        max_token_check = admission.check_max_tokens(parsed.max_tokens, model)
        if not max_token_check.allowed:
            RequestRepository.create_blocked(ip.id, model.id if model else 0, parsed.stream, user_agent, "400 Bad Request", "max_tokens exceeded")
            return error_response(max_token_check.status_code, max_token_check.message or "invalid request", max_token_check.error_type or "invalid_request_error")

        concurrency = admission.check_concurrency(ip, model)
        if not concurrency.allowed:
            RequestRepository.create_blocked(ip.id, model.id if model else 0, parsed.stream, user_agent, "429 Too Many Requests", "concurrent limit exceeded")
            return error_response(concurrency.status_code, concurrency.message or "concurrent limit exceeded", concurrency.error_type or "concurrent_limit_exceeded")

        return ProxyService().forward(request, path, parsed, ip.id, model, user_agent)
    except Exception as exc:
        model_id = model.id if model else 0
        ip_id = ip.id if ip else None
        is_stream = parsed.stream if parsed else None
        RequestRepository.create_blocked(ip_id, model_id, is_stream, user_agent, "502 Bad Gateway", str(exc)[:100])
        return error_response(502, "502 Bad Gateway", "server_error")


@csrf_exempt
@require_http_methods(["POST"])
def whitelist_update(request):
    data = _request_data(request)
    employee_no = str(data.get("employee_no", "")).strip()
    try:
        is_allowed = int(data.get("is_allowed"))
    except (TypeError, ValueError):
        return JsonResponse({"code": 400, "error": "is_allowed must be 0 or 1"}, status=400)
    if not employee_no or is_allowed not in (0, 1):
        return JsonResponse({"code": 400, "error": "employee_no and is_allowed are required"}, status=400)
    row, created, changed = WhitelistRepository.upsert(employee_no, is_allowed)
    message = "创建成功" if created else ("更新成功" if changed else "本次修改未生效")
    return JsonResponse(
        {
            "code": 200,
            "message": message,
            "data": {
                "employee_no": row.employee_no,
                "is_allowed": row.is_allowed,
                "update_time": timezone.localtime(row.update_time).strftime("%Y-%m-%d %H:%M:%S") if row.update_time else None,
            },
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def refresh_user_info(request):
    threading.Thread(target=CMDBService().fetch_all_users, daemon=True).start()
    return JsonResponse({"code": 200, "message": "用户信息刷新任务已启动"})


def _request_data(request) -> dict:
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")
