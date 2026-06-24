from __future__ import annotations

from router.models import DailyMrReview

class DailyMrReviewRepository:
    @staticmethod
    def exists_by_hash(issue_hash: str) -> bool:
        return DailyMrReview.objects.filter(issue_hash=issue_hash).exists()

    @staticmethod
    def create(data: dict) -> DailyMrReview:
        return DailyMrReview.objects.create(**data)
