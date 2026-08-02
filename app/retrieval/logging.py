from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.retrieval.models import SearchQuery, SearchResponse


class RetrievalLogger:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._logger = logging.getLogger("app.retrieval")

    def log_query(self, query: SearchQuery) -> None:
        if not self._enabled:
            return
        self._logger.info(
            "Semantic search query",
            extra={"query": query.to_dict()},
        )

    def log_result(
        self,
        query: SearchQuery,
        response: SearchResponse,
        latency_ms: float,
    ) -> None:
        if not self._enabled:
            return
        self._logger.info(
            "Semantic search result",
            extra={
                "query": query.to_dict(),
                "results_count": len(response.results),
                "total": response.total,
                "latency_ms": round(latency_ms, 4),
                "statistics": response.statistics,
            },
        )

    def log_error(self, query: SearchQuery | None, error: Exception) -> None:
        if not self._enabled:
            return
        self._logger.error(
            "Semantic search error",
            extra={
                "query": query.to_dict() if query else None,
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )
