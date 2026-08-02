from __future__ import annotations

import time
from typing import Any

from .config import TenancyConfig


class TenancyMetricsTracker:
    def __init__(self, config: TenancyConfig | None = None):
        self._config = config or TenancyConfig()
        self._enabled = self._config.track_metrics
        self._requests: dict[str, list[float]] = {}
        self._errors: dict[str, dict[str, int]] = {}
        self._resolutions: dict[str, dict[str, int]] = {}
        self._started_at = time.time()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_request(self, tenant_id: str, latency_ms: float, success: bool = True) -> None:
        if not self._enabled:
            return
        self._requests.setdefault(tenant_id, []).append(latency_ms)
        if not success:
            self._record_error(tenant_id, "request_failure")

    def record_error(self, tenant_id: str, error_type: str) -> None:
        if self._enabled:
            self._record_error(tenant_id, error_type)

    def _record_error(self, tenant_id: str, error_type: str) -> None:
        self._errors.setdefault(tenant_id, {})
        self._errors[tenant_id][error_type] = self._errors[tenant_id].get(error_type, 0) + 1

    def record_resolution(self, tenant_id: str, method: str, success: bool = True) -> None:
        if not self._enabled:
            return
        self._resolutions.setdefault(tenant_id, {})
        key = f"{method}:{'ok' if success else 'fail'}"
        self._resolutions[tenant_id][key] = self._resolutions[tenant_id].get(key, 0) + 1

    def by_tenant(self, tenant_id: str) -> dict[str, Any]:
        latencies = self._requests.get(tenant_id, [])
        return {
            "requests": len(latencies),
            "avg_latency_ms": round(sum(latencies) / len(latencies), 4) if latencies else 0.0,
            "errors": dict(self._errors.get(tenant_id, {})),
            "total_errors": sum(self._errors.get(tenant_id, {}).values()),
            "resolutions": dict(self._resolutions.get(tenant_id, {})),
        }

    def summary(self) -> dict[str, Any]:
        return {
            "tenants": sorted(self._requests.keys()),
            "total_requests": sum(len(v) for v in self._requests.values()),
            "total_errors": sum(sum(v.values()) for v in self._errors.values()),
            "uptime_seconds": round(time.time() - self._started_at, 4),
            "per_tenant": {tid: self.by_tenant(tid) for tid in self._requests},
        }

    def reset(self) -> None:
        self._requests = {}
        self._errors = {}
        self._resolutions = {}
