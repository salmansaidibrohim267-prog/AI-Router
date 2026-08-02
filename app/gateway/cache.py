"""Response caching for the API Gateway (Stage 10.4)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

from .config import GatewayConfig
from .exceptions import CacheError
from .logging import GatewayLogger
from .models import CacheEntry, GatewayRequest, GatewayResponse


def cache_key(request: GatewayRequest, version: str = "", route: str = "") -> str:
    """Deterministic cache key for a request."""
    payload = {
        "method": request.method,
        "path": request.path,
        "version": version or request.version,
        "route": route,
        "query": request.query,
        "tenant": request.tenant_id,
        "client": request.client_id,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResponseCache:
    """Thread-safe TTL cache for gateway responses."""

    def __init__(self, config: GatewayConfig | None = None, logger: GatewayLogger | None = None):
        self._config = config or GatewayConfig()
        self._logger = logger or GatewayLogger(enabled=False)
        self._lock = threading.RLock()
        self._entries: dict[str, CacheEntry] = {}

    @property
    def enabled(self) -> bool:
        return self._config.cache_enabled

    def get(self, key: str, now: float | None = None) -> GatewayResponse | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.is_expired(now):
                self._entries.pop(key, None)
                return None
            return entry.response

    def set(self, key: str, response: GatewayResponse, ttl_seconds: float | None = None) -> CacheEntry:
        with self._lock:
            ttl = ttl_seconds if ttl_seconds is not None else self._config.cache_ttl_seconds
            if len(self._entries) >= self._config.cache_max_entries and key not in self._entries:
                self._evict_oldest()
            entry = CacheEntry(key=key, response=response, ttl_seconds=ttl)
            self._entries[key] = entry
            return entry

    def _evict_oldest(self) -> None:
        oldest_key: str | None = None
        oldest_stored = float("inf")
        for key, entry in self._entries.items():
            if entry.stored_at < oldest_stored:
                oldest_stored = entry.stored_at
                oldest_key = key
        if oldest_key is not None:
            self._entries.pop(oldest_key, None)

    def invalidate(self, key: str) -> bool:
        with self._lock:
            return self._entries.pop(key, None) is not None

    def invalidate_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [key for key in self._entries if key.startswith(prefix)]
            for key in keys:
                self._entries.pop(key, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def prune(self, now: float | None = None) -> int:
        with self._lock:
            current = now if now is not None else time.time()
            expired = [key for key, entry in self._entries.items() if entry.is_expired(current)]
            for key in expired:
                self._entries.pop(key, None)
            return len(expired)
