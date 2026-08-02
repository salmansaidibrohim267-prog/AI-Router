from __future__ import annotations

import threading
from typing import Any

from .config import PluginConfig


class PluginMetricsTracker:
    """Counts platform events per plugin and in aggregate."""

    def __init__(self, config: PluginConfig | None = None) -> None:
        self._config = config or PluginConfig()
        self._counts: dict[str, int] = {}
        self._by_plugin: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    def record(self, metric: str, plugin: str = "", amount: int = 1) -> None:
        if not self._config.track_metrics:
            return
        with self._lock:
            self._counts[metric] = self._counts.get(metric, 0) + amount
            if plugin:
                bucket = self._by_plugin.setdefault(plugin, {})
                bucket[metric] = bucket.get(metric, 0) + amount

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def for_plugin(self, plugin: str) -> dict[str, int]:
        with self._lock:
            return dict(self._by_plugin.get(plugin, {}))

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_events": sum(self._counts.values()),
                "counts": dict(self._counts),
                "plugins": {plugin: dict(bucket) for plugin, bucket in self._by_plugin.items()},
            }
