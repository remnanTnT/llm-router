from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from router.models import UserIP


class UserIPRepository:
    @staticmethod
    def get_by_ip_id(ip_id: int) -> UserIP | None:
        return UserIP.objects.filter(ip_id=ip_id, is_valid=True, deleted_at__isnull=True).first()

    @staticmethod
    def get_by_employee_no(employee_no: str) -> UserIP | None:
        return UserIP.objects.filter(employee_no=employee_no, is_valid=True, deleted_at__isnull=True).first()

    @staticmethod
    def get_ip_backed_by_employee_no(employee_no: str) -> UserIP | None:
        return UserIP.objects.filter(
            employee_no=employee_no,
            ip_id__gt=0,
            is_valid=True,
            deleted_at__isnull=True,
        ).first()

    @staticmethod
    def exists_by_ip_id(ip_id: int) -> bool:
        return UserIP.objects.filter(ip_id=ip_id, deleted_at__isnull=True).exists()

    @staticmethod
    def create_or_update(
        ip_id: int,
        user_name: str = "",
        user_charge: str = "",
        employee_no: str = "",
        department_id: int | None = None,
    ) -> UserIP:
        now = timezone.now()
        obj, created = UserIP.objects.get_or_create(
            ip_id=ip_id,
            defaults={
                "user_name": user_name,
                "user_charge": user_charge,
                "employee_no": employee_no,
                "department_id": department_id,
                "is_valid": True,
                "created_at": now,
                "updated_at": now,
            },
        )
        if not created:
            obj.user_name = user_name
            obj.user_charge = user_charge
            obj.employee_no = employee_no
            obj.department_id = department_id
            obj.is_valid = True
            obj.updated_at = now
            obj.save(update_fields=["user_name", "user_charge", "employee_no", "department_id", "is_valid", "updated_at"])
        return obj

    @staticmethod
    @transaction.atomic
    def register_api_key(
        apikey: str,
        employee_no: str,
        user_charge: str,
        department_id: int | None,
    ) -> tuple[UserIP, str]:
        now = timezone.now()
        employee_rows = UserIP.objects.select_for_update().filter(employee_no=employee_no)
        active_key = employee_rows.filter(
            is_valid=True,
            deleted_at__isnull=True,
        ).exclude(apikey="").first()

        if active_key is not None and active_key.apikey == apikey:
            return active_key, "reused"

        if UserIP.objects.select_for_update().filter(apikey=apikey).exists():
            raise APIKeyConflict("apikey is already registered")

        inherited_vip = employee_rows.filter(
            is_valid=True,
            deleted_at__isnull=True,
            vip=True,
        ).exists()

        action = "created"
        if active_key is not None:
            active_key.is_valid = False
            active_key.deleted_at = now
            active_key.updated_at = now
            active_key.save(update_fields=["is_valid", "deleted_at", "updated_at"])
            action = "replaced"

        row = UserIP.objects.create(
            ip_id=0,
            apikey=apikey,
            vip=inherited_vip,
            user_name="",
            user_charge=user_charge,
            employee_no=employee_no,
            department_id=department_id,
            is_valid=True,
            created_at=now,
            updated_at=now,
        )
        return row, action


class APIKeyConflict(Exception):
    pass
