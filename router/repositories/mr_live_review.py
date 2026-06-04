from __future__ import annotations

import re
from datetime import datetime, timedelta

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
    "diff_file": "diff_file",
    "severity_cn": "severity_cn",
    "code": "code",
    "comment": "comment",
    "categories": "categorys",
    "fix_suggestion": "fix_suggestion",
    "confidence_score": "confidence_score",
    "line": "line",
    "created_at": "created_at",
}


def _parse_created_at_with_timezone(created_at_str: str) -> datetime | None:
    """Parse created_at string and convert to Beijing time if needed.

    Handles formats like "2026-05-28T15:10:02.093+8:00" or "2026-05-28 15:10:02".
    Returns a datetime object in Beijing timezone (+08:00).
    """
    if not created_at_str:
        return None

    # Pattern to extract datetime and timezone
    # Matches: YYYY-MM-DD[T or space]HH:MM:SS[.microseconds][+/-HH:MM or +/-H:MM]
    pattern = r'(\d{4}-\d{2}-\d{2})[\sT](\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:([+-])(\d{1,2}):?(\d{2}))?'
    match = re.match(pattern, str(created_at_str))

    if not match:
        return None

    date_part = match.group(1)
    time_part = match.group(2)
    tz_sign = match.group(3)
    tz_hours = match.group(4)
    tz_minutes = match.group(5)

    # Parse the datetime without timezone
    dt = datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")

    # If timezone info exists, adjust to Beijing time (+08:00)
    if tz_sign and tz_hours:
        offset_hours = int(tz_hours)
        offset_minutes = int(tz_minutes) if tz_minutes else 0

        # Calculate total offset in hours
        total_offset = offset_hours + offset_minutes / 60
        if tz_sign == '-':
            total_offset = -total_offset

        # Convert to Beijing time (UTC+8)
        beijing_offset = 8.0
        offset_diff = beijing_offset - total_offset
        dt = dt + timedelta(hours=offset_diff)

    return dt


class MrLiveReviewRepository:
    @staticmethod
    def count_by_date(
        project_name: str,
        target_branch: str | None,
        stats_type: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        """Count reviews by date for a given project and stats type.

        Args:
            project_name: The project to filter by
            target_branch: The target branch to filter by, or "total" for all branches
            stats_type: One of "valid", "invalid", "no_reply", "total"
            start_time: Start of the date range (Beijing time)
            end_time: End of the date range (Beijing time)

        Returns:
            List of dicts with "date" and "count" keys, ordered by date
        """
        queryset = MrLiveReview.objects.filter(project_name=project_name)

        # Filter by target_branch if not "total"
        if target_branch and target_branch != "total":
            queryset = queryset.filter(target_branch=target_branch)

        # Get all records
        records = queryset.values("created_at")

        # Parse dates and filter by time range, then count by date
        date_counts = {}
        for record in records:
            created_at_str = record["created_at"]
            dt = _parse_created_at_with_timezone(created_at_str)

            if dt is None:
                continue

            # Check if within time range
            if dt < start_time or dt > end_time:
                continue

            date_key = dt.strftime("%Y-%m-%d")

            if date_key not in date_counts:
                date_counts[date_key] = {"valid": 0, "invalid": 0, "no_reply": 0, "total": 0}

            date_counts[date_key]["total"] += 1

        # Now get the actual counts for each type
        for record in queryset.values("created_at", "is_valid_ai_comment", "rejected"):
            created_at_str = record["created_at"]
            dt = _parse_created_at_with_timezone(created_at_str)

            if dt is None:
                continue

            if dt < start_time or dt > end_time:
                continue

            date_key = dt.strftime("%Y-%m-%d")

            if record["is_valid_ai_comment"]:
                date_counts[date_key]["valid"] += 1
            elif record["rejected"]:
                date_counts[date_key]["invalid"] += 1
            else:
                date_counts[date_key]["no_reply"] += 1

        # Build result list
        result = []
        for date_key in sorted(date_counts.keys()):
            counts = date_counts[date_key]
            result.append({
                "date": date_key,
                "count": counts.get(stats_type, 0)
            })

        return result

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

    @staticmethod
    def count_by_confidence_score(project_name: str) -> list[dict]:
        """Aggregate review counts per confidence_score for a given project.

        Each row contains the confidence_score and the counts of valid
        (is_valid_ai_comment), invalid (rejected) and no_reply
        (neither valid nor rejected) reviews.
        """
        return list(
            MrLiveReview.objects.filter(project_name=project_name)
            .values("confidence_score")
            .annotate(
                valid=Count("id", filter=Q(is_valid_ai_comment=True)),
                invalid=Count("id", filter=Q(rejected=True)),
                no_reply=Count("id", filter=Q(is_valid_ai_comment=False, rejected=False)),
            )
            .order_by("confidence_score")
        )

    @staticmethod
    def list_by_type_and_confidence(
        project_name: str,
        confidence_score: str | None,
        review_type: str,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[dict], int]:
        """Return a page of review detail rows plus the total row count.

        Similar to ``list_by_type`` but filters by ``confidence_score`` instead
        of ``target_branch``. ``confidence_score`` can be ``None`` or empty string
        to filter records where confidence_score is null or empty.

        ``review_type`` is one of ``valid``, ``invalid`` or ``no_reply`` (see
        :data:`TYPE_FILTERS`). Rows are ordered by ``created_at`` descending
        (newest first). Each row exposes the fields in :data:`DETAIL_FIELDS`,
        keyed by their public output name.

        ``page`` is 1-based and ``page_size`` is the number of rows per page.
        Returns ``(rows, total)`` where ``total`` is the unpaginated count.
        """
        queryset = MrLiveReview.objects.filter(project_name=project_name)

        # Handle confidence_score filtering, including None and empty string cases
        if confidence_score is None or confidence_score == "":
            queryset = queryset.filter(Q(confidence_score__isnull=True) | Q(confidence_score=""))
        else:
            queryset = queryset.filter(confidence_score=confidence_score)

        queryset = queryset.filter(TYPE_FILTERS[review_type]).order_by("-created_at")

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
