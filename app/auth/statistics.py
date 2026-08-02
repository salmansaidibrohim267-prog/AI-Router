from __future__ import annotations

import time
from typing import Any

from .config import AuthConfig


class AuthMetricsTracker:
    def __init__(self, config: AuthConfig | None = None):
        self._config = config or AuthConfig()
        self._enabled = self._config.track_metrics
        self._events: dict[str, int] = {}
        self._per_tenant: dict[str, dict[str, int]] = {}
        self._started_at = time.time()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record(self, event: str, tenant_id: str = "", count: int = 1) -> None:
        if not self._enabled:
            return
        self._events[event] = self._events.get(event, 0) + count
        if tenant_id:
            bucket = self._per_tenant.setdefault(tenant_id, {})
            bucket[event] = bucket.get(event, 0) + count

    def summary(self) -> dict[str, Any]:
        return {
            "events": dict(self._events),
            "per_tenant": {k: dict(v) for k, v in self._per_tenant.items()},
            "uptime_seconds": round(time.time() - self._started_at, 4),
        }

    def reset(self) -> None:
        self._events = {}
        self._per_tenant = {}
