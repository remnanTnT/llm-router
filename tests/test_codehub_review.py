import pytest
import json
from django.test import Client
from router.models import CodehubReview

@pytest.mark.django_db
def test_create_codehub_review():
    client = Client()
    data = {
        "project_id": 1,
        "branch": "main",
        "issue_hash": "hash1",
        "mr_hash": "mr1",
        "file_path": "path/to/file",
        "line": 10,
        "body": "body text",
        "review_comment": "comment",
        "severity": "high",
        "categories": "bug",
        "fix_suggestion": "fix it",
        "created_at": "2023-01-01",
        "confidence_score": "0.9",
        "issue_url": "http://example.com"
    }
    
    # First creation
    response = client.post("/api/codehub_review", data=json.dumps(data), content_type="application/json")
    assert response.status_code == 200
    assert response.json()["message"] == "created"
    assert CodehubReview.objects.filter(issue_hash="hash1").count() == 1
    
    # Duplicate hash creation
    response = client.post("/api/codehub_review", data=json.dumps(data), content_type="application/json")
    assert response.status_code == 200
    assert response.json()["message"] == "skipped"
    assert CodehubReview.objects.filter(issue_hash="hash1").count() == 1

@pytest.mark.django_db
def test_create_codehub_review_missing_hash():
    client = Client()
    data = {
        "project_id": 1,
        "branch": "main"
        # missing issue_hash
    }
    response = client.post("/api/codehub_review", data=json.dumps(data), content_type="application/json")
    assert response.status_code == 400
    assert "issue_hash is required" in response.json()["error"]
