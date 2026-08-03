from __future__ import annotations

import time
from typing import Any

from app.prompting.models import PromptMetrics


class PromptMetricsTracker:
    def __init__(self):
        self._metrics = PromptMetrics()
        self._start_time = time.monotonic()

    def record_build(
        self,
        total_tokens: int,
        latency_ms: float,
        truncated: bool = False,
    ) -> None:
        self._metrics.total_builds += 1
        self._metrics.total_tokens_built += total_tokens
        self._metrics.total_latency_ms += latency_ms
        if truncated:
            self._metrics.truncations += 1
        self._metrics.average_latency_ms = self._metrics.total_latency_ms / self._metrics.total_builds
        self._metrics.average_tokens_per_build = self._metrics.total_tokens_built / self._metrics.total_builds

    def record_validation_failure(self) -> None:
        self._metrics.validation_failures += 1

    def get_metrics(self) -> PromptMetrics:
        return self._metrics

    def get_metrics_dict(self) -> dict[str, Any]:
        return self._metrics.to_dict()

    def reset(self) -> None:
        self._metrics = PromptMetrics()
        self._start_time = time.monotonic()

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time
