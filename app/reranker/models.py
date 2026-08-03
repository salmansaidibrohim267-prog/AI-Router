from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RerankerInput:
    query: str
    candidates: list[dict[str, Any]]


@dataclass
class RerankerResult:
    id: str
    score: float
    original_score: float = 0.0
    calibrated_score: float = 0.0
    rank: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "score": self.score,
            "original_score": self.original_score,
            "calibrated_score": self.calibrated_score,
            "rank": self.rank,
            "metadata": self.metadata,
            "model": self.model,
        }


@dataclass
class RerankerResponse:
    results: list[RerankerResult]
    total: int
    query_time_ms: float = 0.0
    model: str = ""
    cache_hit: bool = False
    statistics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
            "query_time_ms": self.query_time_ms,
            "model": self.model,
            "cache_hit": self.cache_hit,
            "statistics": self.statistics,
        }


@dataclass
class RerankerMetrics:
    total_requests: int = 0
    total_latency_ms: float = 0.0
    average_latency_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    total_candidates_reranked: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_latency_ms": round(self.total_latency_ms, 4),
            "average_latency_ms": round(self.average_latency_ms, 4),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "total_candidates_reranked": self.total_candidates_reranked,
            "errors": self.errors,
        }
