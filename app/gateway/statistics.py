"""Metrics and observability for the API Gateway (Stage 10.4)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


class GatewayMetricsTracker:
    """Thread-safe in-process metrics for the gateway."""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str], int] = defaultdict(int)
        self._errors: dict[tuple[str, str], int] = defaultdict(int)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._rate_limit_hits: dict[str, int] = defaultdict(int)
        self._quota_hits: dict[str, int] = defaultdict(int)
        self._cache_hits: dict[str, int] = defaultdict(int)
        self._cache_misses: dict[str, int] = defaultdict(int)
        self._webhook_deliveries: dict[str, int] = defaultdict(int)
        self._versions: dict[str, int] = defaultdict(int)
        self._protocols: dict[str, int] = defaultdict(int)
        self._started_at = time.time()

    def record_request(
        self, method: str, path: str, status: int, duration: float, version: str = "", protocol: str = "http"
    ) -> None:  # noqa: E501
        if not self._enabled:
            return
        with self._lock:
            self._requests[(method, path)] += 1
            self._versions[version or "unknown"] += 1
            self._protocols[protocol] += 1
            self._latencies[path].append(duration)
            if status >= 400:
                self._errors[(path, str(status))] += 1

    def record_rate_limit_hit(self, strategy: str) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._rate_limit_hits[strategy] += 1

    def record_quota_hit(self, bucket: str) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._quota_hits[bucket] += 1

    def record_cache(self, hit: bool, route: str = "") -> None:
        if not self._enabled:
            return
        with self._lock:
            if hit:
                self._cache_hits[route] += 1
            else:
                self._cache_misses[route] += 1

    def record_webhook(self, event: str, success: bool) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._webhook_deliveries[event] += 1 if success else -1

    def get_metrics(self) -> dict[str, Any]:
        with self._lock:
            total = sum(self._requests.values())
            latency_data: dict[str, float] = {}
            for path, samples in self._latencies.items():
                latency_data[path] = sum(samples) / len(samples) if samples else 0.0
            return {
                "total_requests": total,
                "requests_by_route": {f"{m} {p}": c for (m, p), c in self._requests.items()},
                "requests_by_version": dict(self._versions),
                "requests_by_protocol": dict(self._protocols),
                "errors": {f"{p} {s}": c for (p, s), c in self._errors.items()},
                "average_latency_by_route": latency_data,
                "rate_limit_hits": dict(self._rate_limit_hits),
                "quota_hits": dict(self._quota_hits),
                "cache_hits": dict(self._cache_hits),
                "cache_misses": dict(self._cache_misses),
                "webhook_deliveries": dict(self._webhook_deliveries),
                "uptime_seconds": time.time() - self._started_at,
            }

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._errors.clear()
            self._latencies.clear()
            self._rate_limit_hits.clear()
            self._quota_hits.clear()
            self._cache_hits.clear()
            self._cache_misses.clear()
            self._webhook_deliveries.clear()
            self._versions.clear()
            self._protocols.clear()
