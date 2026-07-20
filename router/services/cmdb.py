from __future__ import annotations

import logging
import time

from router.config import APP_CONFIG
from router.repositories.ips import IPRepository

logger = logging.getLogger(__name__)


class CMDBService:
    def __init__(self):
        self.interval = float(APP_CONFIG.get("cmdb", {}).get("refresh_interval_between_ips_seconds", 1))

    def fetch_and_save_user(self, ip: str) -> None:
        try:
            IPRepository.get_or_create(ip)
        except Exception:
            logger.exception("dummy CMDB failed to ensure IP row for %s", ip)
            return
        logger.info("CMDB dummy mode: no user data fetched for %s", ip)

    def fetch_user_data_by_employee_no(self, employee_no: str) -> dict[str, str] | None:
        raise NotImplementedError("employee lookup is not implemented in the public CMDB adapter")

    def fetch_all_users(self) -> None:
        for row in IPRepository.all_active():
            self.fetch_and_save_user(row.ip)
            time.sleep(self.interval)
