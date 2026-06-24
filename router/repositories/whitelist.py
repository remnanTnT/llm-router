from __future__ import annotations

from django.utils import timezone

from router.models import Whitelist


class WhitelistRepository:
    @staticmethod
    def is_allowed(employee_no: str | None) -> bool:
        if not employee_no:
            return False
        return Whitelist.objects.filter(employee_no=employee_no, is_allowed=1).exists()

    @staticmethod
    def upsert(employee_no: str, is_allowed: int, user_name: str | None = None) -> tuple[Whitelist, bool, bool]:
        row = Whitelist.objects.filter(employee_no=employee_no).first()
        now = timezone.now()
        if row is None:
            row = Whitelist.objects.create(
                employee_no=employee_no,
                is_allowed=is_allowed,
                user_name=user_name or "",
                update_time=now
            )
            return row, True, True

        # Check if anything changed
        changed = False
        update_fields = []

        if row.is_allowed != is_allowed:
            row.is_allowed = is_allowed
            update_fields.append("is_allowed")
            changed = True

        if user_name is not None and row.user_name != user_name:
            row.user_name = user_name
            update_fields.append("user_name")
            changed = True

        if not changed:
            return row, False, False

        row.update_time = now
        update_fields.append("update_time")
        row.save(update_fields=update_fields)
        return row, False, True
