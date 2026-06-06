from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import requests as http_requests
from django.http import FileResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from router.api.stats import (
    APIValidationError,
    BEIJING_TZ,
    TIME_FORMAT,
    bucket_expression,
    bucket_labels,
    bucket_start,
    choose_granularity,
    fill_series,
    format_bucket,
    latency_boxplot,
    parse_time_range,
)
from router.models import Model, Server, ServerOperation
from router.repositories.models import ModelRepository
from router.repositories.requests import RequestRepository

DOWNLOAD_FILE_PATH = Path("/home/AI_Assistant/AI_Assistant.exe")


@require_http_methods(["GET"])
def request_stats(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    start, end = parsed
    return JsonResponse({"code": 200, "total_count": RequestRepository.count_distinct_ips(start, end)})


@require_http_methods(["GET"])
def total_request_count(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    start, end = parsed
    return JsonResponse({"code": 200, "total_count": RequestRepository.count_success_requests(start, end)})


@require_http_methods(["GET"])
def model_request_stats(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    model = _model_or_error(request.GET.get("model_name"))
    if isinstance(model, JsonResponse):
        return model
    start, end = parsed
    return JsonResponse(
        {
            "code": 200,
            "model_id": model.id,
            "total_count": RequestRepository.count_success_requests_by_model(start, end, model.id),
        }
    )


@require_http_methods(["GET"])
def all_model_request_stats(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    start, end = parsed
    model_name = request.GET.get("model_name")
    if model_name is not None and not model_name.strip():
        return _bad_request("model_name cannot be blank")
    if model_name:
        model = _model_or_error(model_name)
        if isinstance(model, JsonResponse):
            return model
        models = [model]
    else:
        models = ModelRepository.list_all()
    counts = RequestRepository.count_success_requests_grouped_by_model(start, end, [model.id for model in models])
    return JsonResponse(
        {
            "code": 200,
            "data": [{"model_name": model.model_name, "total_count": counts.get(model.id, 0)} for model in models],
        }
    )


@require_http_methods(["GET"])
def models(request):
    return JsonResponse(
        {
            "code": 200,
            "data": [
                {"id": model.id, "model_name": model.model_name, "concurrent_limit": model.concurrent_limit}
                for model in ModelRepository.list_all()
            ],
        }
    )


@require_http_methods(["GET"])
def model_info(request):
    model = _model_or_error(request.GET.get("model_name"))
    if isinstance(model, JsonResponse):
        return model
    return JsonResponse(
        {
            "code": 200,
            "data": {"model_name": model.model_name, "concurrent_limit": model.concurrent_limit},
        }
    )


@require_http_methods(["GET"])
def request_time_stats(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    start, end = parsed
    return JsonResponse({"code": 200, "stats": _average_latency_stats(start, end)})


@require_http_methods(["GET"])
def model_request_time_stats(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    model = _model_or_error(request.GET.get("model_name"))
    if isinstance(model, JsonResponse):
        return model
    start, end = parsed
    return JsonResponse({"code": 200, "stats": _average_latency_stats(start, end, model.id)})


@require_http_methods(["GET"])
def model_request_count_by_period(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    model = _model_or_error(request.GET.get("model_name"))
    if isinstance(model, JsonResponse):
        return model
    start, end = parsed
    granularity = choose_granularity(start, end)
    labels = bucket_labels(start, end, granularity)
    rows = RequestRepository.count_success_by_bucket(start, end, model.id, bucket_expression("send_time", granularity))
    values = {format_bucket(bucket, granularity): count for bucket, count in rows.items()}
    return JsonResponse({"code": 200, "stats": fill_series(labels, values, "count", 0)})


@require_http_methods(["GET"])
def model_ip_count_by_period(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    model = _model_or_error(request.GET.get("model_name"))
    if isinstance(model, JsonResponse):
        return model
    start, end = parsed
    granularity = choose_granularity(start, end)
    labels = bucket_labels(start, end, granularity)
    rows = RequestRepository.count_distinct_ips_by_bucket(start, end, model.id, bucket_expression("send_time", granularity))
    values = {format_bucket(bucket, granularity): count for bucket, count in rows.items()}
    return JsonResponse({"code": 200, "stats": fill_series(labels, values, "count", 0)})


@require_http_methods(["GET"])
def model_latency_boxplot(request):
    parsed = _time_range_or_error(request)
    if isinstance(parsed, JsonResponse):
        return parsed
    start, end = parsed
    models_or_response = _models_for_boxplot(request.GET.get("model_names"))
    if isinstance(models_or_response, JsonResponse):
        return models_or_response
    selected_models = models_or_response
    granularity = choose_granularity(start, end)
    labels = bucket_labels(start, end, granularity)
    model_by_id = {model.id: model for model in selected_models}
    grouped = defaultdict(list)

    for row in RequestRepository.latency_rows_for_boxplot(start, end, list(model_by_id.keys())):
        model = model_by_id.get(row["model_id"])
        if model is None:
            continue
        label = format_bucket(bucket_start(row["send_time"], granularity), granularity)
        grouped[(model.model_name, label)].append(row["latency"])

    model_data = {}
    valid_labels = set()
    for model in selected_models:
        time_labels = []
        boxplot_data = []
        over_threshold_count = []
        over_threshold_ratio = []
        for label in labels:
            summary = latency_boxplot(grouped.get((model.model_name, label), []))
            if summary["sample_count"] == 0:
                continue
            valid_labels.add(label)
            time_labels.append(_short_label(label, granularity))
            boxplot_data.append([summary["min"], summary["q1"], summary["median"], summary["q3"], summary["max"]])
            over_threshold_count.append(summary["over_threshold_count"])
            over_threshold_ratio.append(summary["over_threshold_ratio"])
        model_data[model.model_name] = {
            "time_labels": time_labels,
            "boxplot_data": boxplot_data,
            "over_threshold_count": over_threshold_count,
            "over_threshold_ratio": over_threshold_ratio,
        }

    root_time_labels = [_short_label(label, granularity) for label in labels if label in valid_labels]

    return JsonResponse(
        {
            "code": 200,
            "start_time": start.astimezone(BEIJING_TZ).strftime(TIME_FORMAT),
            "end_time": end.astimezone(BEIJING_TZ).strftime(TIME_FORMAT),
            "time_labels": root_time_labels,
            "model_data": model_data,
        }
    )


@require_http_methods(["GET"])
def download_ai_assistant(request):
    if not DOWNLOAD_FILE_PATH.exists() or not DOWNLOAD_FILE_PATH.is_file():
        return JsonResponse({"code": 404, "error": "file not found"}, status=404)
    return FileResponse(
        DOWNLOAD_FILE_PATH.open("rb"),
        content_type="application/octet-stream",
        as_attachment=True,
        filename="AI_Assistant.exe",
    )


def _time_range_or_error(request):
    try:
        return parse_time_range(request.GET)
    except APIValidationError as exc:
        return _bad_request(str(exc))


def _model_or_error(model_name: str | None):
    if not model_name or not model_name.strip():
        return _bad_request("model_name is required")
    model = ModelRepository.get_by_name(model_name.strip())
    if model is None:
        return JsonResponse({"code": 404, "error": "model_name not found"}, status=404)
    return model


def _models_for_boxplot(model_names: str | None):
    if model_names is None:
        return ModelRepository.list_all()
    names = [name.strip() for name in model_names.split(",") if name.strip()]
    if not names:
        return _bad_request("model_names cannot be blank")
    models = ModelRepository.get_by_names(names)
    missing = [name for name in names if name not in models]
    if missing:
        return JsonResponse({"code": 404, "error": "model_names not found", "missing": missing}, status=404)
    return [models[name] for name in names]


def _short_label(label: str, granularity: str) -> str:
    if granularity == "hour":
        return label[11:16]
    return label


def _average_latency_stats(start, end, model_id: int | None = None):
    granularity = choose_granularity(start, end)
    labels = bucket_labels(start, end, granularity)
    rows = RequestRepository.average_latency_by_bucket(start, end, bucket_expression("send_time", granularity), model_id)
    values = {format_bucket(bucket, granularity): round(value, 2) if value is not None else None for bucket, value in rows.items()}
    return fill_series(labels, values, "avg_duration_ms", None)


@require_http_methods(["POST"])
def add_server(request):
    parsed_payload = _add_server_payload_or_error(request)
    if isinstance(parsed_payload, JsonResponse):
        return parsed_payload
    payload, servers_data = parsed_payload

    if _has_duplicate_base_urls(servers_data):
        return _bad_request("duplicate base_url in request")

    now = timezone.now()
    results = [_process_add_server_item(data, now) for data in servers_data]
    return _add_server_result_response(payload, results)


def _add_server_payload_or_error(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _bad_request("invalid JSON body")

    if isinstance(payload, dict):
        return payload, [payload]
    if isinstance(payload, list):
        return payload, payload
    return _bad_request("payload must be a dictionary or a list")


def _has_duplicate_base_urls(servers_data) -> bool:
    base_urls = [server.get("base_url", "").strip() for server in servers_data if isinstance(server, dict)]
    return len(base_urls) != len(set(base_urls))


def _process_add_server_item(data, now):
    if not isinstance(data, dict):
        return {"error": "invalid item in list, must be a dictionary"}

    base_url = data.get("base_url", "").strip()
    model_name = data.get("model_name", "").strip()
    operation = _create_add_server_operation(data, now)

    validation_failure = _add_server_validation_failure(base_url, model_name)
    if validation_failure:
        message, result_base_url = validation_failure
        return _fail_add_server_operation(operation, message, result_base_url)

    verify_error = _verify_server_model(base_url, model_name)
    if verify_error:
        return _fail_add_server_operation(operation, verify_error, base_url)

    return _create_add_server_success(operation, base_url, model_name)


def _create_add_server_operation(data, now):
    return ServerOperation.objects.create(
        operation_type="add_server",
        request_data=data,
        status="pending",
        created_at=now,
        updated_at=now,
    )


def _add_server_validation_failure(base_url: str, model_name: str) -> tuple[str, str | None] | None:
    if not base_url:
        return "base_url is required", None
    if not base_url.rstrip("/").endswith("/v1"):
        return "base_url must end with /v1", base_url
    if not model_name:
        return "model_name is required", base_url
    if Server.objects.filter(base_url=base_url).exists():
        return "base_url already exists", base_url
    return None


def _verify_server_model(base_url: str, model_name: str) -> str | None:
    verify_url = base_url.rstrip("/") + "/models"
    try:
        resp = http_requests.get(verify_url, timeout=10)
        resp.raise_for_status()
        models_data = resp.json()
        model_ids = [model.get("id", "") for model in models_data.get("data", [])]
        if model_name not in model_ids:
            raise ValueError(f"model '{model_name}' not found in server response, available: {model_ids}")
    except Exception as e:
        return f"failed to reach server at {verify_url}: {e}"
    return None


def _fail_add_server_operation(operation, message: str, base_url: str | None = None):
    operation.status = "failed"
    operation.error_message = message
    operation.updated_at = timezone.now()
    operation.save()

    result = {"error": message}
    if base_url is not None:
        result["base_url"] = base_url
    return result


def _create_add_server_success(operation, base_url: str, model_name: str):
    model_obj, _ = Model.objects.get_or_create(model_name=model_name)
    server = Server.objects.create(
        model_id=model_obj.id,
        base_url=base_url,
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )

    operation.server_id = server.id
    operation.status = "success"
    operation.response_data = {"id": server.id, "base_url": server.base_url, "model_name": model_name}
    operation.updated_at = timezone.now()
    operation.save()
    return operation.response_data


def _add_server_result_response(payload, results):
    if isinstance(payload, dict):
        if "error" in results[0]:
            return _bad_request(results[0]["error"])
        return JsonResponse({"code": 200, "data": results[0]})
    return JsonResponse({"code": 200, "data": results})


@require_http_methods(["POST"])
def upsert_mr_live_review(request):
    import json
    from router.models import MrLiveReview

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _bad_request("invalid JSON body")

    discussion_id = data.get("discussion_id")
    if not discussion_id:
        return _bad_request("discussion_id is required")

    # Validate that all keys in data match model fields
    valid_fields = {f.name for f in MrLiveReview._meta.fields if f.name != "id"}
    extra_fields = set(data.keys()) - valid_fields
    if extra_fields:
        return _bad_request(f"invalid fields: {', '.join(sorted(extra_fields))}")

    state = data.get("state")

    try:
        review = MrLiveReview.objects.get(discussion_id=discussion_id)
        if review.state != state:
            # Update the record if state is different
            for field, value in data.items():
                setattr(review, field, value)
            review.save()
            return JsonResponse({"code": 200, "message": "updated", "data": {"id": review.id}})
        else:
            # Skip if state is the same
            return JsonResponse({"code": 200, "message": "skipped", "data": {"id": review.id}})
    except MrLiveReview.DoesNotExist:
        # Create a new record if discussion_id does not exist
        review = MrLiveReview.objects.create(**data)
        return JsonResponse({"code": 200, "message": "created", "data": {"id": review.id}})


@require_http_methods(["POST"])
def create_codehub_review(request):
    import json
    from router.models import CodehubReview
    from router.repositories.codehub_review import CodehubReviewRepository

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return _bad_request("invalid JSON body")

    # Validate that all keys in data match model fields
    valid_fields = {f.name for f in CodehubReview._meta.fields}
    extra_fields = set(data.keys()) - valid_fields
    if extra_fields:
        return _bad_request(f"invalid fields: {', '.join(sorted(extra_fields))}")

    issue_hash = data.get("issue_hash")
    if not issue_hash:
        return _bad_request("issue_hash is required")

    if CodehubReviewRepository.exists_by_hash(issue_hash):
        return JsonResponse({"code": 200, "message": "skipped", "data": {"issue_hash": issue_hash}})

    try:
        review = CodehubReviewRepository.create(data)
        return JsonResponse({"code": 200, "message": "created", "data": {"id": review.id}})
    except Exception as e:
        return JsonResponse({"code": 500, "error": str(e)}, status=500)


def _bad_request(message: str):
    return JsonResponse({"code": 400, "error": message}, status=400)
