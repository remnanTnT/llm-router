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

    @staticmethod
    def list_all(page: int | None = None, page_size: int | None = None) -> tuple[list[dict], int]:
        """
        获取白名单列表，支持分页。

        Args:
            page: 页码（从1开始），None表示返回全量数据
            page_size: 每页条数，None表示返回全量数据

        Returns:
            (数据列表, 总记录数)
        """
        # 基础查询，按更新时间倒序排列
        queryset = Whitelist.objects.all().order_by('-update_time', '-id')

        # 获取总数
        total = queryset.count()

        # 如果提供了分页参数，应用分页
        if page is not None and page_size is not None:
            offset = (page - 1) * page_size
            queryset = queryset[offset:offset + page_size]

        # 转换为字典列表
        data = [
            {
                "id": item.id,
                "employee_no": item.employee_no,
                "user_name": item.user_name,
                "is_allowed": item.is_allowed,
                "update_time": item.update_time.strftime("%Y-%m-%d %H:%M:%S") if item.update_time else None,
            }
            for item in queryset
        ]

        return data, total
