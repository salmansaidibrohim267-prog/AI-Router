from __future__ import annotations

from threading import Lock
from typing import Any

from app.reranker.models import RerankerMetrics


class RerankerMetricsTracker:
    def __init__(self, track: bool = True):
        self._track = track
        self._lock = Lock()
        self._total_requests: int = 0
        self._total_latency_ms: float = 0.0
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._total_candidates: int = 0
        self._errors: int = 0

    def record_request(self, latency_ms: float, candidates: int) -> None:
        if not self._track:
            return
        with self._lock:
            self._total_requests += 1
            self._total_latency_ms += latency_ms
            self._total_candidates += candidates

    def record_cache_hit(self) -> None:
        if not self._track:
            return
        with self._lock:
            self._cache_hits += 1

    def record_cache_miss(self) -> None:
        if not self._track:
            return
        with self._lock:
            self._cache_misses += 1

    def record_error(self) -> None:
        if not self._track:
            return
        with self._lock:
            self._errors += 1

    def snapshot(self) -> RerankerMetrics:
        avg = 0.0
        if self._total_requests > 0:
            avg = self._total_latency_ms / self._total_requests
        return RerankerMetrics(
            total_requests=self._total_requests,
            total_latency_ms=self._total_latency_ms,
            average_latency_ms=round(avg, 4),
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            total_candidates_reranked=self._total_candidates,
            errors=self._errors,
        )

    def reset(self) -> None:
        with self._lock:
            self._total_requests = 0
            self._total_latency_ms = 0.0
            self._cache_hits = 0
            self._cache_misses = 0
            self._total_candidates = 0
            self._errors = 0
