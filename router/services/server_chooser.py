from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence


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


class LeastConnectionServerChooser:
    def __init__(self, count_provider: Callable[[list[str]], dict[str, int]] | None = None):
        self.count_provider = count_provider

    def choose(
        self,
        candidates: Sequence[Any],
        context: ServerSelectionContext,
        attempted_server_ids: set[int],
    ) -> Any | None:
        available = [server for server in candidates if server.id not in attempted_server_ids]
        if not available:
            return None
        targets = [server.base_url for server in available]
        processing_counts = self._count_processing(targets)
        return min(available, key=lambda server: (processing_counts.get(server.base_url, 0), server.id))

    def _count_processing(self, targets: list[str]) -> dict[str, int]:
        if self.count_provider:
            return self.count_provider(targets)
        from router.repositories.requests import RequestRepository

        return RequestRepository.count_processing_by_targets(targets)
