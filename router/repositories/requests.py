from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.utils import timezone

from router.models import RequestRecord


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
        )

    @staticmethod
    def create_blocked(
        ip_id: int | None,
        model_id: int,
        is_stream: bool | None,
        user_agent: str | None,
        status: str,
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
            status=status[:50],
            fail_reason=fail_reason[:100],
            is_stream=is_stream,
            user_agent=(user_agent or "")[:500],
            attempt_count=0,
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
        record.status = f"{http_status} {reason}"[:50]
        record.task_status = task_status or ("success" if 200 <= http_status < 300 else "failed")
        record.fail_reason = None if record.task_status == "success" else reason[:100]
        record.input_token_cnt = input_tokens or 0
        record.output_token_cnt = output_tokens or 0
        if target_pod_ip:
            record.target_pod_ip = target_pod_ip[:500]
        if model_id is not None:
            record.model_id = model_id
        if attempt_count is not None:
            record.attempt_count = attempt_count
        record.save()

    @staticmethod
    def record_attempt(record: RequestRecord, target_pod_ip: str | None, attempt_count: int) -> None:
        record.attempt_count = attempt_count
        if target_pod_ip:
            record.target_pod_ip = target_pod_ip[:500]
        record.save(update_fields=["attempt_count", "target_pod_ip"] if target_pod_ip else ["attempt_count"])

    @staticmethod
    def cleanup_stale(model_id: int | None = None, threshold_minutes: int = 20) -> int:
        cutoff = timezone.now() - timedelta(minutes=threshold_minutes)
        qs = RequestRecord.objects.filter(task_status="processing", send_time__lt=cutoff)
        if model_id:
            qs = qs.filter(model_id=model_id)
        return qs.update(task_status="incomplete", end_time=timezone.now(), fail_reason="stale processing")

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
