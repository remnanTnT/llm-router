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
def test_mr_live_review_list_valid():
    MrLiveReview.objects.create(**_base_payload(discussion_id="v1", is_valid_ai_comment=True, rejected=False))
    MrLiveReview.objects.create(**_base_payload(discussion_id="i1", is_valid_ai_comment=False, rejected=True))
    MrLiveReview.objects.create(**_base_payload(discussion_id="n1", is_valid_ai_comment=False, rejected=False))
    # other branch / project, ignored
    MrLiveReview.objects.create(**_base_payload(discussion_id="d1", target_branch="dev", is_valid_ai_comment=True))
    MrLiveReview.objects.create(**_base_payload(discussion_id="x1", project_name="proj_b", is_valid_ai_comment=True))

    client = Client()
    response = client.get(
        "/api/mr_live_review/list",
        {"project_name": "proj_a", "target_branch": "main", "type": "valid"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert len(body["data"]) == 1
    row = body["data"][0]
    assert row == {
        "state": "opened",
        "merge_request_iid": 1,
        "merge_url": "http://example.com/mr/1",
        "assignee": "user1",
        "resolved_by_committer": "user2",
        "severity_cn": "高",
        "code": "print(1)",
        "comment": "test comment",
        "categorys": "bug",
        "fix_suggestion": "fix it",
        "confidence_score": "0.9",
        "line": 10,
        "created_at": "2023-01-01T00:00:00Z",
    }


@pytest.mark.django_db
def test_mr_live_review_list_invalid_and_no_reply():
    MrLiveReview.objects.create(**_base_payload(discussion_id="v1", is_valid_ai_comment=True, rejected=False))
    MrLiveReview.objects.create(**_base_payload(discussion_id="i1", is_valid_ai_comment=False, rejected=True))
    MrLiveReview.objects.create(**_base_payload(discussion_id="n1", is_valid_ai_comment=False, rejected=False))

    client = Client()
    invalid = client.get(
        "/api/mr_live_review/list",
        {"project_name": "proj_a", "target_branch": "main", "type": "invalid"},
    ).json()
    assert [r["state"] for r in invalid["data"]] == ["opened"]
    assert len(invalid["data"]) == 1

    no_reply = client.get(
        "/api/mr_live_review/list",
        {"project_name": "proj_a", "target_branch": "main", "type": "no_reply"},
    ).json()
    assert len(no_reply["data"]) == 1


@pytest.mark.django_db
def test_mr_live_review_list_missing_params():
    client = Client()
    assert client.get("/api/mr_live_review/list", {"target_branch": "main", "type": "valid"}).status_code == 400
    assert client.get("/api/mr_live_review/list", {"project_name": "proj_a", "type": "valid"}).status_code == 400


@pytest.mark.django_db
def test_mr_live_review_list_invalid_type():
    client = Client()
    response = client.get(
        "/api/mr_live_review/list",
        {"project_name": "proj_a", "target_branch": "main", "type": "bogus"},
    )
    assert response.status_code == 400
    assert "type must be one of" in response.json()["error"]
