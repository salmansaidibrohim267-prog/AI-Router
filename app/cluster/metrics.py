"""Metrics tracker for the cluster framework."""

from __future__ import annotations

import threading
from typing import Any

from .config import ClusterConfig


class ClusterMetricsTracker:
    """Counts cluster events per component and in aggregate."""

    def __init__(self, config: ClusterConfig | None = None) -> None:
        self._config = config or ClusterConfig()
        self._counts: dict[str, int] = {}
        self._by_component: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    def record(self, metric: str, component: str = "", amount: int = 1) -> None:
        if not self._config.track_metrics:
            return
        with self._lock:
            self._counts[metric] = self._counts.get(metric, 0) + amount
            if component:
                bucket = self._by_component.setdefault(component, {})
                bucket[metric] = bucket.get(metric, 0) + amount

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def for_component(self, component: str) -> dict[str, int]:
        with self._lock:
            return dict(self._by_component.get(component, {}))

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_events": sum(self._counts.values()),
                "counts": dict(self._counts),
                "components": {component: dict(bucket) for component, bucket in self._by_component.items()},
            }
