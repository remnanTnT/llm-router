from pathlib import Path
from datetime import datetime

import pytest

from router.services import request_logger


@pytest.fixture(autouse=True)
def reset_request_logger_cache(monkeypatch):
    monkeypatch.setattr(request_logger, "_LOG_PATH_CACHE", None)
    request_logger._REQUEST_LOG_FILE_CACHE.clear()
    monkeypatch.setattr(request_logger, "_current_log_time", lambda: datetime(2026, 6, 8, 12, 34))


def test_append_request_log_writes_line(tmp_path, monkeypatch):
    monkeypatch.setitem(request_logger.APP_CONFIG, "log_path", str(tmp_path))

    request_logger.append_request_log(123, '{"event":"server_attempt"}')

    path = tmp_path / "2026" / "06" / "08" / "12" / "34" / "123.log"
    assert path.read_text(encoding="utf-8") == '{"event":"server_attempt"}\n'


def test_append_request_log_resolves_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr(request_logger, "BASE_DIR", tmp_path)
    monkeypatch.setitem(request_logger.APP_CONFIG, "log_path", "logs/requests")

    request_logger.append_request_log(123, '{"event":"multi_server_route"}')

    path = Path(tmp_path / "logs" / "requests" / "2026" / "06" / "08" / "12" / "34" / "123.log")
    assert path.read_text(encoding="utf-8") == '{"event":"multi_server_route"}\n'


def test_append_error_log_uses_request_log_file(tmp_path, monkeypatch):
    monkeypatch.setitem(request_logger.APP_CONFIG, "log_path", str(tmp_path))

    request_logger.append_request_log(123, '{"event":"server_attempt"}')
    request_logger.append_error_log(123, '{"event":"upstream_error"}')

    path = tmp_path / "2026" / "06" / "08" / "12" / "34" / "123.log"
    assert path.read_text(encoding="utf-8") == (
        '{"event":"server_attempt"}\n'
        '{"event":"upstream_error"}\n'
    )


def test_same_request_keeps_first_minute_bucket(tmp_path, monkeypatch):
    monkeypatch.setitem(request_logger.APP_CONFIG, "log_path", str(tmp_path))
    times = iter([
        datetime(2026, 6, 8, 12, 34),
        datetime(2026, 6, 8, 12, 35),
    ])
    monkeypatch.setattr(request_logger, "_current_log_time", lambda: next(times))

    request_logger.append_request_log(123, "first")
    request_logger.append_request_log(123, "second")

    first_path = tmp_path / "2026" / "06" / "08" / "12" / "34" / "123.log"
    second_path = tmp_path / "2026" / "06" / "08" / "12" / "35" / "123.log"
    assert first_path.read_text(encoding="utf-8") == "first\nsecond\n"
    assert not second_path.exists()
