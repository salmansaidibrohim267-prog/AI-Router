from __future__ import annotations

import time
from typing import Any

from app.rag.models import RAGMetrics


class RAGMetricsTracker:
    def __init__(self):
        self._metrics = RAGMetrics()
        self._start_time = time.monotonic()

    def record_request(
        self,
        total_latency_ms: float,
        retrieval_latency_ms: float = 0.0,
        llm_latency_ms: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_hit: bool = False,
        fallback: bool = False,
    ) -> None:
        self._metrics.total_requests += 1
        self._metrics.total_latency_ms += total_latency_ms
        self._metrics.total_retrieval_latency_ms += retrieval_latency_ms
        self._metrics.total_llm_latency_ms += llm_latency_ms
        self._metrics.total_prompt_tokens += prompt_tokens
        self._metrics.total_completion_tokens += completion_tokens
        if cache_hit:
            self._metrics.cache_hits += 1
        else:
            self._metrics.cache_misses += 1
        if fallback:
            self._metrics.fallbacks += 1
        self._metrics.average_latency_ms = (
            self._metrics.total_latency_ms / self._metrics.total_requests
        )

    def record_error(self) -> None:
        self._metrics.errors += 1

    def get_metrics(self) -> RAGMetrics:
        return self._metrics

    def get_metrics_dict(self) -> dict[str, Any]:
        return self._metrics.to_dict()

    def reset(self) -> None:
        self._metrics = RAGMetrics()
        self._start_time = time.monotonic()

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time
