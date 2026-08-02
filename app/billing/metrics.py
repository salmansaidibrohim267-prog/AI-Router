from __future__ import annotations

import threading
from typing import Any

from .config import BillingConfig
from .logging import BillingLogger

_MONTHS_PER_YEAR = 12
_CENTS_PER_UNIT = 100.0


class BillingMetricsTracker:
    """Revenue and churn metrics: MRR, ARR, churn and conversion rates.

    Observability surface for the billing platform. Snapshot-based so it can be
    replayed by the Admin Dashboard (Stage 10.6) without recomputation.
    """

    def __init__(self, config: BillingConfig | None = None, logger: BillingLogger | None = None) -> None:
        self._config = config or BillingConfig()
        self._logger = logger or BillingLogger(self._config)
        self._lock = threading.Lock()
        self._snapshots: list[dict[str, Any]] = []

    @property
    def snapshots(self) -> list[dict[str, Any]]:
        return self._snapshots

    @staticmethod
    def _money(amount: float) -> int:
        return round(amount * _CENTS_PER_UNIT)

    def record_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        status: str,
        price: float,
        seats: int = 1,
        interval: str = "monthly",
    ) -> dict[str, Any]:
        if not self._config.track_metrics:
            return {}
        monthly = price * seats
        if interval != "monthly":
            monthly = price * seats / _MONTHS_PER_YEAR
        snapshot = {
            "tenant_id": tenant_id,
            "plan_id": plan_id,
            "status": status,
            "monthly_revenue": round(monthly, 4),
        }
        with self._lock:
            self._snapshots.append(snapshot)
        self._logger.log_event(
            "metrics.subscription",
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=status,
            monthly_revenue=snapshot["monthly_revenue"],
        )
        return snapshot

    def _latest_by_tenant(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for snapshot in self._snapshots:
            latest[snapshot["tenant_id"]] = snapshot
        return latest

    def mrr(self) -> int:
        """Monthly Recurring Revenue in minor units, from active/trialing subs."""
        total = 0.0
        for snapshot in self._latest_by_tenant().values():
            if snapshot["status"] in ("active", "trialing"):
                total += snapshot["monthly_revenue"]
        return self._money(total)

    def arr(self) -> int:
        """Annual Recurring Revenue in minor units."""
        return self.mrr() * _MONTHS_PER_YEAR

    def churn_rate(self, cancelled: int = 0, active_start: int = 0) -> float:
        if active_start <= 0:
            return 0.0
        return cancelled / active_start

    def conversion_rate(self, converted: int = 0, trials: int = 0) -> float:
        if trials <= 0:
            return 0.0
        return converted / trials

    def summary(self) -> dict[str, Any]:
        mrr = self.mrr()
        latest = self._latest_by_tenant()
        return {
            "mrr": mrr,
            "arr": self.arr(),
            "currency": self._config.currency,
            "active_subscriptions": sum(1 for s in latest.values() if s["status"] == "active"),
            "trialing_subscriptions": sum(1 for s in latest.values() if s["status"] == "trialing"),
            "cancelled_subscriptions": sum(1 for s in latest.values() if s["status"] == "cancelled"),
            "by_plan": self.revenue_by_plan(),
        }

    def revenue_by_plan(self) -> dict[str, int]:
        plans: dict[str, float] = {}
        for snapshot in self._latest_by_tenant().values():
            if snapshot["status"] in ("active", "trialing"):
                plans[snapshot["plan_id"]] = plans.get(snapshot["plan_id"], 0.0) + snapshot["monthly_revenue"]
        return {plan: self._money(total) for plan, total in plans.items()}
