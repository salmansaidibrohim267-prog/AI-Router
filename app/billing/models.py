from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class PlanTier(Enum):
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    TEAM = "team"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class BillingInterval(Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(Enum):
    TRIAL = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class UsageCategory(Enum):
    TOKENS = "tokens"
    API_REQUESTS = "api_requests"
    VECTOR_STORAGE = "vector_storage"
    EMBEDDINGS = "embeddings"
    MCP_CALLS = "mcp_calls"
    PLUGINS = "plugins"
    UPLOADS = "uploads"
    ACTIVE_USERS = "active_users"


class InvoiceStatus(Enum):
    DRAFT = "draft"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


class PaymentStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProviderName(Enum):
    STRIPE = "stripe"
    PADDLE = "paddle"
    LEMON_SQUEEZY = "lemonsqueezy"
    MIDTRANS = "midtrans"
    XENDIT = "xendit"
    PAYPAL = "paypal"
    MANUAL = "manual"


class CouponType(Enum):
    PERCENT = "percent"
    FIXED_AMOUNT = "fixed_amount"
    TRIAL_EXTENSION = "trial_extension"


class DiscountType(Enum):
    NONE = "none"
    PERCENT = "percent"
    FIXED = "fixed"


class BillingEventType(Enum):
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    SUBSCRIPTION_RESUMED = "subscription.resumed"
    SUBSCRIPTION_PAUSED = "subscription.paused"
    INVOICE_CREATED = "invoice.created"
    INVOICE_PAID = "invoice.paid"
    INVOICE_OVERDUE = "invoice.overdue"
    PAYMENT_RECORDED = "payment.recorded"
    QUOTA_SYNCED = "quota.synced"


@dataclass
class Plan:
    id: str
    name: str
    tier: PlanTier
    price_monthly: float
    price_annual: float
    limits: dict[str, int] = field(default_factory=dict)
    features: list[str] = field(default_factory=list)
    supports_trial: bool = True
    is_custom: bool = False
    pricing_strategy: str = "flat"
    metadata: dict[str, Any] = field(default_factory=dict)

    def price_for(self, interval: str) -> float:
        if interval == "annual":
            return self.price_annual
        return self.price_monthly


@dataclass
class UsageMeter:
    category: UsageCategory
    unit: str
    limit: int = 0
    used: int = 0
    overage: bool = False


@dataclass
class UsageRecord:
    tenant_id: str
    category: UsageCategory
    amount: int
    recorded_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Subscription:
    id: str
    tenant_id: str
    plan_id: str
    status: SubscriptionStatus = SubscriptionStatus.TRIAL
    interval: str = "monthly"
    seats: int = 1
    price: float = 0.0
    started_at: float = field(default_factory=time.time)
    current_period_start: float = field(default_factory=time.time)
    current_period_end: float = field(default_factory=time.time)
    trial_end: float = 0.0
    grace_end: float = 0.0
    cancel_at_period_end: bool = False
    cancelled_at: float = 0.0
    auto_renew: bool = True
    provider: str = "manual"
    provider_subscription_id: str = ""
    coupon_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "plan_id": self.plan_id,
            "status": self.status.value,
            "interval": self.interval,
            "seats": self.seats,
            "price": self.price,
            "current_period_end": self.current_period_end,
            "provider": self.provider,
            "cancel_at_period_end": self.cancel_at_period_end,
        }


@dataclass
class InvoiceLine:
    description: str
    quantity: int
    unit_amount: float
    category: str = ""

    @property
    def amount(self) -> float:
        return round(self.quantity * self.unit_amount, 4)


@dataclass
class Invoice:
    id: str
    number: str
    tenant_id: str
    subscription_id: str
    lines: list[InvoiceLine] = field(default_factory=list)
    subtotal: float = 0.0
    discount: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    currency: str = "USD"
    status: InvoiceStatus = InvoiceStatus.DRAFT
    period_start: float = 0.0
    period_end: float = 0.0
    due_at: float = 0.0
    paid_at: float = 0.0
    coupon_code: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "tenant_id": self.tenant_id,
            "subscription_id": self.subscription_id,
            "subtotal": self.subtotal,
            "discount": self.discount,
            "tax": self.tax,
            "total": self.total,
            "currency": self.currency,
            "status": self.status.value,
        }


@dataclass
class Payment:
    id: str
    tenant_id: str
    invoice_id: str
    amount: float
    provider: str
    method: str = ""
    status: PaymentStatus = PaymentStatus.PENDING
    reference: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Coupon:
    code: str
    type: CouponType
    value: float
    max_redemptions: int = 0
    redemptions: int = 0
    expires_at: float = 0.0
    applies_to: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class BillingEvent:
    type: BillingEventType
    tenant_id: str = ""
    subscription_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class InvoiceSummary:
    invoice_id: str
    number: str
    total: float
    status: str
    period_start: float
    period_end: float


class BillingAuditLogger:
    def __init__(self, config: Any, logger: BillingLogger) -> None:
        self._config = config
        self._logger = logger

    @property
    def enabled(self) -> bool:
        return bool(self._config.audit_enabled)

    def record(self, action: str, tenant_id: str = "", **details: Any) -> None:
        if not self.enabled:
            return
        self._logger.log_event(
            "audit",
            action=action,
            tenant_id=tenant_id,
            **details,
        )
