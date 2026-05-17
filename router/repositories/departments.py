from router.models import Department


class DepartmentRepository:
    @staticmethod
    def get(department_id: int | None) -> Department | None:
        if department_id is None:
            return None
        return Department.objects.filter(id=department_id, deleted_at__isnull=True).first()
