import pytest
from django.test import Client


@pytest.fixture
def sample_reviews(db):
    from router.models import MrLiveReview

    reviews = [
        MrLiveReview(
            project_name="test_project",
            source="test",
            discussion_id="disc_1",
            is_ai_comment=True,
            is_valid_ai_comment=True,
            rejected=False,
            target_branch="main",
            state="open",
            merge_request_iid=1,
            merge_url="http://example.com/mr/1",
            assignee="user1",
            resolved_by_committer="",
            diff_file="test.py",
            severity="medium",
            severity_cn="中",
            body="test body",
            code="test code",
            comment="test comment",
            categories="bug",
            fix_suggestion="fix it",
            confidence_score="high",
            line=10,
            old_path="test.py",
            new_path="test.py",
            patchset_iid=1,
            author_name="author1",
            created_at="2026-06-01T10:00:00.000+8:00",
        ),
        MrLiveReview(
            project_name="test_project",
            source="test",
            discussion_id="disc_2",
            is_ai_comment=True,
            is_valid_ai_comment=False,
            rejected=True,
            target_branch="main",
            state="open",
            merge_request_iid=2,
            merge_url="http://example.com/mr/2",
            assignee="user2",
            resolved_by_committer="",
            diff_file="test2.py",
            severity="low",
            severity_cn="低",
            body="test body 2",
            code="test code 2",
            comment="test comment 2",
            categories="style",
            fix_suggestion="fix it 2",
            confidence_score="medium",
            line=20,
            old_path="test2.py",
            new_path="test2.py",
            patchset_iid=2,
            author_name="author2",
            created_at="2026-06-01T14:00:00.000+8:00",
        ),
        MrLiveReview(
            project_name="test_project",
            source="test",
            discussion_id="disc_3",
            is_ai_comment=True,
            is_valid_ai_comment=False,
            rejected=False,
            target_branch="main",
            state="open",
            merge_request_iid=3,
            merge_url="http://example.com/mr/3",
            assignee="user3",
            resolved_by_committer="",
            diff_file="test3.py",
            severity="high",
            severity_cn="高",
            body="test body 3",
            code="test code 3",
            comment="test comment 3",
            categories="security",
            fix_suggestion="fix it 3",
            confidence_score="low",
            line=30,
            old_path="test3.py",
            new_path="test3.py",
            patchset_iid=3,
            author_name="author3",
            created_at="2026-06-02T09:00:00.000+8:00",
        ),
        MrLiveReview(
            project_name="test_project",
            source="test",
            discussion_id="disc_4",
            is_ai_comment=True,
            is_valid_ai_comment=True,
            rejected=False,
            target_branch="develop",
            state="open",
            merge_request_iid=4,
            merge_url="http://example.com/mr/4",
            assignee="user4",
            resolved_by_committer="",
            diff_file="test4.py",
            severity="medium",
            severity_cn="中",
            body="test body 4",
            code="test code 4",
            comment="test comment 4",
            categories="performance",
            fix_suggestion="fix it 4",
            confidence_score="high",
            line=40,
            old_path="test4.py",
            new_path="test4.py",
            patchset_iid=4,
            author_name="author4",
            created_at="2026-06-02T15:00:00.000+8:00",
        ),
    ]

    for review in reviews:
        review.save()

    return reviews


@pytest.mark.django_db
def test_stats_by_date_valid(sample_reviews):
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "valid",
            "target_branch": "main",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]) == 2  # 2 dates
    assert data["data"][0]["date"] == "2026-06-01"
    assert data["data"][0]["count"] == 1  # 1 valid on 2026-06-01
    assert data["data"][1]["date"] == "2026-06-02"
    assert data["data"][1]["count"] == 0  # 0 valid on 2026-06-02 for main branch


@pytest.mark.django_db
def test_stats_by_date_invalid(sample_reviews):
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "invalid",
            "target_branch": "main",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"][0]["date"] == "2026-06-01"
    assert data["data"][0]["count"] == 1  # 1 invalid on 2026-06-01


@pytest.mark.django_db
def test_stats_by_date_no_reply(sample_reviews):
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "no_reply",
            "target_branch": "main",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"][0]["date"] == "2026-06-02"
    assert data["data"][0]["count"] == 1  # 1 no_reply on 2026-06-02


@pytest.mark.django_db
def test_stats_by_date_total(sample_reviews):
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "total",
            "target_branch": "main",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"][0]["date"] == "2026-06-01"
    assert data["data"][0]["count"] == 2  # 2 total on 2026-06-01 for main
    assert data["data"][1]["date"] == "2026-06-02"
    assert data["data"][1]["count"] == 1  # 1 total on 2026-06-02 for main


@pytest.mark.django_db
def test_stats_by_date_total_all_branches(sample_reviews):
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "total",
            "target_branch": "total",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"][0]["date"] == "2026-06-01"
    assert data["data"][0]["count"] == 2  # 2 total on 2026-06-01 (all branches)
    assert data["data"][1]["date"] == "2026-06-02"
    assert data["data"][1]["count"] == 2  # 2 total on 2026-06-02 (all branches)


@pytest.mark.django_db
def test_stats_by_date_accept_rate(sample_reviews):
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "accept_rate",
            "target_branch": "main",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    # 2026-06-01: 1 valid, 1 invalid => accept_rate = 1/(1+1) = 0.5
    assert data["data"][0]["date"] == "2026-06-01"
    assert data["data"][0]["accept_rate"] == 0.5


@pytest.mark.django_db
def test_stats_by_date_missing_stats():
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "target_branch": "main",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert "stats must be one of" in data["error"]


@pytest.mark.django_db
def test_stats_by_date_invalid_stats():
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "invalid_stats_type",
            "target_branch": "main",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert "stats must be one of" in data["error"]


@pytest.mark.django_db
def test_stats_by_date_missing_target_branch():
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "valid",
            "project_name": "test_project",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert "target_branch is required" in data["error"]


@pytest.mark.django_db
def test_stats_by_date_missing_project_name():
    client = Client()
    response = client.get(
        "/api/mr_live_review/stats_by_date",
        {
            "stats": "valid",
            "target_branch": "main",
            "start_date": "2026-06-01",
            "end_date": "2026-06-02",
        },
    )

    assert response.status_code == 400
    data = response.json()
    assert "project_name is required" in data["error"]
