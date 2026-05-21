from __future__ import annotations

import json
import logging
import random
import threading
from datetime import timedelta
from typing import Any, Callable, Sequence

from django.utils import timezone

from router.config import APP_CONFIG
from router.route_algorithm.base import ServerSelectionContext
from router.route_algorithm.least_connection import LeastConnectionServerChooser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PrefixCachePrebleServerChooser(LeastConnectionServerChooser):
    _cache_lock = threading.RLock()
    _prefix_cache: dict[str, list[dict[str, Any]]] = {}

    def __init__(
        self,
        count_provider: Callable[[list[str]], dict[str, int]] | None = None,
        primary_match_threshold: float | None = None,
        secondary_match_threshold: float | None = None,
        max_prefix_tokens: int | None = None,
    ):
        super().__init__(count_provider)
        prefix_config = APP_CONFIG.get("prefix_cache", {})
        self.primary_match_threshold = self._float_setting(primary_match_threshold, prefix_config.get("primary_match_threshold"), 0.9)
        self.secondary_match_threshold = self._float_setting(secondary_match_threshold, prefix_config.get("secondary_match_threshold"), 0.5)
        configured_max_prefix_tokens = self._int_setting(max_prefix_tokens, prefix_config.get("max_prefix_tokens"), 100000)
        self.max_prefix_tokens = max(100000, configured_max_prefix_tokens)

    def choose(
        self,
        candidates: Sequence[Any],
        context: ServerSelectionContext,
        attempted_server_ids: set[int],
    ) -> Any | None:
        available = [server for server in candidates if server.id not in attempted_server_ids]
        if not available:
            return None

        request_tokens = self._tokens_from_body(context.body)
        if not request_tokens:
            context.prefix_cache = 0.0
            context.last_match = None
            return self._choose_least_loaded(available)

        model_key = context.model_name or str(context.model_id or "")
        candidates_by_id = {server.id: server for server in candidates}
        available_by_id = {server.id: server for server in available}
        now = timezone.now()
        cached_matches = []
        best_match_ratio = 0.0
        best_match_request_id = None
        server_match_ratios: dict[int, float] = {}

        with self._cache_lock:
            entries = self._prefix_cache.get(model_key, [])
            for entry in entries:
                self._evict_expired(entry, candidates_by_id, now)
                if not entry["server_cached_at"]:
                    continue
                common = self._common_prefix_len(request_tokens, entry["tokens"])
                if not common:
                    continue
                match_ratio = common / len(request_tokens)
                if match_ratio > best_match_ratio:
                    best_match_ratio = match_ratio
                    best_match_request_id = entry.get("request_id")
                for server_id in entry["server_cached_at"]:
                    if match_ratio > server_match_ratios.get(server_id, 0.0):
                        server_match_ratios[server_id] = match_ratio
                if match_ratio > self.primary_match_threshold:
                    for server_id in entry["server_cached_at"]:
                        server = available_by_id.get(server_id)
                        if server is not None:
                            cached_matches.append(server)

        logger.info(
            "[PrefixCachePreble] match_ratio per server (model=%s, best=%.4f):",
            model_key, best_match_ratio,
        )
        for server in available:
            ratio = server_match_ratios.get(server.id, 0.0)
            logger.info(
                "  server_id=%-6d base_url=%-40s match_ratio=%.4f",
                server.id, server.base_url, ratio,
            )

        context.prefix_cache = best_match_ratio
        context.last_match = best_match_request_id
        if cached_matches:
            unique_cached = {server.id: server for server in cached_matches}.values()
            return self._choose_least_loaded(list(unique_cached))

        secondary_matches = [
            server for server in available
            if server_match_ratios.get(server.id, 0.0) > self.secondary_match_threshold
        ]
        if secondary_matches:
            return self._choose_least_loaded(secondary_matches)

        return self._choose_least_loaded(available)

    def _choose_least_loaded(self, available: Sequence[Any]) -> Any | None:
        if not available:
            return None
        targets = [server.base_url for server in available]
        processing_counts = self._count_processing(targets)
        logger.info("[PrefixCachePreble] connection counts per server:")
        for server in available:
            count = processing_counts.get(server.base_url, 0)
            logger.info(
                "  server_id=%-6d base_url=%-40s connections=%d",
                server.id, server.base_url, count,
            )
        min_count = min(processing_counts.get(server.base_url, 0) for server in available)
        least_loaded = [server for server in available if processing_counts.get(server.base_url, 0) == min_count]
        return random.choice(least_loaded)

    def on_response(self, server: Any, context: ServerSelectionContext, status_code: int) -> None:
        if not 200 <= status_code < 300:
            return
        request_tokens = self._tokens_from_body(context.body)
        if not request_tokens:
            return

        model_key = context.model_name or str(context.model_id or "")
        now = timezone.now()
        with self._cache_lock:
            entries = self._prefix_cache.setdefault(model_key, [])
            for entry in entries:
                if entry["tokens"] == request_tokens:
                    entry["server_cached_at"][server.id] = now
                    entry["request_id"] = context.request_id
                    return
            entries.append({"tokens": request_tokens, "request_id": context.request_id, "server_cached_at": {server.id: now}})

    def _evict_expired(self, entry: dict[str, Any], servers_by_id: dict[int, Any], now) -> None:
        expired = []
        for server_id, cached_at in entry["server_cached_at"].items():
            server = servers_by_id.get(server_id)
            if server is None:
                expired.append(server_id)
                continue
            raw_cache_time = getattr(server, "cache_time", 3600)
            cache_time = 3600 if raw_cache_time is None else int(raw_cache_time)
            if now - cached_at > timedelta(seconds=cache_time):
                expired.append(server_id)
        for server_id in expired:
            del entry["server_cached_at"][server_id]

    def _tokens_from_body(self, body: bytes) -> tuple[str, ...]:
        text = self._text_from_body(body)
        tokens = text.split()
        if not tokens and text:
            tokens = list(text)
        return tuple(tokens[: self.max_prefix_tokens])

    @staticmethod
    def _text_from_body(body: bytes) -> str:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text
        if not isinstance(data, dict):
            return text

        messages = data.get("messages")
        if isinstance(messages, list):
            parts = []
            for message in messages:
                if not isinstance(message, dict):
                    continue
                role = message.get("role") or ""
                content = PrefixCachePrebleServerChooser._message_content_text(message.get("content"))
                if content:
                    parts.append(f"{role}: {content}" if role else content)
            if parts:
                return "\n".join(parts)

        prompt = data.get("prompt")
        if isinstance(prompt, str):
            return prompt
        if isinstance(prompt, list):
            return "\n".join(item for item in prompt if isinstance(item, str))
        return text

    @staticmethod
    def _message_content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        return ""

    @staticmethod
    def _common_prefix_len(left: tuple[str, ...], right: tuple[str, ...]) -> int:
        count = 0
        for left_token, right_token in zip(left, right):
            if left_token != right_token:
                break
            count += 1
        return count

    @staticmethod
    def _float_setting(*values) -> float:
        default = float(values[-1])
        for value in values[:-1]:
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default

    @staticmethod
    def _int_setting(*values) -> int:
        default = int(values[-1])
        for value in values[:-1]:
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return default
