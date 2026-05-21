from django.test import Client

from router import views


def test_whitelist_update_create_noop_and_update():
    client = Client()

    created = client.post("/api/whitelist/update", {"employee_no": "E001", "is_allowed": "1"})
    unchanged = client.post("/api/whitelist/update", {"employee_no": "E001", "is_allowed": "1"})
    updated = client.post("/api/whitelist/update", {"employee_no": "E001", "is_allowed": "0"})

    assert created.status_code == 200
    assert created.json()["message"] == "创建成功"
    assert unchanged.status_code == 200
    assert unchanged.json()["message"] == "本次修改未生效"
    assert updated.status_code == 200
    assert updated.json()["message"] == "更新成功"


def test_refresh_user_info_starts_background_thread(monkeypatch):
    started = {}

    class FakeThread:
        def __init__(self, target, daemon):
            started["target"] = target
            started["daemon"] = daemon

        def start(self):
            started["started"] = True

    monkeypatch.setattr(views.threading, "Thread", FakeThread)
    monkeypatch.setitem(views.APP_CONFIG, "cmdb", {**views.APP_CONFIG.get("cmdb", {}), "enabled": True})

    response = Client().post("/api/refresh_user_info")

    assert response.status_code == 200
    assert response.json() == {"code": 200, "message": "用户信息刷新任务已启动"}
    assert started["daemon"] is True
    assert started["started"] is True
