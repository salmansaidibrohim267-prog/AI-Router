from __future__ import annotations

import time
from typing import Any

from app.memory.models import MemoryEventType, MemoryMetrics


class MemoryMetricsTracker:
    def __init__(self):
        self._metrics = MemoryMetrics()
        self._start_time = time.monotonic()

    def record(
        self,
        event: MemoryEventType,
        latency_ms: float = 0.0,
    ) -> None:
        self._metrics.total_ops += 1
        self._metrics.total_latency_ms += latency_ms
        if event == MemoryEventType.STORE:
            self._metrics.total_stores += 1
            self._metrics.stored_items += 1
        elif event == MemoryEventType.RETRIEVE:
            self._metrics.total_retrieves += 1
        elif event == MemoryEventType.UPDATE:
            self._metrics.total_updates += 1
        elif event == MemoryEventType.DELETE:
            self._metrics.total_deletes += 1
            self._metrics.stored_items = max(0, self._metrics.stored_items - 1)
        elif event == MemoryEventType.ARCHIVE:
            self._metrics.total_archives += 1
        elif event == MemoryEventType.PRUNE:
            self._metrics.total_prunes += 1
        elif event == MemoryEventType.COMPACT:
            self._metrics.total_compactions += 1

    def record_search(self, latency_ms: float = 0.0) -> None:
        self._metrics.total_searches += 1
        self._metrics.total_latency_ms += latency_ms

    def record_extraction(self) -> None:
        self._metrics.total_extractions += 1

    def record_summarization(self) -> None:
        self._metrics.total_summarizations += 1

    def record_error(self) -> None:
        self._metrics.errors += 1

    def get_metrics(self) -> MemoryMetrics:
        return self._metrics

    def get_metrics_dict(self) -> dict[str, Any]:
        return self._metrics.to_dict()

    def reset(self) -> None:
        self._metrics = MemoryMetrics()
        self._start_time = time.monotonic()

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time
