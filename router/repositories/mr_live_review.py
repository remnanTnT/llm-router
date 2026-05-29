from __future__ import annotations

from django.db.models import Count, Q

from router.models import MrLiveReview


class MrLiveReviewRepository:
    @staticmethod
    def count_by_target_branch(project_name: str) -> list[dict]:
        """Aggregate review counts per target_branch for a given project.

        Each row contains the target_branch and the counts of valid
        (is_valid_ai_comment), invalid (rejected) and no_reply
        (neither valid nor rejected) reviews.
        """
        return list(
            MrLiveReview.objects.filter(project_name=project_name)
            .values("target_branch")
            .annotate(
                valid=Count("id", filter=Q(is_valid_ai_comment=True)),
                invalid=Count("id", filter=Q(rejected=True)),
                no_reply=Count("id", filter=Q(is_valid_ai_comment=False, rejected=False)),
            )
            .order_by("target_branch")
        )
