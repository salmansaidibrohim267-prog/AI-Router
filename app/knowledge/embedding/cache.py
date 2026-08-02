from __future__ import annotations

import hashlib
import threading
import time
from typing import Any, Protocol


class EmbeddingCache(Protocol):
    async def get(self, key: str) -> list[float] | None:
        ...

    async def set(self, key: str, vector: list[float]) -> None:
        ...

    async def clear(self) -> None:
        ...

    async def stats(self) -> dict[str, Any]:
        ...


def _cache_key(text: str, model: str) -> str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"emb:{model}:{h}"


class InMemoryEmbeddingCache:
    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[list[float], float]] = {}
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> list[float] | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            vector, expires = entry
            if time.time() > expires:
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            return vector

    async def set(self, key: str, vector: list[float]) -> None:
        with self._lock:
            self._cache[key] = (vector, time.time() + self._ttl)

    async def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    async def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
            }


try:
    import redis.asyncio as aioredis

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


class RedisEmbeddingCache:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        ttl: int = 3600,
        prefix: str = "emb:cache:",
    ):
        self._redis_url = redis_url
        self._ttl = ttl
        self._prefix = prefix
        self._redis = None
        self._hits = 0
        self._misses = 0

    async def _get_redis(self):
        if self._redis is None:
            if not HAS_REDIS:
                raise RuntimeError(
                    "redis package is required. Install with: pip install redis"
                )
            self._redis = aioredis.from_url(self._redis_url)
        return self._redis

    async def get(self, key: str) -> list[float] | None:
        r = await self._get_redis()
        raw = await r.get(f"{self._prefix}{key}")
        if raw is None:
            self._misses += 1
            return None
        self._hits += 1
        import json

        return json.loads(raw)

    async def set(self, key: str, vector: list[float]) -> None:
        r = await self._get_redis()
        import json

        await r.setex(f"{self._prefix}{key}", self._ttl, json.dumps(vector))

    async def clear(self) -> None:
        r = await self._get_redis()
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match=f"{self._prefix}*")
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break
        self._hits = 0
        self._misses = 0

    async def stats(self) -> dict[str, Any]:
        r = await self._get_redis()
        cursor, keys = await r.scan(0, match=f"{self._prefix}*")
        total = self._hits + self._misses
        return {
            "size": len(keys),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
        }
