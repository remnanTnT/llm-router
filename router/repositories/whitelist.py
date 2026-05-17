from django.utils import timezone

from router.models import Whitelist


class WhitelistRepository:
    @staticmethod
    def is_allowed(employee_no: str | None) -> bool:
        if not employee_no:
            return False
        return Whitelist.objects.filter(employee_no=employee_no, is_allowed=1).exists()

    @staticmethod
    def upsert(employee_no: str, is_allowed: int) -> tuple[Whitelist, bool, bool]:
        row = Whitelist.objects.filter(employee_no=employee_no).first()
        now = timezone.now()
        if row is None:
            row = Whitelist.objects.create(employee_no=employee_no, is_allowed=is_allowed, update_time=now)
            return row, True, True
        if row.is_allowed == is_allowed:
            return row, False, False
        row.is_allowed = is_allowed
        row.update_time = now
        row.save(update_fields=["is_allowed", "update_time"])
        return row, False, True
