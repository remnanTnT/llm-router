from pathlib import Path

from router.services import request_logger


def test_append_request_log_writes_line(tmp_path, monkeypatch):
    monkeypatch.setitem(request_logger.APP_CONFIG, "log_path", str(tmp_path))

    request_logger.append_request_log(123, '{"event":"server_attempt"}')

    assert (tmp_path / "123.log").read_text(encoding="utf-8") == '{"event":"server_attempt"}\n'


def test_append_request_log_resolves_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr(request_logger, "BASE_DIR", tmp_path)
    monkeypatch.setitem(request_logger.APP_CONFIG, "log_path", "logs/requests")

    request_logger.append_request_log(123, '{"event":"multi_server_route"}')

    assert Path(tmp_path / "logs" / "requests" / "123.log").read_text(encoding="utf-8") == '{"event":"multi_server_route"}\n'
