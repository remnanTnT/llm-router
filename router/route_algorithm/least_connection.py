from __future__ import annotations

from typing import Any, Callable, Sequence

from router.route_algorithm.base import ServerSelectionContext


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
        return self._choose_least_loaded(available)

    def on_response(self, server: Any, context: ServerSelectionContext, status_code: int) -> None:
        return None

    def _choose_least_loaded(self, available: Sequence[Any]) -> Any | None:
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
