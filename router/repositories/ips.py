from __future__ import annotations

from django.utils import timezone

from router.models import Ips


class IPRepository:
    @staticmethod
    def get_or_create(ip: str) -> tuple[Ips, bool]:
        now = timezone.now()
        return Ips.objects.get_or_create(
            ip=ip,
            defaults={"concurrent_multiplier": 1.0, "vip": False, "created_at": now, "updated_at": now},
        )

    @staticmethod
    def all_active() -> list[Ips]:
        return list(Ips.objects.filter(deleted_at__isnull=True).order_by("id"))

    @staticmethod
    def get_by_ip(ip: str) -> Ips | None:
        return Ips.objects.filter(ip=ip, deleted_at__isnull=True).first()

    @staticmethod
    def update_concurrent_multiplier(ip_id: int, multiplier: float) -> Ips:
        now = timezone.now()
        ip = Ips.objects.get(id=ip_id)
        ip.concurrent_multiplier = multiplier
        ip.updated_at = now
        ip.save(update_fields=["concurrent_multiplier", "updated_at"])
        return ip
