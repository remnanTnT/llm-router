from __future__ import annotations

from django.utils import timezone

from router.models import Server


class ServerRepository:
    @staticmethod
    def list_by_model_id(model_id: int | None) -> list[Server]:
        queryset = Server.objects.filter(deleted_at__isnull=True, is_online=True)
        if model_id:
            queryset = queryset.filter(model_id=model_id)
        else:
            queryset = queryset.filter(model_id__isnull=True)
        return list(queryset.order_by("id"))

    @staticmethod
    def list_all_active() -> list[Server]:
        return list(Server.objects.filter(deleted_at__isnull=True).order_by("id"))

    @staticmethod
    def mark_unhealthy(server: Server) -> None:
        now = timezone.now()
        Server.objects.filter(id=server.id).update(
            is_online=False,
            last_failure_at=now,
            updated_at=now,
        )
        server.is_online = False
        server.last_failure_at = now
        server.updated_at = now

    @staticmethod
    def mark_healthy(server: Server) -> None:
        now = timezone.now()
        Server.objects.filter(id=server.id).update(
            is_online=True,
            last_checked_at=now,
            updated_at=now,
        )
        server.is_online = True
        server.last_checked_at = now
        server.updated_at = now

    @staticmethod
    def mark_checked(server: Server) -> None:
        now = timezone.now()
        Server.objects.filter(id=server.id).update(
            last_checked_at=now,
            updated_at=now,
        )
        server.last_checked_at = now
        server.updated_at = now
