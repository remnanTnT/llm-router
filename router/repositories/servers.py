from __future__ import annotations

from django.db.models import F
from django.utils import timezone

from router.models import Server


class ServerRepository:
    @staticmethod
    def list_by_model_id(model_id: int | None) -> list[Server]:
        """Return routable servers: online + (closed or cooldown-expired open/half_open)."""
        now = timezone.now()
        queryset = Server.objects.filter(deleted_at__isnull=True, is_online=True)
        if model_id:
            queryset = queryset.filter(model_id=model_id)
        else:
            queryset = queryset.filter(model_id__isnull=True)
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
            elif s.circuit_state in ("open", "half_open"):
                if s.last_state_change_at and (now - s.last_state_change_at).total_seconds() >= s.cooldown_seconds:
                    ServerRepository.transition_to_half_open(s)
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
            Server.objects.filter(id=server.id).update(
                circuit_state="open",
                last_state_change_at=now,
                cooldown_seconds=new_cooldown,
            )
            server.circuit_state = "open"
            server.last_state_change_at = now
            server.cooldown_seconds = new_cooldown

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
