from __future__ import annotations

import time
from typing import Any

from .config import AdminConfig
from .logging import AdminLogger


class AdminMetricsTracker:
    """Tracks admin API usage: request counts, latency and error rates."""

    def __init__(self, config: AdminConfig | None = None, logger: AdminLogger | None = None) -> None:
        self._config = config or AdminConfig()
        self._logger = logger or AdminLogger(self._config)
        self._requests: list[dict[str, Any]] = []

    def record_request(self, endpoint: str, latency_ms: float = 0.0, error: bool = False) -> None:
        if not self._config.track_metrics:
            return
        self._requests.append({"endpoint": endpoint, "latency_ms": latency_ms, "error": error, "ts": time.time()})

    def report(self) -> dict[str, Any]:
        total = len(self._requests)
        errors = sum(1 for request in self._requests if request["error"])
        by_endpoint: dict[str, int] = {}
        for request in self._requests:
            by_endpoint[request["endpoint"]] = by_endpoint.get(request["endpoint"], 0) + 1
        return {
            "total_requests": total,
            "error_requests": errors,
            "error_rate": round(errors / total, 4) if total else 0.0,
            "by_endpoint": dict(sorted(by_endpoint.items())),
        }
