from __future__ import annotations

import hashlib
import json
import time
from threading import Lock
from typing import Any

from app.reranker.models import RerankerResult


class RerankerCache:
    def __init__(self, ttl: int = 3600, max_size: int = 10000):
        self._ttl = ttl
        self._max_size = max_size
        self._cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(
        self,
        query: str,
        candidate_ids: list[str],
        model_version: str = "",
    ) -> str:
        raw = json.dumps(
            {
                "q": query.strip().lower(),
                "ids": sorted(candidate_ids),
                "mv": model_version,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(
        self,
        query: str,
        candidate_ids: list[str],
        model_version: str = "",
    ) -> list[RerankerResult] | None:
        key = self._make_key(query, candidate_ids, model_version)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            ts, results = entry
            if time.time() - ts > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            self._hits += 1
            return [RerankerResult(**r) for r in results]

    def set(
        self,
        query: str,
        candidate_ids: list[str],
        model_version: str,
        results: list[RerankerResult],
    ) -> None:
        key = self._make_key(query, candidate_ids, model_version)
        serialized = [r.to_dict() for r in results]
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._evict()
            self._cache[key] = (time.time(), serialized)

    def _evict(self) -> None:
        oldest = min(self._cache.keys(), key=lambda k: self._cache[k][0])
        del self._cache[oldest]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def invalidate(self, query: str, candidate_ids: list[str], model_version: str = "") -> bool:
        key = self._make_key(query, candidate_ids, model_version)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def size(self) -> int:
        return len(self._cache)

    def statistics(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
            "ttl": self._ttl,
            "max_size": self._max_size,
        }
