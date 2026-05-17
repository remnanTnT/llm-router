from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class ServerSelectionContext:
    request_id: int
    ip_id: int | None
    model_id: int | None
    model_name: str | None
    path: str
    method: str
    is_stream: bool
    body: bytes


class ServerChooser(Protocol):
    def choose(
        self,
        candidates: Sequence[Any],
        context: ServerSelectionContext,
        attempted_server_ids: set[int],
    ) -> Any | None:
        ...
