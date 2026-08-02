from __future__ import annotations

import time
from typing import Any


class EmbeddingStatistics:
    def __init__(self):
        self._total_embeddings = 0
        self._total_tokens = 0
        self._total_latency = 0.0
        self._batch_count = 0
        self._batch_sizes: list[int] = []
        self._provider_usage: dict[str, int] = {}
        self._errors = 0

    def record(
        self,
        count: int,
        tokens: int = 0,
        latency: float = 0.0,
        provider: str = "",
        batch_size: int = 0,
    ) -> None:
        self._total_embeddings += count
        self._total_tokens += tokens
        self._total_latency += latency
        self._batch_count += 1
        self._batch_sizes.append(batch_size)
        if provider:
            self._provider_usage[provider] = (
                self._provider_usage.get(provider, 0) + count
            )

    def record_error(self) -> None:
        self._errors += 1

    def snapshot(self) -> dict[str, Any]:
        avg_latency = (
            round(self._total_latency / self._total_embeddings, 4)
            if self._total_embeddings > 0
            else 0.0
        )
        avg_batch = (
            round(sum(self._batch_sizes) / len(self._batch_sizes), 1)
            if self._batch_sizes
            else 0.0
        )
        return {
            "total_embeddings": self._total_embeddings,
            "total_tokens": self._total_tokens,
            "average_latency_ms": round(avg_latency * 1000, 2),
            "total_latency_sec": round(self._total_latency, 3),
            "batch_count": self._batch_count,
            "average_batch_size": avg_batch,
            "provider_usage": dict(self._provider_usage),
            "errors": self._errors,
        }
