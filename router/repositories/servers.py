from __future__ import annotations

from datetime import timedelta

from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from router.models import Server


class ServerRepository:
    @staticmethod
    def list_by_model_id(model_id: int | None, vip: bool | None = None) -> list[Server]:
        """Return routable servers: online + (closed or cooldown-expired open/half_open).

        ``vip``: when ``True`` only VIP servers, when ``False`` only non-VIP servers,
        when ``None`` (default) both.
        """
        now = timezone.now()
        queryset = Server.objects.filter(deleted_at__isnull=True, is_online=True)
        if model_id:
            queryset = queryset.filter(model_id=model_id)
        else:
            queryset = queryset.filter(model_id__isnull=True)
        if vip is True:
            queryset = queryset.filter(vip=True)
        elif vip is False:
            queryset = queryset.filter(vip=False)
        servers = list(queryset.order_by("id"))
        return ServerRepository._filter_routable(servers, now)

    @staticmethod
    def list_all_online() -> list[Server]:
        now = timezone.now()
        servers = list(Server.objects.filter(deleted_at__isnull=True, is_online=True).order_by("id"))
        return ServerRepository._filter_routable(servers, now)

    @staticmethod
    def _filter_routable(servers: list[Server], now) -> list[Server]:
        """Include closed servers always; include open/half_open only if cooldown expired (and transition to half_open)."""
        routable = []
        for s in servers:
            if s.circuit_state == "closed":
                routable.append(s)
            elif s.circuit_state == "open":
                if s.last_state_change_at and (now - s.last_state_change_at).total_seconds() >= s.cooldown_seconds:
                    ServerRepository.transition_to_half_open(s)
                    routable.append(s)
            elif s.circuit_state == "half_open":
                routable.append(s)
        return routable

    @staticmethod
    def list_all_active() -> list[Server]:
        return list(Server.objects.filter(deleted_at__isnull=True).order_by("id"))

    @staticmethod
    def mark_checked(server: Server) -> None:
        now = timezone.now()
        Server.objects.filter(id=server.id).update(
            last_checked_at=now,
            updated_at=now,
        )
        server.last_checked_at = now
        server.updated_at = now

    @staticmethod
    def record_failure(server: Server, failure_threshold: int, base_cooldown_seconds: int, max_cooldown_seconds: int) -> None:
        """Increment failure counter. If threshold reached, open the circuit (or re-open with doubled cooldown)."""
        now = timezone.now()
        Server.objects.filter(id=server.id).update(
            consecutive_failures=F("consecutive_failures") + 1,
            last_failure_at=now,
            updated_at=now,
        )
        server.consecutive_failures += 1
        server.last_failure_at = now
        server.updated_at = now

        if server.consecutive_failures >= failure_threshold:
            if server.circuit_state == "half_open":
                # Failed during probe: double cooldown
                new_cooldown = min(server.cooldown_seconds * 2, max_cooldown_seconds)
            else:
                new_cooldown = min(
                    base_cooldown_seconds * (2 ** (server.consecutive_failures - failure_threshold)),
                    max_cooldown_seconds,
                )
            update_fields = {
                "circuit_state": "open",
                "last_state_change_at": now,
                "cooldown_seconds": new_cooldown,
            }
            if server.vip:
                update_fields["vip"] = False
                update_fields["vip_cooldown"] = None
            Server.objects.filter(id=server.id).update(**update_fields)
            server.circuit_state = "open"
            server.last_state_change_at = now
            server.cooldown_seconds = new_cooldown
            if server.vip:
                server.vip = False
                server.vip_cooldown = None

    @staticmethod
    def record_success(server: Server, base_cooldown_seconds: int) -> None:
        """Reset failure counter and close the circuit."""
        now = timezone.now()
        Server.objects.filter(id=server.id).update(
            consecutive_failures=0,
            circuit_state="closed",
            last_state_change_at=now,
            cooldown_seconds=base_cooldown_seconds,
            last_checked_at=now,
            updated_at=now,
        )
        server.consecutive_failures = 0
        server.circuit_state = "closed"
        server.last_state_change_at = now
        server.cooldown_seconds = base_cooldown_seconds
        server.last_checked_at = now
        server.updated_at = now

    @staticmethod
    def increment_workload(server: Server) -> None:
        Server.objects.filter(id=server.id).update(workload=F("workload") + 1)
        server.workload = (server.workload or 0) + 1

    @staticmethod
    def decrement_workload(server: Server) -> None:
        Server.objects.filter(id=server.id, workload__gt=0).update(workload=F("workload") - 1)
        server.workload = max((server.workload or 0) - 1, 0)

    @staticmethod
    def decrement_workload_by_targets(target_counts: dict[str, int]) -> None:
        for base_url, count in target_counts.items():
            if not base_url or count <= 0:
                continue
            Server.objects.filter(base_url=base_url).update(
                workload=Greatest(F("workload") - count, Value(0))
            )

    @staticmethod
    def transition_to_half_open(server: Server) -> None:
        now = timezone.now()
        Server.objects.filter(id=server.id).update(
            circuit_state="half_open",
            last_state_change_at=now,
            updated_at=now,
        )
        server.circuit_state = "half_open"
        server.last_state_change_at = now
        server.updated_at = now

    @staticmethod
    def promote_to_vip(server: Server) -> bool:
        """Atomically flip vip=False -> vip=True. Returns True if this caller did the flip."""
        now = timezone.now()
        updated = Server.objects.filter(id=server.id, vip=False).update(
            vip=True,
            vip_cooldown=None,
            updated_at=now,
        )
        if updated:
            server.vip = True
            server.vip_cooldown = None
            server.updated_at = now
        return bool(updated)

    @staticmethod
    def demote_to_normal(server: Server) -> None:
        now = timezone.now()
        Server.objects.filter(id=server.id).update(
            vip=False,
            vip_cooldown=None,
            updated_at=now,
        )
        server.vip = False
        server.vip_cooldown = None
        server.updated_at = now

    @staticmethod
    def mark_vip_cooldown(server: Server) -> bool:
        """Idempotent: only sets vip_cooldown when currently NULL. Returns True if this caller set it."""
        now = timezone.now()
        updated = Server.objects.filter(
            id=server.id, vip=True, vip_cooldown__isnull=True
        ).update(vip_cooldown=now, updated_at=now)
        if updated:
            server.vip_cooldown = now
            server.updated_at = now
        return bool(updated)

    @staticmethod
    def cancel_vip_cooldown(server: Server) -> bool:
        now = timezone.now()
        updated = Server.objects.filter(
            id=server.id, vip=True, vip_cooldown__isnull=False
        ).update(vip_cooldown=None, updated_at=now)
        if updated:
            server.vip_cooldown = None
            server.updated_at = now
        return bool(updated)

    @staticmethod
    def demote_expired_cooldowns(cooldown_seconds: int, model_id: int | None = None) -> int:
        """Demote any VIP servers whose cooldown started more than ``cooldown_seconds`` ago."""
        now = timezone.now()
        cutoff = now - timedelta(seconds=cooldown_seconds)
        queryset = Server.objects.filter(
            deleted_at__isnull=True,
            vip=True,
            vip_cooldown__isnull=False,
            vip_cooldown__lte=cutoff,
        )
        if model_id is not None:
            queryset = queryset.filter(model_id=model_id)
        return queryset.update(vip=False, vip_cooldown=None, updated_at=now)
