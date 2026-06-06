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
    
    # Verify fail_reason in DB matches
    from router.models import RequestRecord
    record = RequestRecord.objects.last()
    assert record.fail_reason == data["error"]["message"]

@pytest.mark.django_db
def test_max_tokens_fail_reason_matches():
    Model.objects.create(model_name="expensive-model", max_tokens=10)
    
    client = Client()
    response = client.post(
        "/v1/chat/completions",
        data=json.dumps({"model": "expensive-model", "max_tokens": 100}),
        content_type="application/json"
    )
    
    assert response.status_code == 400
    data = response.json()
    from router.models import RequestRecord
    record = RequestRecord.objects.last()
    assert record.fail_reason == data["error"]["message"]
    assert "too many tokens" in record.fail_reason


@pytest.mark.django_db
def test_unknown_model_returns_400():
    input_model_name = "user-requested-unknown-model"
    client = Client()
    response = client.post(
        "/v1/chat/completions",
        data=json.dumps({"model": input_model_name}),
        content_type="application/json"
    )

    assert response.status_code == 400
    data = response.json()
    assert data["error"]["message"] == f"Model {input_model_name} is not supported."
    assert data["error"]["type"] == "invalid_request_error"

    from router.models import RequestRecord
    record = RequestRecord.objects.last()
    assert record.status == "400 Bad Request"
    assert record.fail_reason == data["error"]["message"]


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
