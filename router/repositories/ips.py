from __future__ import annotations

from django.utils import timezone

from router.models import IP


class IPRepository:
    @staticmethod
    def get_or_create(ip: str) -> tuple[IP, bool]:
        now = timezone.now()
        return IP.objects.get_or_create(
            ip=ip,
            defaults={"concurrent_multiplier": 1.0, "created_at": now, "updated_at": now},
        )

    @staticmethod
    def all_active() -> list[IP]:
        return list(IP.objects.filter(deleted_at__isnull=True).order_by("id"))
