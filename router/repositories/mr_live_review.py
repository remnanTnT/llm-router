from __future__ import annotations

import re

from django.db.models import Count, Q

from router.models import MrLiveReview

# Matches the date/time head of an ISO-ish timestamp, ignoring any
# fractional seconds and timezone suffix (which may be non-standard, e.g.
# ``+8:00``). Both ``T`` and space separators are accepted.
_CREATED_AT_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")


def _format_created_at(value):
    """Normalize a stored timestamp string to ``YYYY-MM-DD HH:MM:SS``.

    ``created_at`` is stored as a free-form string such as
    ``2026-05-28T15:10:02.093+8:00``. Return the plain date/time portion;
    if the value does not match the expected shape, return it unchanged.
    """
    if not value:
        return value
    match = _CREATED_AT_RE.search(str(value))
    if not match:
        return value
    return f"{match.group(1)} {match.group(2)}"

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
    def list_by_type(
        project_name: str,
        target_branch: str,
        review_type: str,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict], int]:
        """Return a page of review detail rows plus the total row count.

        ``review_type`` is one of ``valid``, ``invalid`` or ``no_reply`` (see
        :data:`TYPE_FILTERS`). Rows are ordered by ``created_at`` descending
        (newest first). Each row exposes the fields in :data:`DETAIL_FIELDS`,
        keyed by their public output name.

        ``page`` is 1-based and ``page_size`` is the number of rows per page.
        Returns ``(rows, total)`` where ``total`` is the unpaginated count.
        """
        queryset = (
            MrLiveReview.objects.filter(
                project_name=project_name,
                target_branch=target_branch,
            )
            .filter(TYPE_FILTERS[review_type])
            .order_by("-created_at")
        )
        total = queryset.count()
        offset = (page - 1) * page_size
        rows = queryset.values(*DETAIL_FIELDS.keys())[offset : offset + page_size]
        data = [
            {
                out: (_format_created_at(row[field]) if field == "created_at" else row[field])
                for field, out in DETAIL_FIELDS.items()
            }
            for row in rows
        ]
        return data, total

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
