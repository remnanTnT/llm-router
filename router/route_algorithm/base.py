from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass
class ServerSelectionContext:
    request_id: int
    ip_id: int | None
    model_id: int | None
    model_name: str | None
    path: str
    method: str
    is_stream: bool
    body: bytes
    origin_model_name: str | None = None
    prefix_cache: float = 0.0
    last_match: int | None = None


class ServerChooser(Protocol):
    def choose(
        self,
        candidates: Sequence[Any],
        context: ServerSelectionContext,
        attempted_server_ids: set[int],
    ) -> Any | None:
        ...
