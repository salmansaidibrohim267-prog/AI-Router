from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .config import AdminConfig
from .exceptions import AnalyticsUnavailableError
from .logging import AdminLogger
from .models import AnalyticsPoint

_SECONDS_PER_DAY = 86400


class AnalyticsService:
    """Query side of CQRS: aggregates platform analytics.

    Records metric samples internally by default; production wiring may
    substitute external sources (gateway statistics, billing snapshots) via
    the ``sources`` mapping.
    """

    def __init__(
        self,
        config: AdminConfig | None = None,
        logger: AdminLogger | None = None,
        sources: dict[str, Callable[[], Any]] | None = None,
    ) -> None:
        self._config = config or AdminConfig()
        self._logger = logger or AdminLogger(self._config)
        self._sources = sources or {}
        self._series: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def register_source(self, name: str, source: Callable[[], Any]) -> None:
        self._sources[name] = source

    def source(self, name: str) -> Any:
        source = self._sources.get(name)
        if source is None:
            raise AnalyticsUnavailableError(f"analytics source {name!r} is not configured")
        return source()

    def record(self, metric: str, value: float = 1.0, ts: float | None = None, labels: dict[str, str] | None = None) -> None:
        sample = {"ts": ts or time.time(), "value": value, "labels": labels or {}}
        with self._lock:
            self._series.setdefault(metric, []).append(sample)

    def series(self, metric: str, since: float = 0.0) -> list[dict[str, Any]]:
        with self._lock:
            samples = list(self._series.get(metric, []))
        return [sample for sample in samples if sample["ts"] >= since]

    def trend(self, metric: str, days: int = 7) -> list[AnalyticsPoint]:
        if days < 1:
            raise AnalyticsUnavailableError("days must be >= 1")
        now = time.time()
        since = now - days * _SECONDS_PER_DAY
        samples = self.series(metric, since=since)
        buckets: dict[int, float] = {}
        for sample in samples:
            day = int((sample["ts"] - since) // _SECONDS_PER_DAY)
            buckets[day] = buckets.get(day, 0.0) + sample["value"]
        points = []
        for day in range(days):
            points.append(
                AnalyticsPoint(
                    label=f"day-{day + 1}",
                    value=round(buckets.get(day, 0.0), 4),
                    dimension=metric,
                )
            )
        return points

    def top(self, metric: str, limit: int = 5, dimension: str = "label") -> list[AnalyticsPoint]:
        samples = self.series(metric)
        grouped: dict[str, float] = {}
        for sample in samples:
            key = sample.get("labels", {}).get(dimension, "unknown")
            grouped[key] = grouped.get(key, 0.0) + sample["value"]
        ranked = sorted(grouped.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [AnalyticsPoint(label=key, value=round(value, 4), dimension=metric) for key, value in ranked]

    def revenue_report(self, snapshots: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        snapshots = snapshots if snapshots is not None else self.source("revenue_snapshots")
        mrr = 0.0
        arr = 0.0
        by_plan: dict[str, float] = {}
        active = 0
        for snapshot in snapshots:
            if snapshot.get("status") in ("active", "trialing"):
                monthly = snapshot.get("monthly_revenue", 0.0)
                mrr += monthly
                arr += monthly * 12
                plan = snapshot.get("plan_id", "unknown")
                by_plan[plan] = by_plan.get(plan, 0.0) + monthly
                active += 1
        return {
            "mrr": round(mrr, 4),
            "arr": round(arr, 4),
            "active_subscriptions": active,
            "by_plan": {plan: round(total, 4) for plan, total in by_plan.items()},
        }

    def usage_summary(self) -> dict[str, Any]:
        total = 0.0
        by_category: dict[str, float] = {}
        for category in ("tokens", "api_requests", "vector_storage", "embeddings", "mcp_calls", "plugins", "uploads", "active_users"):
            samples = self.series(category)
            value = sum(sample["value"] for sample in samples)
            by_category[category] = round(value, 4)
            total += value
        return {"total": round(total, 4), "by_category": by_category}

    def summary(self) -> dict[str, Any]:
        return {
            "usage": self.usage_summary(),
            "trends": {metric: [point.to_dict() for point in self.trend(metric, days=7)] for metric in self._series},
        }
