from __future__ import annotations

import statistics
import threading
import time
from typing import Any

from .config import AdminConfig
from .logging import AdminLogger


class StatisticsService:
    """Request-level statistics: throughput, latency percentiles, errors."""

    def __init__(self, config: AdminConfig | None = None, logger: AdminLogger | None = None) -> None:
        self._config = config or AdminConfig()
        self._logger = logger or AdminLogger(self._config)
        self._requests: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record_request(
        self,
        method: str,
        path: str,
        status: int,
        latency_ms: float,
        ts: float | None = None,
    ) -> None:
        with self._lock:
            self._requests.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "status": status,
                    "latency_ms": latency_ms,
                    "ts": ts or time.time(),
                }
            )

    def totals(self, since: float = 0.0) -> dict[str, Any]:
        with self._lock:
            requests = [request for request in self._requests if request["ts"] >= since]
        total = len(requests)
        errors = sum(1 for request in requests if request["status"] >= 400)
        latencies = [request["latency_ms"] for request in requests]
        return {
            "total_requests": total,
            "error_requests": errors,
            "error_rate": round(errors / total, 4) if total else 0.0,
            "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        }

    def percentiles(self) -> dict[str, float]:
        with self._lock:
            latencies = sorted(request["latency_ms"] for request in self._requests)
        if not latencies:
            return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}
        return {
            "p50": round(self._percentile(latencies, 0.50), 2),
            "p90": round(self._percentile(latencies, 0.90), 2),
            "p95": round(self._percentile(latencies, 0.95), 2),
            "p99": round(self._percentile(latencies, 0.99), 2),
        }

    @staticmethod
    def _percentile(sorted_values: list[float], percentile: float) -> float:
        if not sorted_values:
            return 0.0
        index = (len(sorted_values) - 1) * percentile
        lower = int(index)
        upper = min(lower + 1, len(sorted_values) - 1)
        weight = index - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    def status_codes(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for request in self._requests:
                key = f"{request['status'] // 100}xx"
                counts[key] = counts.get(key, 0) + 1
            return dict(sorted(counts.items()))

    def top_endpoints(self, limit: int = 5) -> list[dict[str, Any]]:
        with self._lock:
            counts: dict[str, int] = {}
            latencies: dict[str, list[float]] = {}
            for request in self._requests:
                key = f"{request['method']} {request['path']}"
                counts[key] = counts.get(key, 0) + 1
                latencies.setdefault(key, []).append(request["latency_ms"])
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [
            {
                "endpoint": endpoint,
                "count": count,
                "avg_latency_ms": round(statistics.mean(latencies[endpoint]), 2),
            }
            for endpoint, count in ranked
        ]

    def throughput(self, window_minutes: int = 60) -> list[dict[str, Any]]:
        now = time.time()
        window_seconds = window_minutes * 60
        with self._lock:
            requests = [request for request in self._requests if request["ts"] >= now - window_seconds]
        buckets: dict[int, int] = {}
        for request in requests:
            minute = int((now - request["ts"]) // 60)
            buckets[minute] = buckets.get(minute, 0) + 1
        points = []
        for minute in range(min(window_minutes, 60)):
            points.append({"minute_ago": minute, "requests": buckets.get(minute, 0)})
        return points

    def report(self, since: float = 0.0) -> dict[str, Any]:
        return {
            "totals": self.totals(since=since),
            "percentiles": self.percentiles(),
            "status_codes": self.status_codes(),
            "top_endpoints": self.top_endpoints(),
        }
