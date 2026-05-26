from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db.models.functions import TruncDay, TruncHour, TruncMonth
from django.utils import timezone

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class APIValidationError(ValueError):
    pass


def parse_beijing_datetime(value: str | None, field_name: str) -> datetime:
    if not value:
        raise APIValidationError(f"{field_name} is required")
    try:
        parsed = datetime.strptime(value, TIME_FORMAT)
    except ValueError as exc:
        raise APIValidationError(f"{field_name} must be YYYY-MM-DD HH:mm:ss") from exc
    return timezone.make_aware(parsed, BEIJING_TZ)


def parse_time_range(params) -> tuple[datetime, datetime]:
    start = parse_beijing_datetime(params.get("start_time"), "start_time")
    end = parse_beijing_datetime(params.get("end_time"), "end_time")
    if start > end:
        raise APIValidationError("start_time must be earlier than or equal to end_time")
    return start, end


def choose_granularity(start: datetime, end: datetime) -> str:
    delta = end - start
    if delta.days < 2 or delta.total_seconds() <= 2 * 24 * 60 * 60:
        return "hour"
    if delta.days < 31 or delta.total_seconds() <= 31 * 24 * 60 * 60:
        return "day"
    return "month"


def bucket_expression(field_name: str, granularity: str):
    if granularity == "hour":
        return TruncHour(field_name, tzinfo=BEIJING_TZ)
    if granularity == "day":
        return TruncDay(field_name, tzinfo=BEIJING_TZ)
    return TruncMonth(field_name, tzinfo=BEIJING_TZ)


def bucket_start(value: datetime, granularity: str) -> datetime:
    local = value.astimezone(BEIJING_TZ)
    if granularity == "hour":
        return local.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return local.replace(hour=0, minute=0, second=0, microsecond=0)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_bucket(value: datetime, granularity: str) -> datetime:
    if granularity == "hour":
        return value + timedelta(hours=1)
    if granularity == "day":
        return value + timedelta(days=1)
    month = value.month + 1
    year = value.year
    if month == 13:
        month = 1
        year += 1
    return value.replace(year=year, month=month)


def format_bucket(value: datetime, granularity: str) -> str:
    local = value.astimezone(BEIJING_TZ)
    if granularity == "hour":
        return local.strftime("%Y-%m-%d %H:00:00")
    if granularity == "day":
        return local.strftime("%Y-%m-%d")
    return local.strftime("%Y-%m")


def bucket_labels(start: datetime, end: datetime, granularity: str) -> list[str]:
    current = bucket_start(start, granularity)
    last = bucket_start(end, granularity)
    labels = []
    while current <= last:
        labels.append(format_bucket(current, granularity))
        current = next_bucket(current, granularity)
    return labels


def fill_series(labels: list[str], values: dict[str, int | float | None], value_key: str, default):
    return [{"time": label, value_key: values.get(label, default)} for label in labels]


def percentile_linear(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = percentile * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def latency_boxplot(raw_values: list[int]) -> dict:
    raw_count = len(raw_values)
    over_threshold_count = sum(1 for value in raw_values if value > 890000)
    clean_values = sorted(value for value in raw_values if value <= 890000)
    over_threshold_ratio = round(over_threshold_count / raw_count, 4) if raw_count else 0

    if not clean_values:
        return {
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
            "sample_count": 0,
            "over_threshold_count": over_threshold_count,
            "over_threshold_ratio": over_threshold_ratio,
        }

    remove_count = math.ceil(len(clean_values) * 0.01)
    keep_count = max(len(clean_values) - remove_count, 1)
    values = [float(value) for value in clean_values[:keep_count]]

    return {
        "min": percentile_linear(values, 0),
        "q1": percentile_linear(values, 0.25),
        "median": percentile_linear(values, 0.5),
        "q3": percentile_linear(values, 0.75),
        "max": percentile_linear(values, 1),
        "sample_count": len(values),
        "over_threshold_count": over_threshold_count,
        "over_threshold_ratio": over_threshold_ratio,
    }
