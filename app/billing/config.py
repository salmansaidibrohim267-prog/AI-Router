from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class BillingConfig:
    currency: str = "USD"
    tax_rate: float = 0.0
    default_provider: str = "manual"
    default_interval: str = "monthly"
    trial_days: int = 14
    grace_days: int = 3
    invoice_prefix: str = "AIR-"
    invoice_due_days: int = 7
    webhook_secret: str = ""
    track_metrics: bool = True
    log_events: bool = True
    audit_enabled: bool = True
    default_free_plan: str = "free"
    prorate_changes: bool = True
    auto_renew: bool = True
    plan_version: int = 1
    provider_settings: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> BillingConfig:
        return cls(
            currency=os.getenv("BIL_CURRENCY", "USD"),
            tax_rate=float(os.getenv("BIL_TAX_RATE", "0")),
            default_provider=os.getenv("BIL_DEFAULT_PROVIDER", "manual"),
            default_interval=os.getenv("BIL_DEFAULT_INTERVAL", "monthly"),
            trial_days=int(os.getenv("BIL_TRIAL_DAYS", "14")),
            grace_days=int(os.getenv("BIL_GRACE_DAYS", "3")),
            invoice_prefix=os.getenv("BIL_INVOICE_PREFIX", "AIR-"),
            invoice_due_days=int(os.getenv("BIL_INVOICE_DUE_DAYS", "7")),
            webhook_secret=os.getenv("BIL_WEBHOOK_SECRET", ""),
            track_metrics=os.getenv("BIL_TRACK_METRICS", "1") == "1",
            log_events=os.getenv("BIL_LOG_EVENTS", "1") == "1",
            audit_enabled=os.getenv("BIL_AUDIT_ENABLED", "1") == "1",
            default_free_plan=os.getenv("BIL_DEFAULT_FREE_PLAN", "free"),
            prorate_changes=os.getenv("BIL_PRORATE_CHANGES", "1") == "1",
            auto_renew=os.getenv("BIL_AUTO_RENEW", "1") == "1",
        )
