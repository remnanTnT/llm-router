from django.test import Client

from router.api import views


def test_download_ai_assistant(monkeypatch, tmp_path):
    file_path = tmp_path / "AI_Assistant.exe"
    file_path.write_bytes(b"binary")
    monkeypatch.setattr(views, "DOWNLOAD_FILE_PATH", file_path)

    response = Client().get("/api/download/ai_assistant")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/octet-stream"
    assert "attachment" in response["Content-Disposition"]
    assert "AI_Assistant.exe" in response["Content-Disposition"]
    assert b"".join(response.streaming_content) == b"binary"


def test_download_ai_assistant_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(views, "DOWNLOAD_FILE_PATH", tmp_path / "missing.exe")

    response = Client().get("/api/download/ai_assistant")

    assert response.status_code == 404
    assert response.json() == {"code": 404, "error": "file not found"}
