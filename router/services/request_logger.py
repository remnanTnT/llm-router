from __future__ import annotations

from datetime import datetime
from pathlib import Path

from router.config import APP_CONFIG, BASE_DIR


def _resolve_log_path() -> Path:
    log_path = Path(APP_CONFIG.get("log_path", "./logs/requests"))
    if not log_path.is_absolute():
        log_path = BASE_DIR / log_path
    return log_path


def append_request_log(request_id: int, message: str) -> None:
    log_path = _resolve_log_path()
    log_path.mkdir(parents=True, exist_ok=True)
    with (log_path / f"{request_id}.log").open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def append_error_log(request_id: int, message: str) -> None:
    log_path = _resolve_log_path()
    now = datetime.now()
    error_dir = log_path / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
    error_dir.mkdir(parents=True, exist_ok=True)
    with (error_dir / f"{request_id}.log").open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


class RequestLogBuffer:
    def __init__(self):
        self.messages: list[str] = []

    def write(self, message: str) -> None:
        self.messages.append(message)

    def flush(self, request_id: int) -> None:
        log_path = _resolve_log_path()
        log_path.mkdir(parents=True, exist_ok=True)
        with (log_path / f"{request_id}.log").open("a", encoding="utf-8") as handle:
            for message in self.messages:
                handle.write(message.rstrip() + "\n")
        self.messages.clear()
