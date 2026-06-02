import json
import pytest
from django.test import Client
from router.models import MrLiveReview


def _base_payload(**overrides):
    payload = {
        "project_name": "proj_a",
        "source": "gitlab",
        "discussion_id": "disc",
        "is_ai_comment": True,
        "is_valid_ai_comment": False,
        "rejected": False,
        "target_branch": "main",
        "state": "opened",
        "merge_request_iid": 1,
        "merge_url": "http://example.com/mr/1",
        "assignee": "user1",
        "resolved_by_committer": "user2",
        "diff_file": "file1.py",
        "severity": "high",
        "severity_cn": "高",
        "body": "test body",
        "code": "print(1)",
        "comment": "test comment",
        "categories": "bug",
        "fix_suggestion": "fix it",
        "confidence_score": "0.9",
        "line": 10,
        "old_path": "file1.py",
        "new_path": "file1.py",
        "patchset_iid": 1,
        "author_name": "author1",
        "created_at": "2023-01-01T00:00:00Z",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_mr_live_review_stats_aggregation():
    # main: 2 valid, 1 invalid, 1 no_reply
    MrLiveReview.objects.create(**_base_payload(discussion_id="m1", target_branch="main", is_valid_ai_comment=True, rejected=False))
    MrLiveReview.objects.create(**_base_payload(discussion_id="m2", target_branch="main", is_valid_ai_comment=True, rejected=False))
    MrLiveReview.objects.create(**_base_payload(discussion_id="m3", target_branch="main", is_valid_ai_comment=False, rejected=True))
    MrLiveReview.objects.create(**_base_payload(discussion_id="m4", target_branch="main", is_valid_ai_comment=False, rejected=False))
    # dev: 1 valid, 0 invalid, 0 no_reply
    MrLiveReview.objects.create(**_base_payload(discussion_id="d1", target_branch="dev", is_valid_ai_comment=True, rejected=False))
    # another project, should be ignored
    MrLiveReview.objects.create(**_base_payload(discussion_id="x1", project_name="proj_b", target_branch="main", is_valid_ai_comment=True, rejected=False))

    client = Client()
    response = client.get("/api/mr_live_review/stats", {"project_name": "proj_a"})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200

    data = {row["target_branch"]: row for row in body["data"]}
    assert data["main"] == {
        "target_branch": "main",
        "valid": 2,
        "invalid": 1,
        "no_reply": 1,
        "accept_rate": round(2 / 3, 4),
    }
    assert data["dev"] == {
        "target_branch": "dev",
        "valid": 1,
        "invalid": 0,
        "no_reply": 0,
        "accept_rate": 1.0,
    }

    assert body["total"] == {
        "target_branch": "总计",
        "valid": 3,
        "invalid": 1,
        "no_reply": 1,
        "accept_rate": round(3 / 4, 4),
    }


@pytest.mark.django_db
def test_mr_live_review_stats_missing_project_name():
    client = Client()
    response = client.get("/api/mr_live_review/stats")
    assert response.status_code == 400
    assert "project_name is required" in response.json()["error"]


@pytest.mark.django_db
def test_mr_live_review_stats_empty():
    client = Client()
    response = client.get("/api/mr_live_review/stats", {"project_name": "no_such_project"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["total"] == {
        "target_branch": "总计",
        "valid": 0,
        "invalid": 0,
        "no_reply": 0,
        "accept_rate": 0.0,
    }


@pytest.mark.django_db
def test_mr_live_review_stats_by_confidence_aggregation():
    # confidence_score 0.9: 2 valid, 1 invalid, 1 no_reply
    MrLiveReview.objects.create(**_base_payload(discussion_id="c1", confidence_score="0.9", is_valid_ai_comment=True, rejected=False))
    MrLiveReview.objects.create(**_base_payload(discussion_id="c2", confidence_score="0.9", is_valid_ai_comment=True, rejected=False))
    MrLiveReview.objects.create(**_base_payload(discussion_id="c3", confidence_score="0.9", is_valid_ai_comment=False, rejected=True))
    MrLiveReview.objects.create(**_base_payload(discussion_id="c4", confidence_score="0.9", is_valid_ai_comment=False, rejected=False))
    # confidence_score 0.8: 1 valid, 0 invalid, 1 no_reply
    MrLiveReview.objects.create(**_base_payload(discussion_id="c5", confidence_score="0.8", is_valid_ai_comment=True, rejected=False))
    MrLiveReview.objects.create(**_base_payload(discussion_id="c6", confidence_score="0.8", is_valid_ai_comment=False, rejected=False))
    # another project, should be ignored
    MrLiveReview.objects.create(**_base_payload(discussion_id="c7", project_name="proj_b", confidence_score="0.9", is_valid_ai_comment=True, rejected=False))

    client = Client()
    response = client.get("/api/mr_live_review/stats_by_confidence", {"project_name": "proj_a"})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200

    data = {row["confidence_score"]: row for row in body["data"]}
    assert data["0.8"] == {
        "confidence_score": "0.8",
        "valid": 1,
        "invalid": 0,
        "no_reply": 1,
        "total": 2,
        "accept_rate": 1.0,
    }
    assert data["0.9"] == {
        "confidence_score": "0.9",
        "valid": 2,
        "invalid": 1,
        "no_reply": 1,
        "total": 4,
        "accept_rate": round(2 / 3, 4),
    }

    assert body["total"] == {
        "confidence_score": "总计",
        "valid": 3,
        "invalid": 1,
        "no_reply": 2,
        "total": 6,
        "accept_rate": round(3 / 4, 4),
    }


@pytest.mark.django_db
def test_mr_live_review_stats_by_confidence_missing_project_name():
    client = Client()
    response = client.get("/api/mr_live_review/stats_by_confidence")
    assert response.status_code == 400
    assert "project_name is required" in response.json()["error"]


@pytest.mark.django_db
def test_mr_live_review_stats_by_confidence_empty():
    client = Client()
    response = client.get("/api/mr_live_review/stats_by_confidence", {"project_name": "no_such_project"})
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["total"] == {
        "confidence_score": "总计",
        "valid": 0,
        "invalid": 0,
        "no_reply": 0,
        "total": 0,
        "accept_rate": 0.0,
    }
