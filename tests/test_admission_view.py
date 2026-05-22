import json
import pytest
from django.test import Client
from router.models import Model

@pytest.mark.django_db
def test_deprecated_model_returns_400():
    Model.objects.create(
        model_name="deprecated-model",
        deprecation="This model is deprecated. Please use model-v2."
    )
    
    client = Client()
    response = client.post(
        "/v1/chat/completions",
        data=json.dumps({"model": "deprecated-model"}),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    data = response.json()
    assert data["error"]["message"] == "This model is deprecated. Please use model-v2."
    assert data["error"]["type"] == "invalid_request_error"

@pytest.mark.django_db
def test_normal_model_not_blocked_by_deprecation():
    Model.objects.create(
        model_name="normal-model",
        deprecation=None
    )
    
    client = Client()
    # Mocking parser to return normal-model
    response = client.post(
        "/v1/chat/completions",
        data=json.dumps({"model": "normal-model"}),
        content_type="application/json"
    )
    
    # It should pass deprecation check. 
    # It might fail later due to missing servers or other things, but not with the deprecation message.
    if response.status_code == 400:
        assert response.json()["error"]["message"] != "This model is deprecated. Please use model-v2."
