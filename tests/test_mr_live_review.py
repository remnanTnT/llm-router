import json
import pytest
from django.test import Client
from router.models import MrLiveReview

@pytest.mark.django_db
def test_upsert_mr_live_review():
    client = Client()
    url = "/api/mr_live_review"
    
    # 1. Create new
    payload = {
        "project_name": "test_project",
        "source": "gitlab",
        "discussion_id": "disc_1",
        "is_ai_comment": True,
        "is_valid_ai_comment": True,
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
        "created_at": "2023-01-01T00:00:00Z"
    }
    
    response = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 200
    assert response.json()["message"] == "created"
    assert MrLiveReview.objects.count() == 1
    
    # 2. Skip (same state)
    response = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 200
    assert response.json()["message"] == "skipped"
    assert MrLiveReview.objects.count() == 1
    
    # 3. Update (different state)
    payload["state"] = "closed"
    response = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 200
    assert response.json()["message"] == "updated"
    assert MrLiveReview.objects.get(discussion_id="disc_1").state == "closed"
    assert MrLiveReview.objects.count() == 1

@pytest.mark.django_db
def test_upsert_mr_live_review_missing_id():
    client = Client()
    url = "/api/mr_live_review"
    payload = {"state": "opened"}
    response = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert "discussion_id is required" in response.json()["error"]

@pytest.mark.django_db
def test_upsert_mr_live_review_invalid_field():
    client = Client()
    url = "/api/mr_live_review"
    payload = {
        "discussion_id": "disc_invalid",
        "state": "opened",
        "unknown_field": "oops"
    }
    response = client.post(url, data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert "invalid fields: unknown_field" in response.json()["error"]
