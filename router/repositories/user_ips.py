from router.models import UserIP


class UserIPRepository:
    @staticmethod
    def get_by_ip_id(ip_id: int) -> UserIP | None:
        return UserIP.objects.filter(ip_id=ip_id, is_valid=True, deleted_at__isnull=True).first()
