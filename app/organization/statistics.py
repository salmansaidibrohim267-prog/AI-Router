from __future__ import annotations

import time
from typing import Any

from .config import OrganizationConfig


class OrganizationMetricsTracker:
    def __init__(self, config: OrganizationConfig | None = None):
        self._config = config or OrganizationConfig()
        self._enabled = self._config.track_metrics
        self._events: dict[str, int] = {}
        self._per_scope: dict[str, dict[str, int]] = {}
        self._started_at = time.time()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record(self, event: str, scope_id: str = "", count: int = 1) -> None:
        if not self._enabled:
            return
        self._events[event] = self._events.get(event, 0) + count
        if scope_id:
            bucket = self._per_scope.setdefault(scope_id, {})
            bucket[event] = bucket.get(event, 0) + count

    def for_scope(self, scope_id: str) -> dict[str, int]:
        return dict(self._per_scope.get(scope_id, {}))

    def summary(self) -> dict[str, Any]:
        return {
            "events": dict(self._events),
            "per_scope": {k: dict(v) for k, v in self._per_scope.items()},
            "uptime_seconds": round(time.time() - self._started_at, 4),
        }

    def reset(self) -> None:
        self._events = {}
        self._per_scope = {}
