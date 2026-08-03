from __future__ import annotations

from app.retrieval.models import RetrievalStatistics


class RetrievalStatsTracker:
    def __init__(self, track: bool = True):
        self._track = track
        self._query_count: int = 0
        self._total_latency_ms: float = 0.0
        self._total_scanned: int = 0
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._total_comparisons: int = 0

    def record_query(self, latency_ms: float, scanned: int = 0, comparisons: int = 0) -> None:
        if not self._track:
            return
        self._query_count += 1
        self._total_latency_ms += latency_ms
        self._total_scanned += scanned
        self._total_comparisons += comparisons

    def record_cache_hit(self) -> None:
        if self._track:
            self._cache_hits += 1

    def record_cache_miss(self) -> None:
        if self._track:
            self._cache_misses += 1

    def snapshot(self) -> RetrievalStatistics:
        avg = 0.0
        if self._query_count > 0:
            avg = self._total_latency_ms / self._query_count
        return RetrievalStatistics(
            query_count=self._query_count,
            total_latency_ms=self._total_latency_ms,
            average_latency_ms=round(avg, 4),
            total_vectors_scanned=self._total_scanned,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            total_comparisons=self._total_comparisons,
        )

    def reset(self) -> None:
        self._query_count = 0
        self._total_latency_ms = 0.0
        self._total_scanned = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_comparisons = 0
