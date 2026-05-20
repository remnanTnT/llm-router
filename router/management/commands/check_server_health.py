from django.core.management.base import BaseCommand

from router.repositories.servers import ServerRepository
from router.services.server_health import ServerHealthService


class Command(BaseCommand):
    help = "Check configured upstream servers and update health status."

    def add_arguments(self, parser):
        parser.add_argument("--recover-offline", action="store_true", help="Mark offline servers online again when their health check passes.")
        parser.add_argument("--server-id", type=int, help="Check only one server id.")

    def handle(self, *args, **options):
        recover_offline = options.get("recover_offline", False)
        server_id = options.get("server_id")

        servers = ServerRepository.list_all_active()
        if server_id is not None:
            servers = [server for server in servers if server.id == server_id]
        if not recover_offline:
            servers = [server for server in servers if server.is_online]

        service = ServerHealthService()
        for server in servers:
            healthy = service.check_once(server, recover_offline=recover_offline)
            status = "healthy" if healthy else "unhealthy"
            self.stdout.write(f"server {server.id} {server.base_url}: {status}")
