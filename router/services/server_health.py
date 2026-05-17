from __future__ import annotations

from urllib.parse import urljoin

import requests

from router.config import APP_CONFIG
from router.models import Server
from router.repositories.servers import ServerRepository


class ServerHealthService:
    def __init__(self):
        lb_config = APP_CONFIG.get("load_balancer", {})
        self.timeout = float(lb_config.get("health_check_timeout_seconds", 2))

    def mark_failure(self, server: Server, reason: str) -> None:
        ServerRepository.mark_unhealthy(server)

    def check_once(self, server: Server, recover_offline: bool = False) -> bool:
        url = urljoin(server.base_url.rstrip("/") + "/", (server.health_path or "/healthy").lstrip("/"))
        try:
            response = requests.get(url, timeout=self.timeout)
        except requests.RequestException:
            ServerRepository.mark_checked(server)
            if server.is_online:
                ServerRepository.mark_unhealthy(server)
            return False

        if 200 <= response.status_code < 300:
            if server.is_online or recover_offline:
                ServerRepository.mark_healthy(server)
            else:
                ServerRepository.mark_checked(server)
            return True

        ServerRepository.mark_checked(server)
        if server.is_online:
            ServerRepository.mark_unhealthy(server)
        return False
