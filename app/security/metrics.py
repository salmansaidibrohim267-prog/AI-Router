"""Metrics tracking for the security framework."""

from __future__ import annotations

import threading
from typing import Any

from .config import SecurityConfig


class SecurityMetricsTracker:
    """Thread-safe counters, optionally grouped by component."""

    def __init__(self, config: SecurityConfig | None = None) -> None:
        self._config = config or SecurityConfig()
        self._counts: dict[str, int] = {}
        self._by_component: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    def record(self, name: str, component: str = "security", amount: int = 1) -> None:
        with self._lock:
            self._counts[name] = self._counts.get(name, 0) + amount
            component_counts = self._by_component.setdefault(component, {})
            component_counts[name] = component_counts.get(name, 0) + amount

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def by_component(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {name: dict(values) for name, values in self._by_component.items()}

    def summary(self) -> dict[str, Any]:
        return {"counts": self.counts(), "by_component": self.by_component()}
