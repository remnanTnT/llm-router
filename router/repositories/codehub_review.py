from __future__ import annotations

from router.models import CodehubReview

class CodehubReviewRepository:
    @staticmethod
    def exists_by_hash(issue_hash: str) -> bool:
        return CodehubReview.objects.filter(issue_hash=issue_hash).exists()

    @staticmethod
    def create(data: dict) -> CodehubReview:
        return CodehubReview.objects.create(**data)
