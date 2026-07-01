import pytest
from django.test import Client

from router.models import Model


@pytest.mark.django_db
def test_model_online_list_returns_models_with_online_servers():
    client = Client()

    online_a = Model.objects.create(model_name="model-a")
    online_b = Model.objects.create(model_name="model-b")
    no_server = Model.objects.create(model_name="model-no-server")

    _make_server(model_id=online_a.id, is_online=True)
    _make_server(model_id=online_b.id, is_online=True)

    response = client.get("/api/model_online_list")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert set(data["data"]) == {"model-a", "model-b"}
    assert "model-no-server" not in data["data"]


@pytest.mark.django_db
def test_model_online_list_excludes_models_with_only_offline_or_deleted_servers():
    client = Client()

    offline = Model.objects.create(model_name="model-offline")
    deleted = Model.objects.create(model_name="model-deleted")

    _make_server(model_id=offline.id, is_online=False)
    _make_server(model_id=deleted.id, is_online=True, deleted=True)

    response = client.get("/api/model_online_list")

    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []


@pytest.mark.django_db
def test_model_online_list_shows_deprecated_model_backed_by_servers():
    # Regression: a model whose deprecation is set as an access-control word
    # must still appear on the dashboard if it has live servers behind it.
    client = Client()

    deprecated = Model.objects.create(
        model_name="glm-5",
        deprecation="glm-5 is deprecated, please use glm-6.",
    )
    _make_server(model_id=deprecated.id, is_online=True)

    response = client.get("/api/model_online_list")

    assert response.status_code == 200
    data = response.json()
    assert "glm-5" in data["data"]


def _make_server(model_id, *, is_online=True, deleted=False):
    from django.utils import timezone
    from router.models import Server

    return Server.objects.create(
        model_id=model_id,
        base_url=f"http://{model_id}-{is_online}-{deleted}.example",
        is_online=is_online,
        deleted_at=timezone.now() if deleted else None,
    )
