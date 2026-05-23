from __future__ import annotations

import json
import logging
import random
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Sequence

from django.utils import timezone

from router.config import APP_CONFIG
from router.route_algorithm.base import ServerSelectionContext
from router.route_algorithm.least_connection import LeastConnectionServerChooser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TrieNode:
    """Memory-efficient Trie node for prefix matching.
    
    Using __slots__ to minimize memory overhead per node.
    """
    __slots__ = ("children", "server_cached_at", "request_id")

    def __init__(self):
        # token -> TrieNode
        self.children: dict[str, TrieNode] = {}
        # server_id -> (cached_at_timestamp, cache_time_seconds)
        self.server_cached_at: dict[int, tuple[datetime, int]] = {}
        # Most recent request_id that passed through or ended at this node
        self.request_id: int | None = None


class PrefixCachePrebleServerChooser(LeastConnectionServerChooser):
    _cache_lock = threading.RLock()
    # model_key -> root TrieNode
    _prefix_cache: dict[str, TrieNode] = {}
    _node_count = 0
    _last_prune_time = 0

    def __init__(
        self,
        count_provider: Callable[[list[str]], dict[str, int]] | None = None,
        primary_match_threshold: float | None = None,
        secondary_match_threshold: float | None = None,
        max_prefix_tokens: int | None = None,
        max_total_nodes: int | None = None,
        prune_interval: int | None = None,
    ):
        super().__init__(count_provider)
        prefix_config = APP_CONFIG.get("prefix_cache", {})
        self.primary_match_threshold = self._float_setting(primary_match_threshold, prefix_config.get("primary_match_threshold"), 0.9)
        self.secondary_match_threshold = self._float_setting(secondary_match_threshold, prefix_config.get("secondary_match_threshold"), 0.5)
        self.max_prefix_tokens = self._int_setting(max_prefix_tokens, prefix_config.get("max_prefix_tokens"), 5000)
        self.max_total_nodes = self._int_setting(max_total_nodes, prefix_config.get("max_total_nodes"), 1000000)
        self.prune_interval = self._int_setting(prune_interval, prefix_config.get("prune_interval"), 300)

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
        available_by_id = {server.id: server for server in available}
        now = timezone.now()
        
        cached_matches = []
        best_match_ratio = 0.0
        best_match_request_id = None
        server_match_ratios: dict[int, float] = {}

        with self._cache_lock:
            root = self._prefix_cache.get(model_key)
            if root:
                node = root
                for i, token in enumerate(request_tokens):
                    if token not in node.children:
                        break
                    node = node.children[token]
                    match_ratio = (i + 1) / len(request_tokens)
                    
                    # Clean up expired entries on the path we walk
                    self._evict_expired_from_node(node, now)
                    
                    if node.server_cached_at:
                        if match_ratio > best_match_ratio:
                            best_match_ratio = match_ratio
                            best_match_request_id = node.request_id
                        
                        for server_id in node.server_cached_at:
                            if match_ratio > server_match_ratios.get(server_id, 0.0):
                                server_match_ratios[server_id] = match_ratio
                            
                            if match_ratio > self.primary_match_threshold:
                                server = available_by_id.get(server_id)
                                if server:
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
        raw_cache_time = getattr(server, "cache_time", 3600)
        cache_time = 3600 if raw_cache_time is None else int(raw_cache_time)

        with self._cache_lock:
            # 1. Periodic/Emergency Pruning
            if (time.time() - self._last_prune_time > self.prune_interval or 
                self._node_count > self.max_total_nodes):
                self._prune_all()
            
            # 2. Add to Trie
            if self._node_count >= self.max_total_nodes:
                # If still over limit after pruning, skip adding new entries
                return

            node = self._prefix_cache.get(model_key)
            if node is None:
                node = TrieNode()
                self._prefix_cache[model_key] = node
                PrefixCachePrebleServerChooser._node_count += 1
            
            for token in request_tokens:
                if token not in node.children:
                    if self._node_count >= self.max_total_nodes:
                        break
                    node.children[token] = TrieNode()
                    PrefixCachePrebleServerChooser._node_count += 1
                node = node.children[token]
                node.server_cached_at[server.id] = (now, cache_time)
                node.request_id = context.request_id

    @classmethod
    def _evict_expired_from_node(cls, node: TrieNode, now: datetime) -> None:
        expired = []
        for server_id, (cached_at, cache_time) in node.server_cached_at.items():
            if now - cached_at > timedelta(seconds=cache_time):
                expired.append(server_id)
        for server_id in expired:
            del node.server_cached_at[server_id]

    @classmethod
    def _prune_all(cls):
        """Prunes all models in the cache."""
        now = timezone.now()
        cls._last_prune_time = time.time()
        for model_key in list(cls._prefix_cache.keys()):
            root = cls._prefix_cache[model_key]
            if cls._prune_node_iterative(root, now):
                del cls._prefix_cache[model_key]
                cls._node_count -= 1

    @classmethod
    def _prune_node_iterative(cls, root: TrieNode, now: datetime) -> bool:
        """Iteratively removes expired servers and dead branches from the Trie.
        
        Returns True if the node itself should be pruned (no children and no server cache).
        """
        # stack of (node, parent, token_in_parent, children_iterator)
        stack = [(root, None, None, iter(list(root.children.items())))]
        
        while stack:
            node, parent, token, children_iter = stack[-1]
            try:
                child_token, child_node = next(children_iter)
                stack.append((child_node, node, child_token, iter(list(child_node.children.items()))))
            except StopIteration:
                stack.pop()
                # Post-order: children are done.
                # 1. Evict expired from this node
                cls._evict_expired_from_node(node, now)
                
                # 2. If it's a child and it's empty, remove from parent
                if parent is not None:
                    if not node.children and not node.server_cached_at:
                        del parent.children[token]
                        cls._node_count -= 1
        
        return not root.children and not root.server_cached_at

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
