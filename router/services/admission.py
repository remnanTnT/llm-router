from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import ClassVar

from router.config import APP_CONFIG
from router.models import IP, Model
from router.repositories.departments import DepartmentRepository
from router.repositories.requests import RequestRepository
from router.repositories.user_ips import UserIPRepository
from router.repositories.whitelist import WhitelistRepository


@dataclass
class AdmissionResult:
    allowed: bool
    status_code: int = 200
    error_type: str | None = None
    message: str | None = None
    current: int | None = None
    limit: int | None = None


class AdmissionService:
    # model_id -> last_cleanup_timestamp
    _last_cleanup: ClassVar[dict[int, float]] = {}
    _cleanup_throttle_seconds: ClassVar[int] = 10

    def __init__(self):
        self.allow_missing_user_info = bool(APP_CONFIG.get("admission", {}).get("allow_when_user_info_missing", True))
        self.stale_minutes = int(APP_CONFIG.get("proxy", {}).get("stale_processing_minutes", 20))
        self.unknown_model_max_tokens = int(APP_CONFIG.get("proxy", {}).get("unknown_model_max_tokens", 20480))

    def check_permission(self, ip: IP) -> AdmissionResult:
        user_ip = UserIPRepository.get_by_ip_id(ip.id)
        if not user_ip:
            return AdmissionResult(True) if self.allow_missing_user_info else self._permission_denied()
        if user_ip.department_id is None:
            return AdmissionResult(True)
        department = DepartmentRepository.get(user_ip.department_id)
        if department is None:
            return AdmissionResult(True)
        if department.is_allowed == 1:
            return AdmissionResult(True)
        if WhitelistRepository.is_allowed(user_ip.employee_no):
            return AdmissionResult(True)
        return self._permission_denied()

    def check_max_tokens(self, requested: int | None, model: Model | None) -> AdmissionResult:
        if requested is None:
            return AdmissionResult(True)
        maximum = model.max_tokens if model else self.unknown_model_max_tokens
        if requested > maximum:
            return AdmissionResult(
                False,
                400,
                "invalid_request_error",
                f"The request generates too many tokens. Max allowed is {maximum}.",
            )
        return AdmissionResult(True)

    def check_concurrency(self, ip: IP, model: Model | None) -> AdmissionResult:
        if not model or model.concurrent_limit is None:
            return AdmissionResult(True)

        # Throttled Auto-Cleanup: Guarantee that stale requests (zombies) are 
        # cleared regularly without hitting the DB on every single request.
        now = time.time()
        last_run = self._last_cleanup.get(model.id, 0)
        if now - last_run > self._cleanup_throttle_seconds:
            RequestRepository.cleanup_stale(model_id=model.id, threshold_minutes=self.stale_minutes)
            self._last_cleanup[model.id] = now

        limit = max(1, math.ceil(model.concurrent_limit * (ip.concurrent_multiplier or 1.0)))
        current = RequestRepository.count_processing(ip.id, model.id)

        if current >= limit:
            # Final fallback: If we are still at the limit, do a targeted cleanup for this specific IP.
            # This ensures the user is never blocked by their own stale requests.
            cleaned = RequestRepository.cleanup_stale(model_id=model.id, threshold_minutes=self.stale_minutes, ip_id=ip.id)
            if cleaned > 0:
                current = RequestRepository.count_processing(ip.id, model.id)

        if current >= limit:
            return AdmissionResult(
                False,
                429,
                "concurrent_limit_exceeded",
                f"Current concurrency ({current}) has reached the limit ({limit})",
                current,
                limit,
            )
        return AdmissionResult(True)

    @staticmethod
    def _permission_denied() -> AdmissionResult:
        return AdmissionResult(False, 403, "permission_denied", "Access denied, you do not have permission")
