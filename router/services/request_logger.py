from __future__ import annotations

from pathlib import Path

from router.config import APP_CONFIG, BASE_DIR


def append_request_log(request_id: int, message: str) -> None:
    log_path = Path(APP_CONFIG.get("log_path", "./logs/requests"))
    if not log_path.is_absolute():
        log_path = BASE_DIR / log_path
    log_path.mkdir(parents=True, exist_ok=True)
    with (log_path / f"{request_id}.log").open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


class RequestLogBuffer:
    def __init__(self):
        self.messages: list[str] = []

    def write(self, message: str) -> None:
        self.messages.append(message)

    def flush(self, request_id: int) -> None:
        log_path = Path(APP_CONFIG.get("log_path", "./logs/requests"))
        if not log_path.is_absolute():
            log_path = BASE_DIR / log_path
        log_path.mkdir(parents=True, exist_ok=True)
        with (log_path / f"{request_id}.log").open("a", encoding="utf-8") as handle:
            for message in self.messages:
                handle.write(message.rstrip() + "\n")
        self.messages.clear()
