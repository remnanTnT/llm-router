from __future__ import annotations

from django.db.models import Count, Q

from router.models import MrLiveReview

# Maps the public ``type`` query value to the model filter that selects it.
TYPE_FILTERS = {
    "valid": Q(is_valid_ai_comment=True),
    "invalid": Q(rejected=True),
    "no_reply": Q(is_valid_ai_comment=False, rejected=False),
}

# Fields exposed by ``list_by_type`` (model field name -> output key).
DETAIL_FIELDS = {
    "state": "state",
    "merge_request_iid": "merge_request_iid",
    "merge_url": "merge_url",
    "assignee": "assignee",
    "resolved_by_committer": "resolved_by_committer",
    "severity_cn": "severity_cn",
    "code": "code",
    "comment": "comment",
    "categories": "categorys",
    "fix_suggestion": "fix_suggestion",
    "confidence_score": "confidence_score",
    "line": "line",
    "created_at": "created_at",
}


class MrLiveReviewRepository:
    @staticmethod
    def list_by_type(project_name: str, target_branch: str, review_type: str) -> list[dict]:
        """Return review detail rows for a project/branch filtered by type.

        ``review_type`` is one of ``valid``, ``invalid`` or ``no_reply`` (see
        :data:`TYPE_FILTERS`). Each row exposes the fields in
        :data:`DETAIL_FIELDS`, keyed by their public output name.
        """
        rows = (
            MrLiveReview.objects.filter(
                project_name=project_name,
                target_branch=target_branch,
            )
            .filter(TYPE_FILTERS[review_type])
            .values(*DETAIL_FIELDS.keys())
            .order_by("-created_at")
        )
        return [{out: row[field] for field, out in DETAIL_FIELDS.items()} for row in rows]

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
