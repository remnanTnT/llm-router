import json

import pytest
from django.db import IntegrityError, transaction

from router.models import Department, Ips, UserIP
from router.services.cmdb import CMDBService


def _cmdb_data():
    return {
        "user_charge": "Engineer",
        "dept1": "Technology",
        "dept2": "Platform",
        "dept3": "AI",
        "dept4": "Routing",
    }


def _post(client, apikey="key-1", employee_no="E001"):
    return client.post(
        "/api/apikey",
        data=json.dumps({"apikey": apikey, "employee_no": employee_no}),
        content_type="application/json",
    )


@pytest.mark.django_db
def test_public_cmdb_adapter_returns_404(client):
    response = _post(client)

    assert response.status_code == 404
    assert response.json()["error"] == "employee lookup is not implemented"
    assert not UserIP.objects.filter(apikey="key-1").exists()


@pytest.mark.django_db
def test_register_apikey_creates_key_backed_user(client, monkeypatch):
    monkeypatch.setattr(CMDBService, "fetch_user_data_by_employee_no", lambda self, employee_no: _cmdb_data())

    response = _post(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["operation"] == "created"
    assert "key-1" not in response.content.decode()

    row = UserIP.objects.get(id=payload["data"]["user_ip_id"])
    department = Department.objects.get(id=row.department_id)
    assert row.ip_id == 0
    assert row.apikey == "key-1"
    assert row.employee_no == "E001"
    assert row.user_charge == "Engineer"
    assert row.vip is False
    assert (department.dept1, department.dept2, department.dept3, department.dept4) == (
        "Technology",
        "Platform",
        "AI",
        "Routing",
    )


@pytest.mark.django_db
def test_register_apikey_is_idempotent(client, monkeypatch):
    monkeypatch.setattr(CMDBService, "fetch_user_data_by_employee_no", lambda self, employee_no: _cmdb_data())

    created = _post(client)
    reused = _post(client)

    assert created.status_code == 200
    assert reused.status_code == 200
    assert reused.json()["data"]["operation"] == "reused"
    assert reused.json()["data"]["user_ip_id"] == created.json()["data"]["user_ip_id"]
    assert UserIP.objects.filter(employee_no="E001").count() == 1


@pytest.mark.django_db
def test_register_apikey_rotates_row_and_inherits_vip(client, monkeypatch):
    monkeypatch.setattr(CMDBService, "fetch_user_data_by_employee_no", lambda self, employee_no: _cmdb_data())
    ip = Ips.objects.create(ip="10.0.0.1", vip=True)
    UserIP.objects.create(ip_id=ip.id, employee_no="E001", vip=True, is_valid=True)

    first = _post(client, apikey="key-old")
    second = _post(client, apikey="key-new")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["operation"] == "replaced"
    assert second.json()["data"]["vip"] is True

    old_row = UserIP.objects.get(apikey="key-old")
    new_row = UserIP.objects.get(apikey="key-new")
    assert old_row.is_valid is False
    assert old_row.deleted_at is not None
    assert new_row.is_valid is True
    assert new_row.deleted_at is None
    assert new_row.vip is True
    assert old_row.id != new_row.id


@pytest.mark.django_db
def test_register_apikey_rejects_key_used_by_another_employee(client, monkeypatch):
    monkeypatch.setattr(CMDBService, "fetch_user_data_by_employee_no", lambda self, employee_no: _cmdb_data())
    assert _post(client, apikey="shared-key", employee_no="E001").status_code == 200

    response = _post(client, apikey="shared-key", employee_no="E002")

    assert response.status_code == 409
    assert not UserIP.objects.filter(employee_no="E002").exists()


@pytest.mark.django_db
def test_register_apikey_handles_cmdb_failures(client, monkeypatch):
    monkeypatch.setattr(CMDBService, "fetch_user_data_by_employee_no", lambda self, employee_no: None)
    assert _post(client).status_code == 404

    def fail(self, employee_no):
        raise RuntimeError("CMDB unavailable")

    monkeypatch.setattr(CMDBService, "fetch_user_data_by_employee_no", fail)
    assert _post(client).status_code == 502


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"apikey": "", "employee_no": "E001"},
        {"apikey": "key-1", "employee_no": ""},
        {"apikey": 123, "employee_no": "E001"},
    ],
)
def test_register_apikey_validates_body(client, body):
    response = client.post("/api/apikey", data=json.dumps(body), content_type="application/json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_user_ip_credential_constraints():
    UserIP.objects.create(ip_id=10, employee_no="IP-1")
    UserIP.objects.create(ip_id=0, apikey="key-1", employee_no="E001")
    UserIP.objects.create(ip_id=0, apikey="key-2", employee_no="E002")

    with pytest.raises(IntegrityError), transaction.atomic():
        UserIP.objects.create(ip_id=10, employee_no="IP-2")

    with pytest.raises(IntegrityError), transaction.atomic():
        UserIP.objects.create(ip_id=0, apikey="key-1", employee_no="E003")

    with pytest.raises(IntegrityError), transaction.atomic():
        UserIP.objects.create(ip_id=11, apikey="both", employee_no="E004")

    with pytest.raises(IntegrityError), transaction.atomic():
        UserIP.objects.create(ip_id=0, apikey="key-3", employee_no="E001")
