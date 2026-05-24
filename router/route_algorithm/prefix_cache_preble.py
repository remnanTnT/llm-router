from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Sequence

import redis
from django.utils import timezone

from router.config import APP_CONFIG
from router.route_algorithm.base import ServerSelectionContext
from router.route_algorithm.least_connection import LeastConnectionServerChooser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PrefixCachePrebleServerChooser(LeastConnectionServerChooser):
    _redis_client: redis.Redis | None = None
    _client_lock = threading.Lock()
    _cache_key_namespace = "prefix_chars"

    def __init__(
        self,
        count_provider: Callable[[list[str]], dict[str, int]] | None = None,
        primary_match_threshold: float | None = None,
        secondary_match_threshold: float | None = None,
        max_prefix_chars: int | None = None,
        prefix_block_chars: int | None = None,
    ):
        super().__init__(count_provider)
        prefix_config = APP_CONFIG.get("prefix_cache", {})
        self.primary_match_threshold = self._float_setting(primary_match_threshold, prefix_config.get("primary_match_threshold"), 0.9)
        self.secondary_match_threshold = self._float_setting(secondary_match_threshold, prefix_config.get("secondary_match_threshold"), 0.5)
        self.max_prefix_chars = self._positive_int_setting(
            max_prefix_chars,
            prefix_config.get("max_prefix_chars"),
            1000000,
        )
        self.prefix_block_chars = self._positive_int_setting(
            prefix_block_chars,
            prefix_config.get("prefix_block_chars"),
            8,
        )
        self._ensure_redis()

    def _ensure_redis(self):
        if PrefixCachePrebleServerChooser._redis_client is not None:
            return
        with PrefixCachePrebleServerChooser._client_lock:
            if PrefixCachePrebleServerChooser._redis_client is not None:
                return
            redis_cfg = APP_CONFIG.get("prefix_cache", {}).get("redis", {})
            try:
                PrefixCachePrebleServerChooser._redis_client = redis.Redis(
                    host=redis_cfg.get("host", "localhost"),
                    port=redis_cfg.get("port", 6379),
                    db=redis_cfg.get("db", 0),
                    password=redis_cfg.get("password"),
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
            except Exception as e:
                logger.error("[PrefixCachePreble] Failed to connect to Redis: %s", e)

    def choose(
        self,
        candidates: Sequence[Any],
        context: ServerSelectionContext,
        attempted_server_ids: set[int],
    ) -> Any | None:
        available = [server for server in candidates if server.id not in attempted_server_ids]
        if not available:
            return None

        request_chars = self._prefix_chars_from_body(context.body)
        if not request_chars or self._redis_client is None:
            context.prefix_cache = 0.0
            context.last_match = None
            return self._choose_least_loaded(available)

        model_key = context.model_name or str(context.model_id or "")
        available_by_id = {server.id: server for server in available}
        
        # 1. Generate prefix hashes for all blocks
        prefixes = self._build_prefixes(request_chars)
        
        if not prefixes:
            return self._choose_least_loaded(available)

        prefix_hashes = [self._hash_prefix(p) for p in prefixes]
        redis_keys = [f"{self._cache_key_namespace}:{model_key}:{h}" for h in prefix_hashes]

        # 2. MGET from Redis
        try:
            cached_values = self._redis_client.mget(redis_keys)
        except Exception as e:
            logger.error("[PrefixCachePreble] Redis MGET failed: %s", e)
            cached_values = [None] * len(redis_keys)

        # 3. Find longest match
        best_match_ratio = 0.0
        best_match_request_id = None
        cached_matches = []
        server_match_ratios: dict[int, float] = {}
        now_ts = time.time()

        for i, val in enumerate(cached_values):
            if not val:
                continue
            
            try:
                # Value format: {"request_id": int, "servers": {server_id: expiry_ts, ...}}
                data = json.loads(val)
                request_id = data.get("request_id")
                servers_data = data.get("servers", {})
                
                match_ratio = len(prefixes[i]) / len(request_chars)
                found_valid_server_for_ratio = False
                
                valid_servers_in_this_prefix = []
                for s_id_str, expiry_ts in servers_data.items():
                    if now_ts < expiry_ts:
                        s_id = int(s_id_str)
                        found_valid_server_for_ratio = True
                        
                        if match_ratio > server_match_ratios.get(s_id, 0.0):
                            server_match_ratios[s_id] = match_ratio
                        
                        if match_ratio > self.primary_match_threshold:
                            server = available_by_id.get(s_id)
                            if server:
                                valid_servers_in_this_prefix.append(server)
                
                if found_valid_server_for_ratio:
                    if match_ratio > best_match_ratio:
                        best_match_ratio = match_ratio
                        best_match_request_id = request_id
                
                if valid_servers_in_this_prefix:
                    cached_matches = valid_servers_in_this_prefix # Update with the longest match's servers
            except Exception as e:
                logger.error("[PrefixCachePreble] Failed to parse cached value: %s", e)

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
            return self._choose_least_loaded(cached_matches)

        secondary_matches = [
            server for server in available
            if server_match_ratios.get(server.id, 0.0) > self.secondary_match_threshold
        ]
        if secondary_matches:
            return self._choose_least_loaded(secondary_matches)

        return self._choose_least_loaded(available)

    def on_response(self, server: Any, context: ServerSelectionContext, status_code: int) -> None:
        if not 200 <= status_code < 300 or self._redis_client is None:
            return
        request_chars = self._prefix_chars_from_body(context.body)
        if not request_chars:
            return

        model_key = context.model_name or str(context.model_id or "")
        raw_cache_time = getattr(server, "cache_time", 3600)
        cache_time = 3600 if raw_cache_time is None else int(raw_cache_time)
        expiry_ts = time.time() + cache_time

        # Generate hashes for blocks and full request
        prefixes_to_save = self._build_prefixes(request_chars)

        if not prefixes_to_save:
            return

        try:
            pipe = self._redis_client.pipeline()
            for p in prefixes_to_save:
                h = self._hash_prefix(p)
                key = f"{self._cache_key_namespace}:{model_key}:{h}"
                data = {
                    "request_id": context.request_id,
                    "servers": {str(server.id): expiry_ts}
                }
                pipe.set(key, json.dumps(data), ex=cache_time)
            pipe.execute()
        except Exception as e:
            logger.error("[PrefixCachePreble] Redis SET failed: %s", e)

    def _build_prefixes(self, prefix_chars: tuple[str, ...]) -> list[tuple[str, ...]]:
        prefixes = []
        for i in range(self.prefix_block_chars, len(prefix_chars) + 1, self.prefix_block_chars):
            prefixes.append(prefix_chars[:i])
        if len(prefix_chars) % self.prefix_block_chars != 0:
            prefixes.append(prefix_chars)
        return prefixes

    def _hash_prefix(self, prefix_chars: tuple[str, ...]) -> str:
        return hashlib.sha256("".join(prefix_chars).encode("utf-8")).hexdigest()

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

    def _prefix_chars_from_body(self, body: bytes) -> tuple[str, ...]:
        text = self._text_from_body(body)
        return tuple(text[: self.max_prefix_chars])

    def _tokens_from_body(self, body: bytes) -> tuple[str, ...]:
        return self._prefix_chars_from_body(body)

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

    @staticmethod
    def _positive_int_setting(*values) -> int:
        setting = PrefixCachePrebleServerChooser._int_setting(*values)
        return max(setting, 1)
