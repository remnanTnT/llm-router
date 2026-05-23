from __future__ import annotations

from datetime import datetime
from pathlib import Path

from router.config import APP_CONFIG, BASE_DIR


_LOG_PATH_CACHE: Path | None = None
_LOG_DIR_CREATED: bool = False
_ERROR_DIR_CACHE: dict[str, Path] = {}


def _resolve_log_path() -> Path:
    global _LOG_PATH_CACHE
    if _LOG_PATH_CACHE is None:
        log_path = Path(APP_CONFIG.get("log_path", "./logs/requests"))
        if not log_path.is_absolute():
            log_path = BASE_DIR / log_path
        _LOG_PATH_CACHE = log_path
    return _LOG_PATH_CACHE


def append_request_log(request_id: int, message: str) -> None:
    log_path = _resolve_log_path()
    global _LOG_DIR_CREATED
    if not _LOG_DIR_CREATED:
        log_path.mkdir(parents=True, exist_ok=True)
        _LOG_DIR_CREATED = True
    with (log_path / f"{request_id}.log").open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def append_error_log(request_id: int, message: str) -> None:
    log_path = _resolve_log_path()
    now = datetime.now()
    date_key = now.strftime("%Y%m%d")
    error_dir = _ERROR_DIR_CACHE.get(date_key)
    if error_dir is None:
        error_dir = log_path / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        error_dir.mkdir(parents=True, exist_ok=True)
        _ERROR_DIR_CACHE[date_key] = error_dir
        # Keep cache small
        if len(_ERROR_DIR_CACHE) > 10:
            oldest_key = min(_ERROR_DIR_CACHE.keys())
            _ERROR_DIR_CACHE.pop(oldest_key)

    with (error_dir / f"{request_id}.log").open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


class RequestLogBuffer:
    def __init__(self):
        self.messages: list[str] = []

    def write(self, message: str) -> None:
        self.messages.append(message)

    def flush(self, request_id: int) -> None:
        log_path = _resolve_log_path()
        global _LOG_DIR_CREATED
        if not _LOG_DIR_CREATED:
            log_path.mkdir(parents=True, exist_ok=True)
            _LOG_DIR_CREATED = True
        with (log_path / f"{request_id}.log").open("a", encoding="utf-8") as handle:
            for message in self.messages:
                handle.write(message.rstrip() + "\n")
        self.messages.clear()
