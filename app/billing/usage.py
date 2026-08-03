from __future__ import annotations

import time
from typing import Any

from .exceptions import UsageRecordingError
from .models import UsageCategory, UsageRecord


class UsageMeter:
    """Meters usage across the eight platform dimensions.

    Aggregates UsageRecords per tenant/category with a time window, and
    compares consumption against plan limits to produce UsageMeter views.
    """

    CATEGORIES: tuple[str, ...] = tuple(category.value for category in UsageCategory)

    def __init__(self, repository: Any = None) -> None:
        from .repository import InMemoryUsageRepository

        self._repository = repository or InMemoryUsageRepository()

    @property
    def repository(self) -> Any:
        return self._repository

    def record(
        self,
        tenant_id: str,
        category: str | UsageCategory,
        amount: int = 1,
        at: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        if isinstance(category, str):
            try:
                category = UsageCategory(category)
            except ValueError:
                raise UsageRecordingError(f"Unknown usage category {category!r}", category=category) from None
        if amount < 0:
            raise UsageRecordingError("Usage amount cannot be negative", amount=amount)
        record = UsageRecord(
            tenant_id=tenant_id,
            category=category,
            amount=amount,
            recorded_at=at or time.time(),
            metadata=metadata or {},
        )
        return self._repository.record(record)

    def usage(self, tenant_id: str, category: str | UsageCategory, since: float = 0.0) -> int:
        key = category.value if isinstance(category, UsageCategory) else category
        return self._repository.usage(tenant_id, key, since=since)

    def usage_by_category(self, tenant_id: str, since: float = 0.0) -> dict[str, int]:
        return self._repository.usage_by_category(tenant_id, since=since)

    def snapshot(self, tenant_id: str, limits: dict[str, int] | None = None, since: float = 0.0) -> list[Any]:
        """Return a per-category metering view aligned to plan limits."""
        from .models import UsageMeter

        usage = self.usage_by_category(tenant_id, since=since)
        meters: list[Any] = []
        for category in self.CATEGORIES:
            used = usage.get(category, 0)
            limit = (limits or {}).get(category, 0)
            meters.append(
                UsageMeter(
                    category=UsageCategory(category),
                    unit=category,
                    limit=limit,
                    used=used,
                    overage=limit > 0 and used > limit,
                )
            )
        return meters

    def reset(self, tenant_id: str, category: str = "") -> None:
        self._repository.reset(tenant_id, category=category)

    def period_usage(self, tenant_id: str, period_start: float, period_end: float) -> dict[str, int]:
        return self.usage_by_category(tenant_id, since=period_start)
