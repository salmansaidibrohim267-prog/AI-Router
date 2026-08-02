from __future__ import annotations

import time
from typing import Any

from .config import MCPIntegrationConfig
from .models import MCPIntegrationMetrics


class MCPIntegrationMetricsTracker:
    def __init__(self, config: MCPIntegrationConfig | None = None):
        self._config = config or MCPIntegrationConfig()
        self._metrics = MCPIntegrationMetrics()
        self._enabled = self._config.track_metrics

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_retrieval(self, latency_ms: float) -> None:
        if self._enabled:
            self._metrics.record_retrieval(latency_ms)

    def record_tool_call(self) -> None:
        if self._enabled:
            self._metrics.record_tool_call()

    def record_resource_read(self) -> None:
        if self._enabled:
            self._metrics.record_resource_read()

    def record_memory_store(self) -> None:
        if self._enabled:
            self._metrics.record_memory_store()

    def record_memory_retrieve(self, count: int = 1) -> None:
        if self._enabled:
            self._metrics.record_memory_retrieve(count)

    def record_citation(self) -> None:
        if self._enabled:
            self._metrics.record_citation()

    def record_answer(self, latency_ms: float) -> None:
        if self._enabled:
            self._metrics.record_answer(latency_ms)

    def record_error(self) -> None:
        if self._enabled:
            self._metrics.record_error()

    def get_metrics(self) -> MCPIntegrationMetrics:
        return self._metrics

    def reset(self) -> None:
        self._metrics = MCPIntegrationMetrics()

    def elapsed(self, start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 4)
