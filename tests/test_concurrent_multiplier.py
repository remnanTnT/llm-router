import json

import pytest
from django.test import Client
from django.utils import timezone

from router.models import IP, UserIP


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def setup_test_data(db):
    """创建测试数据"""
    now = timezone.now()

    # 创建IP记录
    ip1 = IP.objects.create(
        ip="192.168.1.100",
        concurrent_multiplier=1.0,
        vip=False,
        created_at=now,
        updated_at=now,
    )

    ip2 = IP.objects.create(
        ip="192.168.1.101",
        concurrent_multiplier=1.0,
        vip=False,
        created_at=now,
        updated_at=now,
    )

    # 创建UserIP记录
    user_ip = UserIP.objects.create(
        ip_id=ip1.id,
        user_name="测试用户",
        employee_no="EMP001",
        is_valid=True,
        created_at=now,
        updated_at=now,
    )

    return {
        "ip1": ip1,
        "ip2": ip2,
        "user_ip": user_ip,
    }


@pytest.mark.django_db
def test_update_by_employee_no_success(client, setup_test_data):
    """测试通过工号更新成功"""
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "employee_no": "EMP001",
            "concurrent_multiplier": 2.5,
        }),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "更新成功"
    assert data["data"]["employee_no"] == "EMP001"
    assert data["data"]["ip"] == "192.168.1.100"
    assert data["data"]["concurrent_multiplier"] == 2.5

    # 验证数据库中的值已更新
    ip = IP.objects.get(id=setup_test_data["ip1"].id)
    assert ip.concurrent_multiplier == 2.5


@pytest.mark.django_db
def test_update_by_employee_no_not_found(client, setup_test_data):
    """测试工号不存在"""
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "employee_no": "NOTEXIST",
            "concurrent_multiplier": 2.0,
        }),
        content_type="application/json",
    )

    assert response.status_code == 404
    data = response.json()
    assert data["code"] == 404
    assert "not found" in data["error"]


@pytest.mark.django_db
def test_update_by_ip_success(client, setup_test_data):
    """测试通过IP更新成功"""
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "ip": "192.168.1.101",
            "concurrent_multiplier": 3.0,
        }),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "更新成功"
    assert data["data"]["ip"] == "192.168.1.101"
    assert data["data"]["concurrent_multiplier"] == 3.0

    # 验证数据库中的值已更新
    ip = IP.objects.get(id=setup_test_data["ip2"].id)
    assert ip.concurrent_multiplier == 3.0


@pytest.mark.django_db
def test_update_by_ip_not_found(client, setup_test_data):
    """测试IP不存在"""
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "ip": "10.0.0.1",
            "concurrent_multiplier": 2.0,
        }),
        content_type="application/json",
    )

    assert response.status_code == 404
    data = response.json()
    assert data["code"] == 404
    assert "not found" in data["error"]


@pytest.mark.django_db
def test_missing_parameters(client, setup_test_data):
    """测试缺少必需参数"""
    # 缺少employee_no和ip
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "concurrent_multiplier": 2.0,
        }),
        content_type="application/json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 400
    assert "required" in data["error"]

    # 缺少concurrent_multiplier
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "ip": "192.168.1.100",
        }),
        content_type="application/json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 400
    assert "concurrent_multiplier" in data["error"]


@pytest.mark.django_db
def test_both_parameters_provided(client, setup_test_data):
    """测试同时提供employee_no和ip"""
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "employee_no": "EMP001",
            "ip": "192.168.1.100",
            "concurrent_multiplier": 2.0,
        }),
        content_type="application/json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 400
    assert "only one" in data["error"]


@pytest.mark.django_db
def test_invalid_concurrent_multiplier(client, setup_test_data):
    """测试无效的concurrent_multiplier值"""
    # 小于1
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "ip": "192.168.1.100",
            "concurrent_multiplier": 0.5,
        }),
        content_type="application/json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 400
    assert ">= 1" in data["error"]

    # 非数字
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "ip": "192.168.1.100",
            "concurrent_multiplier": "invalid",
        }),
        content_type="application/json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 400
    assert "number" in data["error"]


@pytest.mark.django_db
def test_invalid_json(client, setup_test_data):
    """测试无效的JSON"""
    response = client.post(
        "/api/concurrent_multiplier/update",
        data="not json",
        content_type="application/json",
    )

    assert response.status_code == 400
    data = response.json()
    assert data["code"] == 400
    assert "invalid JSON" in data["error"]


@pytest.mark.django_db
def test_concurrent_multiplier_as_integer(client, setup_test_data):
    """测试concurrent_multiplier为整数"""
    response = client.post(
        "/api/concurrent_multiplier/update",
        data=json.dumps({
            "ip": "192.168.1.100",
            "concurrent_multiplier": 5,
        }),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["concurrent_multiplier"] == 5.0
