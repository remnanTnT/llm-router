from __future__ import annotations

from datetime import datetime, timedelta
from http import HTTPStatus

from django.db import models
from django.utils import timezone

from router.models import RequestRecord


_EXTRA_STATUS_PHRASES = {
    499: "Client Closed Request",
}


def _status_text(code: int) -> str:
    try:
        phrase = HTTPStatus(code).phrase
    except ValueError:
        phrase = _EXTRA_STATUS_PHRASES.get(code, "")
    return f"{code} {phrase}".rstrip()


class RequestRepository:
    @staticmethod
    def create_processing(ip_id: int | None, model_id: int, is_stream: bool, user_agent: str | None) -> RequestRecord:
        return RequestRecord.objects.create(
            user_ip_id=1,
            ip_id=ip_id,
            send_time=timezone.now(),
            model_id=model_id,
            task_status="processing",
            is_stream=is_stream,
            user_agent=(user_agent or "")[:500],
            input_token_cnt=0,
            output_token_cnt=0,
            attempt_count=0,
            prefix_cache=0.0,
            last_match=None,
        )

    @staticmethod
    def create_blocked(
        ip_id: int | None,
        model_id: int,
        is_stream: bool | None,
        user_agent: str | None,
        status_code: int,
        fail_reason: str,
    ) -> RequestRecord:
        now = timezone.now()
        return RequestRecord.objects.create(
            user_ip_id=1,
            ip_id=ip_id,
            send_time=now,
            end_time=now,
            latency=0,
            model_id=model_id,
            input_token_cnt=0,
            output_token_cnt=0,
            task_status="failed",
            status=_status_text(status_code),
            fail_reason=fail_reason[:200],
            is_stream=is_stream,
            user_agent=(user_agent or "")[:500],
            attempt_count=0,
            prefix_cache=0.0,
            last_match=None,
        )

    @staticmethod
    def finish(
        record: RequestRecord,
        http_status: int,
        reason: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        target_pod_ip: str | None = None,
        model_id: int | None = None,
        task_status: str | None = None,
        attempt_count: int | None = None,
    ) -> None:
        end_time = timezone.now()
        record.end_time = end_time
        record.latency = int((end_time - record.send_time).total_seconds() * 1000)
        record.status = _status_text(http_status)
        record.task_status = task_status or ("success" if 200 <= http_status < 300 else "failed")
        record.fail_reason = None if record.task_status == "success" else reason[:200]
        record.input_token_cnt = input_tokens or 0
        record.output_token_cnt = output_tokens or 0
        update_fields = [
            "end_time",
            "latency",
            "status",
            "task_status",
            "fail_reason",
            "input_token_cnt",
            "output_token_cnt",
        ]
        if target_pod_ip:
            record.target_pod_ip = target_pod_ip[:500]
            update_fields.append("target_pod_ip")
        if model_id is not None:
            record.model_id = model_id
            update_fields.append("model_id")
        if attempt_count is not None:
            record.attempt_count = attempt_count
            update_fields.append("attempt_count")
        record.save(update_fields=update_fields)

    @staticmethod
    def record_attempt(
        record: RequestRecord,
        target_pod_ip: str | None,
        attempt_count: int,
        prefix_cache: float | None = None,
        last_match: int | None = None,
    ) -> None:
        record.attempt_count = attempt_count
        update_fields = ["attempt_count"]
        if target_pod_ip:
            record.target_pod_ip = target_pod_ip[:500]
            update_fields.append("target_pod_ip")
        if prefix_cache is not None:
            record.prefix_cache = prefix_cache
            update_fields.append("prefix_cache")
        record.last_match = last_match
        update_fields.append("last_match")
        record.save(update_fields=update_fields)

    @staticmethod
    def cleanup_stale(model_id: int | None = None, threshold_minutes: int = 20) -> int:
        from router.repositories.servers import ServerRepository

        cutoff = timezone.now() - timedelta(minutes=threshold_minutes)
        qs = RequestRecord.objects.filter(task_status="processing", send_time__lt=cutoff)
        if model_id:
            qs = qs.filter(model_id=model_id)
        target_counts = {
            row["target_pod_ip"]: row["count"]
            for row in qs.exclude(target_pod_ip__isnull=True)
            .values("target_pod_ip")
            .annotate(count=models.Count("id"))
        }
        updated = qs.update(task_status="incomplete", end_time=timezone.now(), fail_reason="stale processing")
        if target_counts:
            ServerRepository.decrement_workload_by_targets(target_counts)
        return updated

    @staticmethod
    def count_processing(ip_id: int, model_id: int) -> int:
        return RequestRecord.objects.filter(ip_id=ip_id, model_id=model_id, task_status="processing").count()

    @staticmethod
    def count_processing_by_targets(targets: list[str]) -> dict[str, int]:
        if not targets:
            return {}
        return {
            row["target_pod_ip"]: row["count"]
            for row in RequestRecord.objects.filter(task_status="processing", target_pod_ip__in=targets)
            .values("target_pod_ip")
            .annotate(count=models.Count("id"))
        }

    @staticmethod
    def count_distinct_ips(start: datetime, end: datetime) -> int:
        return RequestRecord.objects.filter(send_time__gte=start, send_time__lte=end, ip_id__isnull=False).values("ip_id").distinct().count()

    @staticmethod
    def count_success_requests(start: datetime, end: datetime) -> int:
        return RequestRecord.objects.filter(send_time__gte=start, send_time__lte=end, task_status="success").count()

    @staticmethod
    def count_success_requests_by_model(start: datetime, end: datetime, model_id: int) -> int:
        return RequestRecord.objects.filter(send_time__gte=start, send_time__lte=end, task_status="success", model_id=model_id).count()

    @staticmethod
    def count_success_requests_grouped_by_model(start: datetime, end: datetime, model_ids: list[int]) -> dict[int, int]:
        if not model_ids:
            return {}
        return {
            row["model_id"]: row["count"]
            for row in RequestRecord.objects.filter(send_time__gte=start, send_time__lte=end, task_status="success", model_id__in=model_ids)
            .values("model_id")
            .annotate(count=models.Count("id"))
        }

    @staticmethod
    def average_latency_by_bucket(start: datetime, end: datetime, bucket_expr, model_id: int | None = None) -> dict:
        qs = RequestRecord.objects.filter(send_time__gte=start, send_time__lte=end, task_status="success", latency__isnull=False)
        if model_id is not None:
            qs = qs.filter(model_id=model_id)
        return {
            row["bucket"]: row["avg_latency"]
            for row in qs.annotate(bucket=bucket_expr).values("bucket").annotate(avg_latency=models.Avg("latency")).order_by("bucket")
        }

    @staticmethod
    def count_success_by_bucket(start: datetime, end: datetime, model_id: int, bucket_expr) -> dict:
        return {
            row["bucket"]: row["count"]
            for row in RequestRecord.objects.filter(send_time__gte=start, send_time__lte=end, task_status="success", model_id=model_id)
            .annotate(bucket=bucket_expr)
            .values("bucket")
            .annotate(count=models.Count("id"))
            .order_by("bucket")
        }

    @staticmethod
    def count_distinct_ips_by_bucket(start: datetime, end: datetime, model_id: int, bucket_expr) -> dict:
        return {
            row["bucket"]: row["count"]
            for row in RequestRecord.objects.filter(
                send_time__gte=start,
                send_time__lte=end,
                task_status="success",
                model_id=model_id,
                ip_id__isnull=False,
            )
            .annotate(bucket=bucket_expr)
            .values("bucket")
            .annotate(count=models.Count("ip_id", distinct=True))
            .order_by("bucket")
        }

    @staticmethod
    def latency_rows_for_boxplot(start: datetime, end: datetime, model_ids: list[int]) -> list[dict]:
        if not model_ids:
            return []
        return list(
            RequestRecord.objects.filter(
                send_time__gte=start,
                send_time__lte=end,
                task_status="success",
                latency__isnull=False,
                model_id__in=model_ids,
            ).values("model_id", "send_time", "latency")
        )
