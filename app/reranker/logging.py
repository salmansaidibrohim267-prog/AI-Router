from __future__ import annotations

import logging

from app.reranker.models import RerankerResponse


class RerankerLogger:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._logger = logging.getLogger("app.reranker")

    def log_rerank(self, query: str, candidate_count: int, top_k: int) -> None:
        if not self._enabled:
            return
        self._logger.info(
            "Reranker request",
            extra={
                "query": query[:200],
                "candidate_count": candidate_count,
                "top_k": top_k,
            },
        )

    def log_result(self, query: str, response: RerankerResponse, latency_ms: float) -> None:
        if not self._enabled:
            return
        self._logger.info(
            "Reranker result",
            extra={
                "query": query[:200],
                "results_count": len(response.results),
                "total": response.total,
                "latency_ms": round(latency_ms, 4),
                "model": response.model,
                "cache_hit": response.cache_hit,
            },
        )

    def log_error(self, query: str | None, error: Exception) -> None:
        if not self._enabled:
            return
        self._logger.error(
            "Reranker error",
            extra={
                "query": query[:200] if query else None,
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )
