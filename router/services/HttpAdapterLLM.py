"""
HTTPAdapterLLM - Custom HTTP adapter with per-model, per-server connection pooling.

Architecture
~~~~~~~~~~~~

    HTTPAdapterLLM  (requests.HTTPAdapter)
      └─ PoolManagerLLM  (urllib3.PoolManager)
           └─ HTTPConnectionPoolLLM  (urllib3.HTTPConnectionPool)  [one per model]
                └─ server_pools: dict[int, LifoQueue]              [one per server]

Routing
~~~~~~~

1. Each model is identified by a **virtual** (host, port) pair in the URL.
2. The ``server-id`` header tells *HTTPConnectionPoolLLM* which actual
   server to connect to.
3. TCP connections are pooled **per server** so they can be reused across
   requests that target the same server.

Example
~~~~~~~

3 models × 3 servers each::

    PoolManagerLLM.pools:
        ("model-1", 8000) → HTTPConnectionPoolLLM(server_map={
            0: ("10.0.0.1", 8080),   # server 0 of model-1
            1: ("10.0.0.2", 8080),   # server 1 of model-1
            2: ("10.0.0.3", 8080),   # server 2 of model-1
        })
        ("model-2", 8001) → HTTPConnectionPoolLLM(server_map={...})
        ("model-3", 8002) → HTTPConnectionPoolLLM(server_map={...})

    HTTPConnectionPoolLLM (for model-1):
        server_pools[0] → LifoQueue  # reusable conns to 10.0.0.1:8080
        server_pools[1] → LifoQueue  # reusable conns to 10.0.0.2:8080
        server_pools[2] → LifoQueue  # reusable conns to 10.0.0.3:8080

Usage with requests.Session::

    adapter = HTTPAdapterLLM(maxsize_per_server=10)
    adapter.register_model_servers("model-1", 8000, {
        0: ("10.0.0.1", 8080),
        1: ("10.0.0.2", 8080),
        2: ("10.0.0.3", 8080),
    })

    session = requests.Session()
    session.mount("http://model-1:8000", adapter)

    resp = session.get(
        "http://model-1:8000/v1/chat/completions",
        headers={"server-id": "1"},
    )
    # → routed to 10.0.0.2:8080, TCP connection pooled for reuse
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Any

from requests.adapters import (
    DEFAULT_POOLBLOCK,
    DEFAULT_POOLSIZE,
    DEFAULT_RETRIES,
    HTTPAdapter,
)
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import ClosedPoolError, EmptyPoolError, FullPoolError
from urllib3.poolmanager import SSL_KEYWORDS, PoolManager
from urllib3.util.connection import is_connection_dropped

__all__ = [
    "HTTPAdapterLLM",
    "HTTPConnectionPoolLLM",
    "PoolManagerLLM",
]

log = logging.getLogger(__name__)

# Default max reusable connections per server sub-pool
DEFAULT_MAXSIZE_PER_SERVER = 10


# ---------------------------------------------------------------------------
#  HTTPConnectionPoolLLM
# ---------------------------------------------------------------------------


class HTTPConnectionPoolLLM(HTTPConnectionPool):
    """Per-model connection pool with **per-server** sub-queues.

    Instead of a single connection queue (as in :class:`HTTPConnectionPool`),
    this class maintains one :class:`queue.LifoQueue` per server under the
    model.  Requests are routed to the correct server's queue based on the
    ``server-id`` HTTP header.

    The ``host`` / ``port`` passed to the constructor are *virtual* – they
    identify the model, not a real network endpoint.  The actual target
    is resolved from :attr:`server_map` using the ``server-id`` header.

    Thread-safety
    ~~~~~~~~~~~~~
    * Each request's ``server-id`` is stored in a ``threading.local()``
      so that :meth:`_get_conn` / :meth:`_put_conn` / :meth:`_new_conn`
      can read it without explicit parameters.
    * Connections are also tagged with their ``server_id`` in
      ``_conn_server_map`` so that :meth:`_put_conn` can route correctly
      even when the connection is released after the thread-local context
      has been cleared (e.g. streaming responses).

    :param host: Virtual host (model identifier).
    :param port: Virtual port (model identifier).
    :param server_map: ``{server_id: (actual_host, actual_port), ...}``
    :param maxsize_per_server: Max reusable connections **per server**.
    """

    scheme = "http"

    def __init__(
        self,
        host: str,
        port: int | None = None,
        server_map: dict[int, tuple[str, int]] | None = None,
        maxsize_per_server: int = DEFAULT_MAXSIZE_PER_SERVER,
        **kwargs: Any,
    ) -> None:
        # Initialise the parent with *minimal* maxsize because we never
        # use its single pool – we manage our own per-server sub-pools.
        super().__init__(host, port, maxsize=1, **kwargs)

        self.server_map: dict[int, tuple[str, int]] = dict(server_map) if server_map else {}
        self.maxsize_per_server = maxsize_per_server

        # Per-server connection queues:  server_id → LifoQueue
        self.server_pools: dict[int, queue.LifoQueue] = {}
        self._init_server_pools()

        # Thread-local context – set in urlopen(), read in _get_conn etc.
        self._local = threading.local()

        # Track which server a connection belongs to, so _put_conn can
        # return it to the right sub-pool even when the thread-local
        # context has already been cleared.
        self._conn_map_lock = threading.Lock()
        self._conn_server_map: dict[int, int] = {}  # id(conn) → server_id

    # ── Server pool management ──────────────────────────────────────────

    def _init_server_pools(self) -> None:
        """Create sub-pools for every entry in :attr:`server_map`."""
        for server_id in self.server_map:
            if server_id not in self.server_pools:
                q: queue.LifoQueue = queue.LifoQueue(self.maxsize_per_server)
                # Pre-fill with None entries (same pattern as parent)
                for _ in range(self.maxsize_per_server):
                    q.put(None)
                self.server_pools[server_id] = q

    def add_server(self, server_id: int, host: str, port: int) -> None:
        """Dynamically register a new server under this model."""
        self.server_map[server_id] = (host, port)
        if server_id not in self.server_pools:
            q: queue.LifoQueue = queue.LifoQueue(self.maxsize_per_server)
            for _ in range(self.maxsize_per_server):
                q.put(None)
            self.server_pools[server_id] = q

    def remove_server(self, server_id: int) -> None:
        """Remove a server and close all its pooled connections."""
        sub_pool = self.server_pools.pop(server_id, None)
        if sub_pool is not None:
            _close_sub_pool(sub_pool)
        self.server_map.pop(server_id, None)

    # ── Header parsing ──────────────────────────────────────────────────

    @staticmethod
    def _extract_server_id(headers: Any) -> int | None:
        """Extract the ``server-id`` value from request headers."""
        if headers is None:
            return None
        # ``requests.structures.CaseInsensitiveDict`` normalises keys to
        # lowercase internally, so a single ``.get("server-id")`` suffices.
        # We also try other casings for plain ``dict`` objects.
        for key in ("server-id", "Server-Id", "SERVER-ID"):
            val = None
            if isinstance(headers, dict):
                val = headers.get(key)
            elif hasattr(headers, "get"):
                val = headers.get(key)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    continue
        return None

    # ── Connection lifecycle overrides ──────────────────────────────────

    def _get_conn(self, timeout: float | None = None) -> Any:
        """Get a connection from the current server's sub-pool."""
        server_id = getattr(self._local, "current_server_id", None)
        if server_id is None:
            raise ClosedPoolError(self, "No server-id context set for current request")

        sub_pool = self.server_pools.get(server_id)
        if sub_pool is None:
            raise ClosedPoolError(self, f"No sub-pool for server-id: {server_id}")

        conn = None
        try:
            conn = sub_pool.get(block=self.block, timeout=timeout)
        except AttributeError:
            raise ClosedPoolError(self, "Sub-pool is closed") from None
        except queue.Empty:
            if self.block:
                raise EmptyPoolError(
                    self,
                    f"Server {server_id} pool empty, blocking prevents new connection",
                ) from None
            # No free connection – will create a new one below

        # Check if a pooled connection is still alive
        if conn and is_connection_dropped(conn):
            log.debug("Resetting dropped connection for server %s", server_id)
            conn.close()
            with self._conn_map_lock:
                self._conn_server_map.pop(id(conn), None)
            conn = None

        if conn is None:
            conn = self._new_conn()

        # Tag the connection so _put_conn knows its server
        with self._conn_map_lock:
            self._conn_server_map[id(conn)] = server_id

        return conn

    def _put_conn(self, conn: Any) -> None:
        """Return a connection to the correct server's sub-pool."""
        if conn is None:
            return

        # Primary: look up server_id from our tracking map
        server_id: int | None = None
        with self._conn_map_lock:
            server_id = self._conn_server_map.pop(id(conn), None)

        # Fallback: thread-local (covers synchronous / non-streaming case)
        if server_id is None:
            server_id = getattr(self._local, "current_server_id", None)

        if server_id is None:
            log.warning("Cannot determine server-id for connection, closing it")
            conn.close()
            return

        sub_pool = self.server_pools.get(server_id)
        if sub_pool is not None:
            try:
                sub_pool.put(conn, block=False)
                return
            except queue.Full:
                if self.block:
                    raise FullPoolError(
                        self,
                        f"Server {server_id} pool full, cannot return connection",
                    ) from None
                log.warning("Server %s pool full, discarding connection", server_id)

        conn.close()

    def _new_conn(self) -> Any:
        """Create a new connection to the *actual* server indicated by
        the current thread-local ``server_id``."""
        server_id = getattr(self._local, "current_server_id", None)
        if server_id is None:
            raise ValueError("No server-id context set for current request")

        server_info = self.server_map.get(server_id)
        if server_info is None:
            raise ValueError(f"Unknown server-id: {server_id}")

        actual_host, actual_port = server_info
        self.num_connections += 1
        log.debug(
            "New HTTP connection (%d) → server %s (%s:%s)",
            self.num_connections,
            server_id,
            actual_host,
            actual_port or 80,
        )
        return self.ConnectionCls(
            host=actual_host,
            port=actual_port,
            timeout=self.timeout.connect_timeout,
            **self.conn_kw,
        )

    # ── urlopen – routing entry point ───────────────────────────────────

    def urlopen(  # type: ignore[override]
        self,
        method: str,
        url: str,
        body: Any | None = None,
        headers: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Intercept *urlopen* to extract ``server-id`` from headers and
        set the thread-local routing context before delegating to the
        parent implementation.

        The ``server-id`` header **must** be present; a :class:`ValueError`
        is raised if it is missing or refers to an unknown server.
        """
        server_id = self._extract_server_id(headers)
        if server_id is None:
            raise ValueError(
                "Request must include 'server-id' header. "
                f"Known servers: {list(self.server_map.keys())}"
            )
        if server_id not in self.server_map:
            raise ValueError(
                f"Unknown server-id: {server_id}. "
                f"Known servers: {list(self.server_map.keys())}"
            )

        self._local.current_server_id = server_id
        # Disable host-checking because we route to different actual hosts
        kwargs["assert_same_host"] = False
        try:
            return super().urlopen(method, url, body=body, headers=headers, **kwargs)
        finally:
            self._local.current_server_id = None

    # ── Cleanup ─────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close all server sub-pools and the parent pool."""
        for server_id in list(self.server_pools):
            sub_pool = self.server_pools.pop(server_id)
            _close_sub_pool(sub_pool)
        # Parent pool only has dummy entries but close it anyway
        super().close()

    def is_same_host(self, url: str) -> bool:
        """Always ``True`` – host routing is managed internally."""
        return True

    # ── Diagnostics ─────────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """Return pool statistics per server (for monitoring / debugging)."""
        return {
            "host": self.host,
            "port": self.port,
            "num_connections": self.num_connections,
            "num_requests": self.num_requests,
            "servers": {
                sid: {
                    "target": f"{info[0]}:{info[1]}",
                    "pool_qsize": self.server_pools[sid].qsize()
                    if sid in self.server_pools
                    else 0,
                }
                for sid, info in self.server_map.items()
            },
        }


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------


def _close_sub_pool(pool: queue.LifoQueue) -> None:
    """Drain and close all connections in a sub-pool."""
    try:
        while True:
            conn = pool.get(block=False)
            if conn:
                conn.close()
    except queue.Empty:
        pass


# ---------------------------------------------------------------------------
#  PoolManagerLLM
# ---------------------------------------------------------------------------


class PoolManagerLLM(PoolManager):
    """PoolManager that creates :class:`HTTPConnectionPoolLLM` instances.

    Each model is identified by a **virtual** ``(host, port)`` pair.
    Before making requests, call :meth:`register_pool_servers` to tell the
    manager which real servers sit behind each virtual endpoint.

    The mapping ``(virtual_host, virtual_port) → server_map`` is stored
    internally; when a pool for a virtual endpoint is first requested,
    an :class:`HTTPConnectionPoolLLM` is created with the corresponding
    ``server_map`` already injected.

    :param maxsize_per_server: Max connections **per server** sub-pool.
    """

    def __init__(
        self,
        num_pools: int = 10,
        headers: Any | None = None,
        maxsize_per_server: int = DEFAULT_MAXSIZE_PER_SERVER,
        **connection_pool_kw: Any,
    ) -> None:
        super().__init__(num_pools, headers, **connection_pool_kw)
        self._maxsize_per_server = maxsize_per_server
        # (virtual_host, virtual_port) → {server_id: (actual_host, actual_port)}
        self._pool_server_maps: dict[tuple[str, int], dict[int, tuple[str, int]]] = {}

    # ── Server registration ─────────────────────────────────────────────

    def register_pool_servers(
        self,
        virtual_host: str,
        virtual_port: int,
        server_map: dict[int, tuple[str, int]],
    ) -> None:
        """Register or update the server mapping for a virtual model endpoint.

        :param virtual_host: Virtual hostname (model identifier in URL).
        :param virtual_port: Virtual port (model identifier in URL).
        :param server_map: ``{server_id: (actual_host, actual_port), ...}``
        """
        key = (virtual_host.lower(), virtual_port)
        self._pool_server_maps[key] = server_map

        # If a pool already exists for this endpoint, update it in-place
        # so that the new server_map takes effect immediately.
        with self.pools.lock:
            for pool_key, pool in self.pools.items():
                if (
                    getattr(pool_key, "key_host", None) == key[0]
                    and getattr(pool_key, "key_port", None) == key[1]
                    and isinstance(pool, HTTPConnectionPoolLLM)
                ):
                    pool.server_map = dict(server_map)
                    pool._init_server_pools()

    # ── Pool creation override ──────────────────────────────────────────

    def _new_pool(
        self,
        scheme: str,
        host: str,
        port: int,
        request_context: dict[str, Any] | None = None,
    ) -> HTTPConnectionPoolLLM:
        """Create an :class:`HTTPConnectionPoolLLM` for *virtual* host:port."""
        lookup = (host.lower(), port)
        server_map = self._pool_server_maps.get(lookup, {})

        if request_context is None:
            request_context = self.connection_pool_kw.copy()
        if request_context.get("blocksize") is None:
            request_context["blocksize"] = 16384  # _DEFAULT_BLOCKSIZE
        for k in ("scheme", "host", "port"):
            request_context.pop(k, None)
        if scheme == "http":
            for kw in SSL_KEYWORDS:
                request_context.pop(kw, None)

        return HTTPConnectionPoolLLM(
            host,
            port,
            server_map=server_map,
            maxsize_per_server=self._maxsize_per_server,
            **request_context,
        )


# ---------------------------------------------------------------------------
#  HTTPAdapterLLM
# ---------------------------------------------------------------------------


class HTTPAdapterLLM(HTTPAdapter):
    """:class:`requests.HTTPAdapter` with per-model, per-server connection
    pooling.

    Drop-in replacement for the default adapter.  Register model servers
    via :meth:`register_model_servers`, mount the adapter on a
    :class:`requests.Session`, and include the ``server-id`` header in
    every request.

    Example
    -------

    .. code-block:: python

        adapter = HTTPAdapterLLM(maxsize_per_server=10)
        adapter.register_model_servers("model-glm-5", 8000, {
            0: ("10.0.0.1", 8080),
            1: ("10.0.0.2", 8080),
            2: ("10.0.0.3", 8080),
        })

        session = requests.Session()
        session.mount("http://model", adapter)

        resp = session.get(
            "http://model-glm-5:8000/v1/chat/completions",
            headers={"server-id": "1"},
        )
        # Request routed to 10.0.0.2:8080; TCP connection is pooled.

    :param maxsize_per_server: Max reusable TCP connections **per server**.
    """

    def __init__(
        self,
        pool_connections: int = DEFAULT_POOLSIZE,
        pool_maxsize: int = DEFAULT_POOLSIZE,
        max_retries: int | Any = DEFAULT_RETRIES,
        pool_block: bool = DEFAULT_POOLBLOCK,
        maxsize_per_server: int = DEFAULT_MAXSIZE_PER_SERVER,
    ) -> None:
        self._maxsize_per_server = maxsize_per_server
        super().__init__(pool_connections, pool_maxsize, max_retries, pool_block)

    # ── PoolManager factory ─────────────────────────────────────────────

    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = DEFAULT_POOLBLOCK,
        **pool_kwargs: Any,
    ) -> None:
        """Create :class:`PoolManagerLLM` instead of the default
        :class:`~urllib3.PoolManager`."""
        self._pool_connections = connections
        self._pool_maxsize = maxsize
        self._pool_block = block

        self.poolmanager = PoolManagerLLM(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            maxsize_per_server=self._maxsize_per_server,
            **pool_kwargs,
        )

    # ── Public API ──────────────────────────────────────────────────────

    def register_model_servers(
        self,
        virtual_host: str,
        virtual_port: int,
        server_map: dict[int, tuple[str, int]],
    ) -> None:
        """Register a model's servers with the pool manager.

        :param virtual_host: Virtual hostname representing the model
            (used in the request URL).
        :param virtual_port: Virtual port representing the model
            (used in the request URL).
        :param server_map: ``{server_id: (actual_host, actual_port), ...}``
            – each key is the integer ID that will appear in the
            ``server-id`` header; each value is the real ``(host, port)``
            the connection should be made to.
        """
        self.poolmanager.register_pool_servers(virtual_host, virtual_port, server_map)
