from datetime import timedelta

from django.utils import timezone

from router.models import Server
from router.repositories.servers import ServerRepository
from router.services.circuit_breaker import CircuitBreakerService


class TestCircuitBreakerFailureCounting:
    def test_single_failure_keeps_server_routable(self):
        server = Server.objects.create(base_url="http://s1.example", is_online=True)
        cb = CircuitBreakerService()

        cb.record_failure(server)

        server.refresh_from_db()
        assert server.circuit_state == "closed"
        assert server.consecutive_failures == 1
        # Server should still appear in routing
        assert server in ServerRepository.list_all_online()

    def test_two_failures_keeps_server_routable(self):
        server = Server.objects.create(base_url="http://s2.example", is_online=True)
        cb = CircuitBreakerService()

        cb.record_failure(server)
        cb.record_failure(server)

        server.refresh_from_db()
        assert server.circuit_state == "closed"
        assert server.consecutive_failures == 2
        assert server in ServerRepository.list_all_online()

    def test_third_failure_opens_circuit(self):
        server = Server.objects.create(base_url="http://s3.example", is_online=True)
        cb = CircuitBreakerService()

        cb.record_failure(server)
        cb.record_failure(server)
        cb.record_failure(server)

        server.refresh_from_db()
        assert server.circuit_state == "open"
        assert server.consecutive_failures == 3
        # Server should NOT appear in routing (cooldown not expired)
        assert server not in ServerRepository.list_all_online()

    def test_success_resets_failure_counter_and_closes_circuit(self):
        server = Server.objects.create(
            base_url="http://s4.example",
            is_online=True,
            consecutive_failures=2,
            circuit_state="half_open",
        )
        cb = CircuitBreakerService()

        cb.record_success(server)

        server.refresh_from_db()
        assert server.consecutive_failures == 0
        assert server.circuit_state == "closed"


class TestCircuitBreakerAdminControl:
    def test_offline_server_never_routed_regardless_of_circuit_state(self):
        Server.objects.create(base_url="http://admin-off.example", is_online=False, circuit_state="closed")

        assert ServerRepository.list_all_online() == []

    def test_offline_server_with_open_circuit_not_routed(self):
        Server.objects.create(base_url="http://admin-off2.example", is_online=False, circuit_state="open")

        assert ServerRepository.list_all_online() == []


class TestCircuitBreakerInlineProbe:
    def test_open_server_with_expired_cooldown_becomes_routable_as_half_open(self):
        server = Server.objects.create(
            base_url="http://probe1.example",
            is_online=True,
            circuit_state="open",
            consecutive_failures=3,
            last_state_change_at=timezone.now() - timedelta(seconds=60),
            cooldown_seconds=30,
        )

        # Cooldown expired: server should be included and transitioned to half_open
        online = ServerRepository.list_all_online()
        assert server in online
        server.refresh_from_db()
        assert server.circuit_state == "half_open"

    def test_open_server_before_cooldown_expires_not_routable(self):
        server = Server.objects.create(
            base_url="http://probe2.example",
            is_online=True,
            circuit_state="open",
            consecutive_failures=3,
            last_state_change_at=timezone.now() - timedelta(seconds=10),  # only 10s ago
            cooldown_seconds=30,  # needs 30s
        )

        # Cooldown NOT expired: server excluded
        online = ServerRepository.list_all_online()
        assert server not in online
        server.refresh_from_db()
        assert server.circuit_state == "open"  # unchanged

    def test_half_open_failure_reopens_with_doubled_cooldown(self):
        server = Server.objects.create(
            base_url="http://probe3.example",
            is_online=True,
            circuit_state="half_open",
            consecutive_failures=2,
            cooldown_seconds=30,
        )
        cb = CircuitBreakerService()

        cb.record_failure(server)

        server.refresh_from_db()
        assert server.circuit_state == "open"
        assert server.cooldown_seconds == 60  # doubled from 30

    def test_cooldown_capped_at_max(self):
        server = Server.objects.create(
            base_url="http://probe4.example",
            is_online=True,
            circuit_state="half_open",
            consecutive_failures=2,
            cooldown_seconds=2000,
        )
        cb = CircuitBreakerService()

        cb.record_failure(server)

        server.refresh_from_db()
        assert server.cooldown_seconds == 3000  # capped at max

    def test_half_open_success_closes_circuit(self):
        server = Server.objects.create(
            base_url="http://probe5.example",
            is_online=True,
            circuit_state="half_open",
            consecutive_failures=3,
            cooldown_seconds=60,
        )
        cb = CircuitBreakerService()

        cb.record_success(server)

        server.refresh_from_db()
        assert server.circuit_state == "closed"
        assert server.consecutive_failures == 0
        assert server.cooldown_seconds == 30  # reset to base
