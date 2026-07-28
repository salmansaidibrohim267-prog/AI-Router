"""Cache manager with TTL support."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

from app.models import CacheEntry


@dataclass
class CacheStats:
    """Cache statistics."""
    name: str
    size: int = 0
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    max_size: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class TTLCache:
    """Thread-safe TTL cache with LRU eviction."""

    def __init__(
        self,
        name: str,
        max_size: int = 1000,
        default_ttl: int = 300,
        cleanup_interval: int = 60,
    ):
        self.name = name
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval

        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats(name=name, max_size=max_size)
        self._cleanup_timer: threading.Timer | None = None
        self._start_cleanup()

    def _start_cleanup(self) -> None:
        """Start periodic cleanup of expired entries."""
        def cleanup():
            self._cleanup_expired()
            self._cleanup_timer = threading.Timer(self.cleanup_interval, cleanup)
            self._cleanup_timer.daemon = True
            self._cleanup_timer.start()

        self._cleanup_timer = threading.Timer(self.cleanup_interval, cleanup)
        self._cleanup_timer.daemon = True
        self._cleanup_timer.start()

    def _cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        now = time.time()
        removed = 0
        with self._lock:
            keys_to_remove = [
                key for key, entry in self._cache.items()
                if entry.expires_at and entry.expires_at < now
            ]
            for key in keys_to_remove:
                del self._cache[key]
                removed += 1
                self._stats.evictions += 1
            self._stats.size = len(self._cache)
        return removed

    def _make_key(self, key: Any) -> str:
        """Create cache key from any hashable object."""
        if isinstance(key, str):
            return key
        try:
            return hashlib.sha256(
                json.dumps(key, sort_keys=True, default=str).encode()
            ).hexdigest()
        except (TypeError, ValueError):
            return hashlib.sha256(str(key).encode()).hexdigest()

    def get(self, key: Any) -> Any | None:
        """Get value from cache."""
        cache_key = self._make_key(key)

        with self._lock:
            entry = self._cache.get(cache_key)
            if not entry:
                self._stats.misses += 1
                return None

            # Check expiration
            if entry.expires_at and entry.expires_at < time.time():
                del self._cache[cache_key]
                self._stats.evictions += 1
                self._stats.misses += 1
                self._stats.size = len(self._cache)
                return None

            # Move to end (LRU)
            self._cache.move_to_end(cache_key)
            self._stats.hits += 1
            return entry.value

    def set(
        self,
        key: Any,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Set value in cache."""
        cache_key = self._make_key(key)
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl if ttl > 0 else None

        with self._lock:
            # Remove existing if present
            if cache_key in self._cache:
                del self._cache[cache_key]

            # Check size limit
            if len(self._cache) >= self.max_size:
                # Evict LRU
                self._cache.popitem(last=False)
                self._stats.evictions += 1

            # Add new entry
            entry = CacheEntry(
                key=cache_key,
                value=value,
                created_at=time.time(),
                expires_at=expires_at,
                ttl=ttl,
            )
            self._cache[cache_key] = entry
            self._stats.size = len(self._cache)
            return True

    def delete(self, key: Any) -> bool:
        """Delete key from cache."""
        cache_key = self._make_key(key)
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                self._stats.size = len(self._cache)
                return True
            return False

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._cache.clear()
            self._stats.size = 0
            self._stats.hits = 0
            self._stats.misses = 0
            self._stats.evictions = 0

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        with self._lock:
            self._stats.size = len(self._cache)
            return self._stats

    def close(self) -> None:
        """Close cache and stop cleanup timer."""
        if self._cleanup_timer:
            self._cleanup_timer.cancel()


class CacheManager:
    """Manages multiple named caches."""

    def __init__(self):
        self._caches: dict[str, TTLCache] = {}
        self._lock = threading.RLock()

    def get_cache(
        self,
        name: str,
        max_size: int = 1000,
        default_ttl: int = 300,
    ) -> TTLCache:
        """Get or create a named cache."""
        with self._lock:
            if name not in self._caches:
                self._caches[name] = TTLCache(name, max_size, default_ttl)
            return self._caches[name]

    def get_all_stats(self) -> dict[str, dict]:
        """Get stats for all caches."""
        with self._lock:
            return {
                name: cache.get_stats().__dict__
                for name, cache in self._caches.items()
            }

    def clear_all(self) -> None:
        """Clear all caches."""
        with self._lock:
            for cache in self._caches.values():
                cache.clear()

    def close_all(self) -> None:
        """Close all caches."""
        with self._lock:
            for cache in self._caches.values():
                cache.close()
            self._caches.clear()


# Global cache manager
cache_manager = CacheManager()