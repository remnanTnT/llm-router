from __future__ import annotations

from django.utils import timezone

from router.models import Department


class DepartmentRepository:
    @staticmethod
    def get(department_id: int | None) -> Department | None:
        if department_id is None:
            return None
        return Department.objects.filter(id=department_id, deleted_at__isnull=True).first()

    @staticmethod
    def get_or_create(
        dept1: str = "",
        dept2: str = "",
        dept3: str = "",
        dept4: str = "",
    ) -> tuple[Department, bool]:
        now = timezone.now()
        return Department.objects.get_or_create(
            dept1=dept1,
            dept2=dept2,
            dept3=dept3,
            dept4=dept4,
            defaults={"created_at": now, "updated_at": now},
        )
