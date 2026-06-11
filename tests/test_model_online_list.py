import pytest
from django.test import Client

from router.models import Model


@pytest.mark.django_db
def test_model_online_list_returns_only_non_deprecated():
    client = Client()

    # Create models with different deprecation statuses
    Model.objects.create(model_name="model-active-1", deprecation=None)
    Model.objects.create(model_name="model-active-2", deprecation=None)
    Model.objects.create(model_name="model-deprecated", deprecation="This model is deprecated")
    Model.objects.create(model_name="model-deprecated-2", deprecation="Replaced by new version")

    response = client.get("/api/model_online_list")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]) == 2
    assert "model-active-1" in data["data"]
    assert "model-active-2" in data["data"]
    assert "model-deprecated" not in data["data"]
    assert "model-deprecated-2" not in data["data"]


@pytest.mark.django_db
def test_model_online_list_returns_empty_when_all_deprecated():
    client = Client()

    Model.objects.create(model_name="model-deprecated-1", deprecation="deprecated")
    Model.objects.create(model_name="model-deprecated-2", deprecation="removed")

    response = client.get("/api/model_online_list")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"] == []


@pytest.mark.django_db
def test_model_online_list_returns_all_when_none_deprecated():
    client = Client()

    Model.objects.create(model_name="model-a", deprecation=None)
    Model.objects.create(model_name="model-b", deprecation=None)
    Model.objects.create(model_name="model-c", deprecation=None)

    response = client.get("/api/model_online_list")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert len(data["data"]) == 3
    assert set(data["data"]) == {"model-a", "model-b", "model-c"}
