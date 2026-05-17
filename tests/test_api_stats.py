from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import Client
from django.utils import timezone

from router.models import Model, RequestRecord


def _dt(value):
    return timezone.make_aware(datetime.strptime(value, "%Y-%m-%d %H:%M:%S"), ZoneInfo("Asia/Shanghai"))


def _request(model, send_time, task_status="success", latency=100, ip_id=1):
    return RequestRecord.objects.create(
        user_ip_id=1,
        ip_id=ip_id,
        send_time=_dt(send_time),
        end_time=_dt(send_time),
        latency=latency,
        model_id=model.id,
        task_status=task_status,
        input_token_cnt=0,
        output_token_cnt=0,
    )


def test_request_stats_counts_distinct_ips():
    client = Client()
    model = Model.objects.create(model_name="model-a", concurrent_limit=3)
    _request(model, "2026-01-01 00:10:00", ip_id=1)
    _request(model, "2026-01-01 00:20:00", ip_id=1)
    _request(model, "2026-01-01 00:30:00", ip_id=2)

    response = client.get("/api/request_stats", {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 01:00:00"})

    assert response.status_code == 200
    assert response.json()["total_count"] == 2


def test_total_request_count_counts_success_only():
    client = Client()
    model = Model.objects.create(model_name="model-a", concurrent_limit=3)
    _request(model, "2026-01-01 00:10:00", task_status="success")
    _request(model, "2026-01-01 00:20:00", task_status="failed")

    response = client.get("/api/total_request_count", {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 01:00:00"})

    assert response.status_code == 200
    assert response.json()["total_count"] == 1


def test_model_request_stats_filters_model():
    client = Client()
    model_a = Model.objects.create(model_name="model-a", concurrent_limit=3)
    model_b = Model.objects.create(model_name="model-b", concurrent_limit=3)
    _request(model_a, "2026-01-01 00:10:00")
    _request(model_b, "2026-01-01 00:20:00")

    response = client.get(
        "/api/model_request_stats",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 01:00:00", "model_name": "model-a"},
    )

    assert response.status_code == 200
    assert response.json()["model_id"] == model_a.id
    assert response.json()["total_count"] == 1


def test_all_model_request_stats_includes_zero_count_models():
    client = Client()
    model_a = Model.objects.create(model_name="model-a", concurrent_limit=3)
    Model.objects.create(model_name="model-b", concurrent_limit=5)
    _request(model_a, "2026-01-01 00:10:00")

    response = client.get(
        "/api/all_model_request_stats",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 01:00:00"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == [
        {"model_name": "model-a", "total_count": 1},
        {"model_name": "model-b", "total_count": 0},
    ]


def test_models_and_model_info():
    client = Client()
    model = Model.objects.create(model_name="model-a", concurrent_limit=7)

    models_response = client.get("/api/models")
    info_response = client.get("/api/model_info", {"model_name": "model-a"})

    assert models_response.status_code == 200
    assert models_response.json()["data"] == [{"id": model.id, "model_name": "model-a", "concurrent_limit": 7}]
    assert info_response.status_code == 200
    assert info_response.json()["data"] == {"model_name": "model-a", "concurrent_limit": 7}


def test_request_time_stats_uses_beijing_bucket_and_excludes_failed_and_null_latency():
    client = Client()
    model = Model.objects.create(model_name="model-a", concurrent_limit=3)
    _request(model, "2026-01-01 00:30:00", task_status="success", latency=100)
    _request(model, "2026-01-01 00:40:00", task_status="success", latency=200)
    _request(model, "2026-01-01 00:50:00", task_status="failed", latency=900)
    _request(model, "2026-01-01 00:55:00", task_status="success", latency=None)

    response = client.get(
        "/api/request_time_stats",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 01:00:00"},
    )

    assert response.status_code == 200
    assert response.json()["stats"] == [
        {"time": "2026-01-01 00:00:00", "avg_duration_ms": 150.0},
        {"time": "2026-01-01 01:00:00", "avg_duration_ms": None},
    ]


def test_period_counts_fill_missing_buckets_and_count_distinct_ips():
    client = Client()
    model = Model.objects.create(model_name="model-a", concurrent_limit=3)
    _request(model, "2026-01-01 00:10:00", ip_id=1)
    _request(model, "2026-01-01 00:20:00", ip_id=1)
    _request(model, "2026-01-01 02:10:00", ip_id=2)

    count_response = client.get(
        "/api/model_request_count_by_period",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 02:00:00", "model_name": "model-a"},
    )
    ip_response = client.get(
        "/api/model_ip_count_by_period",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 02:00:00", "model_name": "model-a"},
    )

    assert count_response.status_code == 200
    assert count_response.json()["stats"] == [
        {"time": "2026-01-01 00:00:00", "count": 2},
        {"time": "2026-01-01 01:00:00", "count": 0},
        {"time": "2026-01-01 02:00:00", "count": 1},
    ]
    assert ip_response.status_code == 200
    assert ip_response.json()["stats"] == [
        {"time": "2026-01-01 00:00:00", "count": 1},
        {"time": "2026-01-01 01:00:00", "count": 0},
        {"time": "2026-01-01 02:00:00", "count": 1},
    ]


def test_boxplot_filters_over_limit_truncates_top_one_percent_and_interpolates():
    client = Client()
    model = Model.objects.create(model_name="model-a", concurrent_limit=3)
    for latency in [100, 200, 300, 400, 500, 900001]:
        _request(model, "2026-01-01 00:10:00", latency=latency)

    response = client.get(
        "/api/model_latency_boxplot",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 01:00:00", "model_names": "model-a"},
    )

    assert response.status_code == 200
    point = response.json()["model_data"]["model-a"][0]
    assert point == {
        "time": "2026-01-01 00:00:00",
        "min": 100.0,
        "q1": 175.0,
        "median": 250.0,
        "q3": 325.0,
        "max": 400.0,
        "sample_count": 4,
        "raw_count": 6,
        "over_limit_count": 1,
        "over_limit_ratio": 0.1667,
    }


def test_validation_errors():
    client = Client()

    missing = client.get("/api/total_request_count")
    invalid = client.get("/api/total_request_count", {"start_time": "bad", "end_time": "2026-01-01 00:00:00"})
    reversed_range = client.get(
        "/api/total_request_count",
        {"start_time": "2026-01-02 00:00:00", "end_time": "2026-01-01 00:00:00"},
    )
    missing_model = client.get(
        "/api/model_request_stats",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 01:00:00"},
    )
    unknown_model = client.get(
        "/api/model_request_stats",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-01 01:00:00", "model_name": "missing"},
    )

    assert missing.status_code == 400
    assert invalid.status_code == 400
    assert reversed_range.status_code == 400
    assert missing_model.status_code == 400
    assert unknown_model.status_code == 404


def test_granularity_thresholds():
    client = Client()
    model = Model.objects.create(model_name="model-a", concurrent_limit=3)
    _request(model, "2026-01-01 00:10:00", latency=100)

    hourly = client.get(
        "/api/request_time_stats",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-01-03 00:00:00"},
    )
    daily = client.get(
        "/api/request_time_stats",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-02-01 00:00:00"},
    )
    monthly = client.get(
        "/api/request_time_stats",
        {"start_time": "2026-01-01 00:00:00", "end_time": "2026-02-02 00:00:00"},
    )

    assert hourly.json()["stats"][0]["time"] == "2026-01-01 00:00:00"
    assert hourly.json()["stats"][1]["time"] == "2026-01-01 01:00:00"
    assert daily.json()["stats"][0]["time"] == "2026-01-01"
    assert daily.json()["stats"][1]["time"] == "2026-01-02"
    assert monthly.json()["stats"][0]["time"] == "2026-01"
    assert monthly.json()["stats"][1]["time"] == "2026-02"
