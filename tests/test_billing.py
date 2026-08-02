"""Stage 10.5 — Billing & Subscription platform tests."""
from __future__ import annotations

import os
import time

import pytest

from app.billing import (
    BillingConfig,
    BillingError,
    BillingEventBus,
    BillingEventType,
    BillingLogger,
    BillingManager,
    BillingMetricsTracker,
    BillingWebhookHandler,
    CouponExpiredError,
    CouponExhaustedError,
    CouponInvalidError,
    CouponManager,
    CouponNotFoundError,
    CouponType,
    GatewayQuotaTarget,
    InvalidTransitionError,
    InvoiceAlreadyPaidError,
    InvoiceError,
    InvoiceNotFoundError,
    InvoiceNumberStrategy,
    InvoiceService,
    InvoiceStatus,
    LemonSqueezyProvider,
    MCPQuotaTarget,
    ManualInvoiceProvider,
    MidtransProvider,
    PaddleProvider,
    PaymentError,
    PaymentFailedError,
    PaymentProvider,
    PaymentProviderFactory,
    PaymentStatus,
    PayPalProvider,
    PerSeatPricingStrategy,
    PlanCatalog,
    PlanNotFoundError,
    PluginQuotaTarget,
    PricingEngine,
    PricingStrategyFactory,
    ProviderConfigurationError,
    QuotaSyncCoordinator,
    QuotaSyncError,
    QuotaSyncTarget,
    RateLimiterQuotaTarget,
    StripeProvider,
    SubscriptionAlreadyExistsError,
    SubscriptionCancelledError,
    GracePeriodExceededError,
    SubscriptionLifecycle,
    SubscriptionNotFoundError,
    SubscriptionStatus,
    TaxCalculator,
    TrialNotAllowedError,
    TieredPricingStrategy,
    UsageBasedPricingStrategy,
    UsageCategory,
    UsageMeter,
    UsageRecordingError,
    VectorStoreQuotaTarget,
    WebhookEventError,
    WebhookVerificationError,
    XenditProvider,
    create_billing_manager,
    generate_id,
)
from app.billing.invoicing import InvoiceService as IS
from app.billing.lifecycle import SubscriptionState, SubscriptionStateFactory
from app.billing.logging import BillingLogger as BL
from app.billing.metrics import BillingMetricsTracker as BMT
from app.billing.models import (
    BillingAuditLogger,
    Coupon,
    Invoice,
    InvoiceLine,
    Payment,
    Plan,
    PlanTier,
    Subscription,
    UsageMeter as UsageMeterModel,
    UsageRecord,
)
from app.billing.plans import FlatPricingStrategy
from app.billing.providers import PaymentProviderFactory as PPF
from app.billing.repository import (
    BillingRepositories,
    InMemoryCouponRepository,
    InMemoryInvoiceRepository,
    InMemoryPaymentRepository,
    InMemorySubscriptionRepository,
    InMemoryUsageRepository,
)
from app.billing.usage import UsageMeter as UsageMeterService
from app.gateway.quota import QuotaManager
from app.gateway.ratelimit import RateLimiter

DAY = 86400


def make_config(**overrides) -> BillingConfig:
    base = dict(trial_days=7, grace_days=2, prorate_changes=True, auto_renew=True)
    base.update(overrides)
    return BillingConfig(**base)


def make_manager(**overrides) -> BillingManager:
    return create_billing_manager(make_config(**overrides.pop("config_kwargs", {})), **overrides)


def transport(status: int = 200, body: str = "ok"):
    def fake(url: str, data: dict) -> dict:
        return {"status": status, "body": body}

    return fake


# ---------------------------------------------------------------- exceptions


def test_subscription_cancelled_and_trial_exceptions():
    assert SubscriptionCancelledError("s1").details["subscription_id"] == "s1"
    assert TrialNotAllowedError("free").details["plan_id"] == "free"
    assert GracePeriodExceededError("s1").details["subscription_id"] == "s1"


def test_exceptions_defaults():
    assert BillingError("boom").message == "boom"
    assert BillingError("boom", code=1).details == {"code": 1}
    assert PlanNotFoundError("x").status_code == 404
    assert SubscriptionNotFoundError("x").status_code == 404
    assert SubscriptionAlreadyExistsError("t").status_code == 409
    assert InvalidTransitionError("active", "cancelled").details == {"current": "active", "target": "cancelled"}
    assert InvoiceNotFoundError("i").status_code == 404
    assert InvoiceAlreadyPaidError("i").status_code == 409
    assert PaymentFailedError("no", code=5).details == {"code": 5}
    assert PaymentError().message == "Payment operation failed"
    assert PaymentError().status_code == 500
    assert ProviderConfigurationError("stripe", "unknown").details == {"provider": "stripe", "detail": "unknown"}
    assert CouponNotFoundError("X").details["code"] == "X"
    assert CouponExpiredError("X").details["code"] == "X"
    assert CouponExhaustedError("X").details["code"] == "X"
    assert CouponInvalidError("X", "nope").details["reason"] == "nope"
    assert WebhookVerificationError("stripe").details["provider"] == "stripe"
    assert WebhookEventError("bad").status_code == 422
    assert QuotaSyncError("mcp").details == {"target": "mcp", "detail": "failed to apply limits"}


# ------------------------------------------------------------------- config


def test_config_defaults_and_from_env():
    config = BillingConfig()
    assert config.currency == "USD"
    assert config.trial_days == 14
    assert config.grace_days == 3
    assert config.invoice_prefix == "AIR-"
    assert config.default_provider == "manual"
    os.environ["BIL_CURRENCY"] = "EUR"
    os.environ["BIL_TAX_RATE"] = "0.1"
    os.environ["BIL_TRIAL_DAYS"] = "5"
    os.environ["BIL_GRACE_DAYS"] = "1"
    os.environ["BIL_WEBHOOK_SECRET"] = "sec"
    os.environ["BIL_PRORATE_CHANGES"] = "0"
    os.environ["BIL_AUTO_RENEW"] = "0"
    os.environ["BIL_TRACK_METRICS"] = "0"
    try:
        env = BillingConfig.from_env()
        assert env.currency == "EUR"
        assert env.tax_rate == 0.1
        assert env.trial_days == 5
        assert env.grace_days == 1
        assert env.webhook_secret == "sec"
        assert env.prorate_changes is False
        assert env.auto_renew is False
        assert env.track_metrics is False
    finally:
        for key in ("BIL_CURRENCY", "BIL_TAX_RATE", "BIL_TRIAL_DAYS", "BIL_GRACE_DAYS", "BIL_WEBHOOK_SECRET", "BIL_PRORATE_CHANGES", "BIL_AUTO_RENEW", "BIL_TRACK_METRICS"):
            os.environ.pop(key, None)


# ------------------------------------------------------------------- logger


def test_logger_events_and_disable():
    logger = BillingLogger(make_config(log_events=True))
    logger.log_event("test", tenant_id="t1")
    assert logger.events[0]["event"] == "billing_test"
    assert logger.events[0]["data"]["tenant_id"] == "t1"
    silent = BillingLogger(make_config(log_events=False))
    silent.log_event("x")
    assert silent.events == []


# ------------------------------------------------------------------ metrics


def test_metrics_mrr_arr_churn_conversion():
    metrics = BillingMetricsTracker(make_config())
    metrics.record_subscription("t1", "professional", "active", 99.0)
    metrics.record_subscription("t2", "starter", "trialing", 29.0)
    metrics.record_subscription("t3", "free", "cancelled", 0.0)
    assert metrics.mrr() == 12800
    assert metrics.arr() == 153600
    summary = metrics.summary()
    assert summary["active_subscriptions"] == 1
    assert summary["trialing_subscriptions"] == 1
    assert summary["cancelled_subscriptions"] == 1
    assert summary["by_plan"] == {"professional": 9900, "starter": 2900}
    assert metrics.churn_rate(2, 100) == 0.02
    assert metrics.churn_rate(1, 0) == 0.0
    assert metrics.conversion_rate(3, 10) == 0.3
    assert metrics.conversion_rate(1, 0) == 0.0


def test_metrics_annual_and_latest_wins_and_disabled():
    metrics = BillingMetricsTracker(make_config())
    metrics.record_subscription("t1", "starter", "active", 290.0, interval="annual")
    assert metrics.mrr() == 2417
    metrics.record_subscription("t1", "starter", "active", 290.0, interval="annual")
    assert metrics.mrr() == 2417
    metrics.record_subscription("t1", "starter", "cancelled", 290.0, interval="annual")
    assert metrics.mrr() == 0
    disabled = BillingMetricsTracker(make_config(track_metrics=False))
    assert disabled.record_subscription("t1", "x", "active", 10.0) == {}
    assert disabled.mrr() == 0
    assert disabled.summary()["mrr"] == 0


# ------------------------------------------------------------------- models


def test_models_helpers():
    assert generate_id("sub").startswith("sub_")
    line = InvoiceLine(description="d", quantity=2, unit_amount=3.5)
    assert line.amount == 7.0
    plan = Plan(id="p", name="P", tier=PlanTier.FREE, price_monthly=10.0, price_annual=100.0)
    assert plan.price_for("annual") == 100.0
    assert plan.price_for("monthly") == 10.0
    sub = Subscription(id="s", tenant_id="t", plan_id="p", status=SubscriptionStatus.ACTIVE)
    assert sub.to_dict()["status"] == "active"
    invoice = Invoice(id="i", number="N", tenant_id="t", subscription_id="s")
    assert invoice.to_dict()["status"] == "draft"
    audit = BillingAuditLogger(make_config(audit_enabled=False), BillingLogger())
    audit.record("x", tenant_id="t")
    enabled = BillingAuditLogger(make_config(audit_enabled=True), BillingLogger(make_config(log_events=True)))
    enabled.record("subscription.created", tenant_id="t", plan="p")
    assert enabled._logger.events[-1]["data"]["action"] == "subscription.created"
    assert enabled.enabled is True
    assert audit.enabled is False


# ------------------------------------------------------------------- plans


def test_plan_catalog():
    catalog = PlanCatalog()
    assert catalog.get("free").name == "Free"
    assert catalog.get("custom").is_custom is True
    assert len(catalog.all()) == 6
    assert "enterprise" in catalog.ids()
    with pytest.raises(PlanNotFoundError):
        catalog.get("nope")
    custom = Plan(id="c1", name="C1", tier=PlanTier.CUSTOM, price_monthly=5, price_annual=50)
    catalog.register(custom)
    assert catalog.get("c1") is custom
    assert catalog.remove("c1") is True
    assert catalog.remove("c1") is False
    assert catalog.limits_for("free")["tokens"] == 100000


def test_pricing_strategies():
    plan = Plan(id="p", name="P", tier=PlanTier.STARTER, price_monthly=100.0, price_annual=900.0)
    assert FlatPricingStrategy().compute(plan, seats=2) == 200.0
    assert PerSeatPricingStrategy().compute(plan, seats=3) == 300.0
    tiered = Plan(id="t", name="T", tier=PlanTier.TEAM, price_monthly=100.0, price_annual=900.0,
                  limits={"tiers": [{"dimension": "api_requests", "threshold": 1000, "price": 50.0}]})
    assert TieredPricingStrategy().compute(tiered, usage={"api_requests": 5000}) == 150.0
    assert TieredPricingStrategy().compute(tiered, usage={"api_requests": 100}) == 100.0
    usage_plan = Plan(id="u", name="U", tier=PlanTier.PROFESSIONAL, price_monthly=50.0, price_annual=450.0,
                      limits={"tokens": 1000}, metadata={"tokens_rate": 0.02})
    assert UsageBasedPricingStrategy().compute(usage_plan, usage={"tokens": 2000}) == 70.0
    assert UsageBasedPricingStrategy().compute(usage_plan, usage={"tokens": 500}) == 50.0


def test_pricing_strategy_factory():
    assert PricingStrategyFactory.create("tiered").name() == "tiered"
    assert PricingStrategyFactory.create("nope").name() == "flat"
    assert PricingStrategyFactory.create("per_seat").name() == "per_seat"
    assert isinstance(PricingStrategyFactory.create("per_seat"), PerSeatPricingStrategy)


def test_pricing_engine():
    engine = PricingEngine()
    result = engine.price("starter", seats=2)
    assert result["amount"] == 58.0
    assert result["interval"] == "monthly"
    annual = engine.price("starter", interval="annual")
    assert annual["amount"] == 290.0
    custom = engine.create_custom_plan("c-xyz", "Xyz Corp", 500.0, limits={"tokens": 999999})
    assert custom.is_custom is True
    assert engine.price("c-xyz")["amount"] == 500.0
    assert engine.price("c-xyz", interval="annual")["amount"] == 5000.0
    assert engine.catalog is engine.catalog


# --------------------------------------------------------------- repositories


def test_subscription_repository():
    repo = InMemorySubscriptionRepository()
    sub = Subscription(id="s1", tenant_id="t1", plan_id="free")
    repo.create(sub)
    assert repo.get("s1") is sub
    assert repo.by_tenant("t1") is sub
    assert repo.by_tenant("missing") is None
    sub.seats = 2
    repo.update(sub)
    assert repo.get("s1").seats == 2
    assert len(repo.list()) == 1
    with pytest.raises(SubscriptionNotFoundError):
        repo.get("nope")
    with pytest.raises(SubscriptionNotFoundError):
        repo.update(Subscription(id="nope", tenant_id="t", plan_id="free"))
    assert repo.delete("s1") is True
    assert repo.delete("s1") is False


def test_invoice_repository():
    repo = InMemoryInvoiceRepository()
    invoice = Invoice(id="i1", number="AIR-1", tenant_id="t1", subscription_id="s1")
    repo.create(invoice)
    assert repo.get("i1") is invoice
    invoice.status = InvoiceStatus.PAID
    repo.update(invoice)
    assert repo.get("i1").status == InvoiceStatus.PAID
    assert len(repo.list()) == 1
    assert len(repo.list("t1")) == 1
    assert len(repo.list("other")) == 0
    assert repo.count() == 1
    with pytest.raises(InvoiceNotFoundError):
        repo.get("nope")
    with pytest.raises(InvoiceNotFoundError):
        repo.update(Invoice(id="nope", number="X", tenant_id="t", subscription_id="s"))


def test_payment_repository():
    repo = InMemoryPaymentRepository()
    payment = Payment(id="p1", tenant_id="t1", invoice_id="i1", amount=10.0, provider="manual")
    repo.create(payment)
    assert repo.get("p1") is payment
    payment.status = PaymentStatus.COMPLETED
    repo.update(payment)
    assert repo.get("p1").status == PaymentStatus.COMPLETED
    assert len(repo.list("t1")) == 1
    assert len(repo.list("other")) == 0
    with pytest.raises(BillingError):
        repo.get("nope")
    with pytest.raises(BillingError):
        repo.update(Payment(id="nope", tenant_id="t", invoice_id="i", amount=1, provider="m"))


def test_coupon_repository():
    repo = InMemoryCouponRepository()
    coupon = Coupon(code="SAVE10", type=CouponType.PERCENT, value=10.0)
    repo.create(coupon)
    assert repo.get("save10") is coupon
    assert repo.get("SAVE10").code == "SAVE10"
    coupon.value = 20.0
    repo.update(coupon)
    assert repo.get("SAVE10").value == 20.0
    assert len(repo.list()) == 1
    assert repo.delete("save10") is True
    assert repo.delete("save10") is False
    with pytest.raises(CouponNotFoundError):
        repo.get("SAVE10")
    with pytest.raises(CouponNotFoundError):
        repo.update(Coupon(code="nope", type=CouponType.PERCENT, value=1.0))


def test_usage_repository():
    repo = InMemoryUsageRepository()
    repo.record(UsageRecord(tenant_id="t1", category=UsageCategory.TOKENS, amount=10, recorded_at=100.0))
    repo.record(UsageRecord(tenant_id="t1", category=UsageCategory.TOKENS, amount=5, recorded_at=200.0))
    repo.record(UsageRecord(tenant_id="t1", category=UsageCategory.MCP_CALLS, amount=2, recorded_at=150.0))
    repo.record(UsageRecord(tenant_id="t2", category=UsageCategory.TOKENS, amount=99, recorded_at=100.0))
    assert repo.usage("t1", "tokens", since=0.0) == 15
    assert repo.usage("t1", "tokens", since=150.0) == 5
    assert repo.usage("t1", "embeddings") == 0
    assert repo.usage_by_category("t1", since=0.0) == {"tokens": 15, "mcp_calls": 2}
    repo.reset("t1", "tokens")
    assert repo.usage("t1", "tokens") == 0
    assert repo.usage("t1", "mcp_calls") == 2
    repo.reset("t1")
    assert repo.usage_by_category("t1") == {}


def test_billing_repositories_aggregate():
    repos = BillingRepositories()
    assert isinstance(repos.subscriptions, InMemorySubscriptionRepository)
    assert isinstance(repos.invoices, InMemoryInvoiceRepository)
    assert isinstance(repos.payments, InMemoryPaymentRepository)
    assert isinstance(repos.coupons, InMemoryCouponRepository)
    assert isinstance(repos.usage, InMemoryUsageRepository)
    assert set(repos.as_dict().keys()) == {"subscriptions", "invoices", "payments", "coupons", "usage"}


# --------------------------------------------------------------------- usage


def test_usage_meter():
    meter = UsageMeterService()
    meter.record("t1", "tokens", 100)
    meter.record("t1", UsageCategory.API_REQUESTS, 5)
    assert meter.usage("t1", "tokens") == 100
    assert meter.usage("t1", UsageCategory.API_REQUESTS) == 5
    assert meter.usage("t1", "tokens", since=time.time() + 1) == 0
    with pytest.raises(UsageRecordingError):
        meter.record("t1", "bogus")
    with pytest.raises(UsageRecordingError):
        meter.record("t1", "tokens", amount=-1)
    assert meter.repository is meter.repository
    snapshot = meter.snapshot("t1", limits={"tokens": 100, "api_requests": 10})
    by_key = {item.category.value: item for item in snapshot}
    assert by_key["tokens"].used == 100
    assert by_key["tokens"].overage is False
    assert by_key["api_requests"].overage is False
    assert by_key["embeddings"].used == 0
    overage_meter = UsageMeterService()
    overage_meter.record("t2", "tokens", 200)
    over = overage_meter.snapshot("t2", limits={"tokens": 100})[0]
    assert over.overage is True
    meter.reset("t1", "tokens")
    assert meter.usage("t1", "tokens") == 0
    assert meter.usage("t1", "api_requests") == 5
    meter.reset("t1")
    assert meter.usage_by_category("t1") == {}
    assert meter.period_usage("t1", time.time() - 10, time.time()) == {}


# ---------------------------------------------------------------- providers


def test_provider_factory():
    assert PPF.create("stripe") .name == "stripe"
    assert PPF.create("paddle").name == "paddle"
    assert PPF.create("lemonsqueezy").name == "lemonsqueezy"
    assert PPF.create("midtrans").name == "midtrans"
    assert PPF.create("xendit").name == "xendit"
    assert PPF.create("paypal").name == "paypal"
    assert PPF.create("manual").name == "manual"
    assert set(PPF.names()) == {"stripe", "paddle", "lemonsqueezy", "midtrans", "xendit", "paypal", "manual"}
    with pytest.raises(ProviderConfigurationError):
        PPF.create("nope")


def test_provider_requires_configuration():
    provider = StripeProvider()
    with pytest.raises(ProviderConfigurationError):
        provider.charge("t", 10.0, "i")
    with pytest.raises(ProviderConfigurationError):
        provider.refund(Payment(id="p", tenant_id="t", invoice_id="i", amount=1, provider="stripe"))


def test_stripe_provider():
    ok = StripeProvider(secret="s", settings={"transport": transport(200)})
    payment = ok.charge("t", 10.0, "inv1")
    assert payment.status == PaymentStatus.COMPLETED
    assert payment.provider == "stripe"
    assert payment.invoice_id == "inv1"
    declined = StripeProvider(secret="s", settings={"transport": transport(402)})
    with pytest.raises(PaymentFailedError):
        declined.charge("t", 10.0, "inv2")
    down = StripeProvider(secret="s", settings={"transport": transport(0)})
    with pytest.raises(PaymentError):
        down.charge("t", 10.0, "inv3")
    refund = ok.refund(payment)
    assert refund.status == PaymentStatus.REFUNDED


def test_other_providers_charge():
    cases = [
        (PaddleProvider(secret="s", settings={"transport": transport(200)}), PaymentStatus.COMPLETED, 200),
        (LemonSqueezyProvider(secret="s", settings={"transport": transport(200)}), PaymentStatus.COMPLETED, 200),
        (MidtransProvider(secret="s", settings={"transport": transport(201)}), PaymentStatus.PENDING, 201),
        (XenditProvider(secret="s", settings={"transport": transport(200)}), PaymentStatus.PENDING, 200),
        (PayPalProvider(secret="s", settings={"transport": transport(201)}), PaymentStatus.COMPLETED, 201),
    ]
    for provider, expected_status, expected_code in cases:
        assert provider.configured is True
        payment = provider.charge("t", 5.0, "inv", method="card")
        assert payment.status == expected_status
        assert payment.provider == provider.name
        assert payment.amount == 5.0
        refunded = provider.refund(payment)
        assert refunded.status == PaymentStatus.REFUNDED


def test_provider_decline_paths():
    with pytest.raises(PaymentFailedError):
        PaddleProvider(secret="s", settings={"transport": transport(400)}).charge("t", 5.0, "i")
    with pytest.raises(PaymentFailedError):
        LemonSqueezyProvider(secret="s", settings={"transport": transport(400)}).charge("t", 5.0, "i")
    with pytest.raises(PaymentFailedError):
        MidtransProvider(secret="s", settings={"transport": transport(400)}).charge("t", 5.0, "i")
    with pytest.raises(PaymentFailedError):
        XenditProvider(secret="s", settings={"transport": transport(400)}).charge("t", 5.0, "i")
    with pytest.raises(PaymentFailedError):
        PayPalProvider(secret="s", settings={"transport": transport(400)}).charge("t", 5.0, "i")


def test_manual_invoice_provider():
    provider = ManualInvoiceProvider()
    assert provider.configured is True
    payment = provider.charge("t", 10.0, "inv1", method="bank_transfer")
    assert payment.status == PaymentStatus.PENDING
    assert payment.method == "bank_transfer"
    assert payment.reference.startswith("inv_")
    assert provider.refund(payment).status == PaymentStatus.REFUNDED


def test_provider_webhook_verification():
    import hashlib
    import hmac

    secret = "topsecret"
    payload = '{"type":"payment.succeeded"}'
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    provider = StripeProvider(secret=secret)
    assert provider.verify_webhook(payload, signature) is True
    assert provider.verify_webhook(payload, "bad") is False
    empty = StripeProvider()
    assert empty.verify_webhook(payload, "") is False


# ------------------------------------------------------------------- coupons


def test_coupon_manager_lifecycle():
    manager = CouponManager()
    coupon = manager.create("SAVE20", "percent", value=20.0, max_redemptions=2)
    assert coupon.type == CouponType.PERCENT
    assert manager.get("save20").code == "SAVE20"
    validated = manager.validate("SAVE20", plan_id="free")
    assert validated is coupon
    assert manager.redeem("SAVE20").redemptions == 1
    assert manager.redeem("SAVE20").redemptions == 2
    with pytest.raises(CouponExhaustedError):
        manager.redeem("SAVE20")
    with pytest.raises(CouponNotFoundError):
        manager.validate("NOPE")


def test_coupon_discounts():
    manager = CouponManager()
    manager.create("PCT", "percent", value=10.0)
    manager.create("FIX", "fixed_amount", value=15.0)
    manager.create("TRIAL", "trial_extension", value=7.0)
    amount, description = manager.discount("PCT", 100.0)
    assert amount == 10.0
    assert "10%" in description
    amount, description = manager.discount("FIX", 100.0)
    assert amount == 15.0
    amount, description = manager.discount("FIX", 10.0)
    assert amount == 10.0
    amount, description = manager.discount("TRIAL", 100.0)
    assert amount == 0.0
    assert description == ""


def test_coupon_expiry_and_applicability():
    manager = CouponManager()
    manager.create("OLD", "percent", value=5.0, expires_at=time.time() - 10)
    with pytest.raises(CouponExpiredError):
        manager.validate("OLD")
    manager.create("PLANONLY", "percent", value=5.0, applies_to=["starter"])
    with pytest.raises(CouponInvalidError):
        manager.validate("PLANONLY", plan_id="free")
    assert manager.validate("PLANONLY", plan_id="starter") is not None
    assert len(manager.list()) == 2
    assert manager.delete("PLANONLY") is True
    assert manager.delete("PLANONLY") is False


# ----------------------------------------------------------------- taxation


def test_tax_calculator():
    tax = TaxCalculator(make_config(tax_rate=0.1))
    assert tax.rate_for("") == 0.1
    assert tax.rate_for("US") == 0.0
    assert tax.rate_for("GB") == 0.2
    assert tax.rate_for("DE") == 0.19
    assert tax.rate_for("SG") == 0.09
    assert tax.rate_for("ID") == 0.11
    assert tax.rate_for("XX") == 0.1
    assert tax.tax(100.0) == 10.0
    assert tax.tax(100.0, "GB") == 20.0
    assert tax.tax_details(100.0, "GB") == {"rate": 0.2, "amount": 20.0}
    tax.register_jurisdiction("FR", 0.2)
    assert tax.rate_for("FR") == 0.2
    assert tax.jurisdictions["FR"] == 0.2


# ---------------------------------------------------------------- invoicing


def test_invoice_number_strategy():
    strategy = InvoiceNumberStrategy("INV-", start=5)
    assert strategy.next() == "INV-0005"
    assert strategy.next() == "INV-0006"
    assert strategy.last == "INV-0006"
    strategy.from_count(100)
    assert strategy.next() == "INV-0101"


def test_invoice_service_draft_and_build():
    config = make_config(currency="USD", tax_rate=0.2, invoice_prefix="AIR-", invoice_due_days=7)
    coupons = CouponManager()
    invoices = IS(config, coupons=coupons, tax=TaxCalculator(config))
    sub = Subscription(id="s1", tenant_id="t1", plan_id="starter", interval="monthly", seats=2)
    plan = PlanCatalog().get("starter")
    draft = invoices.create_draft("t1", sub, plan, period_start=100.0, period_end=200.0)
    assert draft.status == InvoiceStatus.DRAFT
    assert draft.number == "AIR-0001"
    assert draft.due_at == 200.0 + 7 * DAY
    built = invoices.build(draft, plan, sub, usage={"tokens": 1000}, country_code="")
    assert built.status == InvoiceStatus.PENDING
    assert built.subtotal == 58.0
    assert built.tax == 11.6
    assert built.total == 69.6
    assert built.lines[1].description == "tokens usage"
    assert built.lines[1].quantity == 1000
    assert len(built.lines) == 2


def test_invoice_service_build_with_coupon_and_tax_rate():
    config = make_config(tax_rate=0.0)
    coupons = CouponManager()
    coupons.create("PCT10", "percent", value=10.0)
    invoices = IS(config, coupons=coupons, tax=TaxCalculator(config))
    sub = Subscription(id="s1", tenant_id="t1", plan_id="starter", interval="monthly")
    plan = PlanCatalog().get("starter")
    draft = invoices.create_draft("t1", sub, plan, period_start=100.0, period_end=200.0)
    built = invoices.build(draft, plan, sub, usage={}, coupon_code="pct10", country_code="GB")
    assert built.coupon_code == "PCT10"
    assert built.discount == 2.9
    assert built.subtotal == 29.0
    assert built.tax == pytest.approx(5.22)
    assert built.total == pytest.approx(31.32)
    custom_rate = invoices.build(invoices.create_draft("t1", sub, plan, 1.0, 2.0), plan, sub, tax_rate=0.05)
    assert custom_rate.tax == pytest.approx(1.45)


def test_invoice_service_itemize_void_paid():
    config = make_config(tax_rate=0.1)
    invoices = IS(config, tax=TaxCalculator(config))
    sub = Subscription(id="s1", tenant_id="t1", plan_id="free", interval="monthly")
    plan = PlanCatalog().get("free")
    draft = invoices.create_draft("t1", sub, plan, 1.0, 2.0)
    itemized = invoices.itemize(draft, [InvoiceLine("one", 1, 10.0), InvoiceLine("two", 2, 5.0)])
    assert itemized.subtotal == 20.0
    assert itemized.tax == 2.0
    assert itemized.total == 22.0
    voided = invoices.void(draft.id)
    assert voided.status == InvoiceStatus.VOID
    paid = invoices.create_draft("t1", sub, plan, 1.0, 2.0)
    invoices.mark_paid(paid.id)
    assert paid.status == InvoiceStatus.PAID
    with pytest.raises(InvoiceError):
        invoices.void(paid.id)
    assert invoices.mark_paid(paid.id).status == InvoiceStatus.PAID
    summaries = invoices.summaries("t1")
    assert len(summaries) == 2
    assert summaries[0].total == 22.0
    assert summaries[0].status == "void"
    assert summaries[1].status == "paid"


# --------------------------------------------------------------- lifecycle


def test_lifecycle_states():
    lifecycle = SubscriptionLifecycle()
    assert lifecycle.allowed_transitions("trialing") == ["active", "cancelled", "past_due", "paused"]
    assert lifecycle.allowed_transitions(SubscriptionStatus.ACTIVE) == ["cancelled", "past_due", "paused", "trialing"]
    assert lifecycle.allowed_transitions("past_due") == ["active", "cancelled", "paused"]
    assert lifecycle.allowed_transitions("paused") == ["active", "cancelled"]
    assert lifecycle.allowed_transitions("cancelled") == ["active"]
    assert SubscriptionStateFactory.create("active").status == SubscriptionStatus.ACTIVE
    sub = Subscription(id="s", tenant_id="t", plan_id="p", status=SubscriptionStatus.ACTIVE)
    lifecycle.transition(sub, SubscriptionStatus.CANCELLED)
    assert sub.status == SubscriptionStatus.CANCELLED
    with pytest.raises(InvalidTransitionError):
        lifecycle.transition(sub, SubscriptionStatus.PAUSED)
    with pytest.raises(InvalidTransitionError):
        lifecycle.transition(sub, "trialing")
    resumed = Subscription(id="s2", tenant_id="t", plan_id="p", status=SubscriptionStatus.CANCELLED)
    lifecycle.transition(resumed, SubscriptionStatus.ACTIVE)
    assert resumed.status == SubscriptionStatus.ACTIVE


# -------------------------------------------------------------------- sync


def test_gateway_quota_target_real_quota_manager():
    quota = QuotaManager()
    target = GatewayQuotaTarget(quota)
    target.apply("t1", {"tokens": 5000, "api_requests": 100}, "starter")
    assert quota.limit_for("t1", "tokens") == 5000
    assert quota.limit_for("t1", "requests") == 100
    mapped = GatewayQuotaTarget(quota, bucket_mapping={"tokens": "storage"})
    mapped.apply("t2", {"tokens": 10, "api_requests": 5}, "starter")
    assert quota.limit_for("t2", "storage") == 10
    assert quota.limit_for("t2", "requests") == 5
    mapped.apply("t3", {"plugins": 999}, "starter")
    assert quota.limit_for("t3", "tokens") == 1000000


def test_gateway_quota_target_error():
    class Broken:
        def set_limit(self, scope, bucket, limit):
            raise RuntimeError("boom")

    target = GatewayQuotaTarget(Broken())
    with pytest.raises(QuotaSyncError):
        target.apply("t1", {"tokens": 1}, "starter")


def test_rate_limiter_quota_target_real_limiter():
    limiter = RateLimiter()
    target = RateLimiterQuotaTarget(limiter, window_seconds=3600.0)
    target.apply("t1", {"api_requests": 250}, "professional")
    policy = limiter.limiter_for("plan:t1")
    assert policy.limit == 250
    target.apply("t2", {"api_requests": 0}, "free")
    assert "plan:t2" not in limiter._policies


def test_vector_store_mcp_plugin_targets():
    vector = VectorStoreQuotaTarget()
    vector.apply("t1", {"vector_storage": 2000, "embeddings": 100}, "starter")
    assert vector.limits["t1"]["storage_bytes"] == 2000 * 1024
    assert vector.limits["t1"]["embeddings"] == 100
    assert vector.limits["t1"]["plan"] == "starter"
    mcp = MCPQuotaTarget()
    mcp.apply("t1", {"mcp_calls": 500}, "starter")
    assert mcp.limits["t1"]["mcp_calls"] == 500
    plugins = PluginQuotaTarget()
    plugins.apply("t1", {"plugins": 3, "uploads": 200}, "starter")
    assert plugins.limits["t1"]["plugins"] == 3
    assert plugins.limits["t1"]["uploads"] == 200


def test_quota_sync_coordinator():
    coordinator = QuotaSyncCoordinator(BillingLogger(make_config(log_events=True)))
    vector = VectorStoreQuotaTarget()
    coordinator.register(vector)
    assert coordinator.targets() == ["vector_store"]
    assert coordinator.unregister("vector_store") is True
    assert coordinator.unregister("vector_store") is False
    coordinator.register(vector)
    plan = PlanCatalog().get("starter")
    results = coordinator.sync("t1", plan)
    assert results == {"vector_store": "ok"}
    assert vector.limits["t1"]["embeddings"] == 100000
    assert coordinator._logger.events[-1]["data"]["plan_id"] == "starter"


def test_quota_sync_coordinator_partial_failure():
    class BrokenTarget(QuotaSyncTarget):
        name = "broken"

        def apply(self, scope, limits, plan_id):
            raise QuotaSyncError(self.name, detail="nope")

    coordinator = QuotaSyncCoordinator()
    coordinator.register(BrokenTarget())
    coordinator.register(VectorStoreQuotaTarget())
    results = coordinator.sync("t1", PlanCatalog().get("free"))
    assert results["broken"].startswith("Quota sync to 'broken'")
    assert results["vector_store"] == "ok"


def test_event_bus():
    bus = BillingEventBus()
    received = []

    def on_event(subscription, payload):
        received.append((subscription.id, payload))

    sub = Subscription(id="s1", tenant_id="t1", plan_id="free")
    bus.subscribe("subscription.created", on_event)
    assert bus.publish("subscription.created", sub, {"a": 1}) == 1
    assert received == [("s1", {"a": 1})]
    assert bus.publish("other.event", sub) == 0
    assert bus.unsubscribe("subscription.created", on_event) is True
    assert bus.unsubscribe("subscription.created", on_event) is False
    assert bus.publish("subscription.created", sub) == 0


# ---------------------------------------------------------------- webhooks


def test_webhook_handler_basic():
    handler = BillingWebhookHandler(logger=BillingLogger(make_config(log_events=True)))
    result = handler.handle("payment.succeeded", {"id": "evt1", "invoice_id": "inv1"})
    assert result["processed"] is True
    assert result["invoice_id"] == "inv1"
    duplicate = handler.handle("payment.succeeded", {"id": "evt1"})
    assert duplicate["processed"] is False
    assert duplicate["reason"] == "duplicate"
    assert handler.processed == 1
    assert len(handler.handlers) == 7


def test_webhook_handler_events():
    handler = BillingWebhookHandler()
    assert handler.handle("payment.failed", {"invoice_id": "i"})["failure_reason"] == "declined"
    assert handler.handle("invoice.overdue", {"subscription_id": "s"})["subscription_id"] == "s"
    assert handler.handle("subscription.updated", {"plan_id": "p"})["plan_id"] == "p"
    assert handler.handle("subscription.deleted", {"subscription_id": "s"})["subscription_id"] == "s"
    assert handler.handle("subscription.resumed", {"subscription_id": "s"})["subscription_id"] == "s"
    assert handler.handle("payment.succeeded", {})["payment_id"].startswith("wh_")
    with pytest.raises(WebhookEventError):
        handler.handle("unknown.event", {})
    with pytest.raises(WebhookEventError):
        handler.handle_payload({"data": {}})


def test_webhook_handler_signature():
    provider = StripeProvider(secret="sec")
    handler = BillingWebhookHandler(provider=provider)
    payload = {"type": "payment.succeeded", "invoice_id": "inv1"}
    import hashlib
    import hmac

    raw = '{"type":"payment.succeeded"}'
    signature = hmac.new(b"sec", raw.encode(), hashlib.sha256).hexdigest()
    result = handler.handle_payload({**payload, "_raw": raw}, signature=signature)
    assert result["processed"] is True
    with pytest.raises(WebhookVerificationError):
        handler.handle_payload({**payload, "_raw": raw}, signature="bogus")


# ---------------------------------------------------------------- manager


def test_create_subscription_trial_and_active():
    manager = make_manager()
    sub = manager.create_subscription("t1", "professional")
    assert sub.status == SubscriptionStatus.TRIAL
    assert sub.trial_end > sub.started_at
    assert sub.price == 99.0
    assert sub.interval == "monthly"
    assert sub.auto_renew is True
    no_trial = manager.create_subscription("t2", "free")
    assert no_trial.status == SubscriptionStatus.ACTIVE
    no_trial_plan = manager.create_subscription("t3", "enterprise", trial_days=0)
    assert no_trial_plan.status == SubscriptionStatus.ACTIVE
    assert no_trial_plan.trial_end == 0.0
    assert manager.get_subscription(sub.id) is sub
    assert manager.get_subscription_by_tenant("t1") is sub
    assert manager.get_subscription_by_tenant("ghost") is None
    assert len(manager.list_subscriptions()) == 3


def test_create_subscription_duplicate_and_reactivate():
    manager = make_manager()
    manager.create_subscription("t1", "starter")
    with pytest.raises(SubscriptionAlreadyExistsError):
        manager.create_subscription("t1", "professional")
    original = manager.get_subscription_by_tenant("t1")
    manager.cancel_subscription(original.id, at_period_end=False)
    reactivated = manager.create_subscription("t1", "professional")
    assert reactivated.id == original.id
    assert reactivated.status == SubscriptionStatus.TRIAL
    assert reactivated.trial_end > reactivated.started_at
    assert len(manager.list_subscriptions()) == 1


def test_create_subscription_with_coupon_and_annual():
    manager = make_manager()
    manager.create_coupon("WELCOME10", "percent", value=10.0)
    sub = manager.create_subscription("t1", "starter", interval="annual", coupon_code="welcome10")
    assert sub.coupon_code == "WELCOME10"
    assert sub.interval == "annual"
    assert sub.price == 290.0
    coupon = manager.coupons.get("WELCOME10")
    assert coupon.redemptions == 1


def test_create_subscription_metrics_and_events():
    manager = make_manager()
    events = []
    manager.event_bus.subscribe("subscription.created", lambda s, p: events.append(s.id))
    sub = manager.create_subscription("t1", "starter")
    assert events == [sub.id]
    assert manager.metrics_summary()["mrr"] == 2900
    assert manager.metrics_summary()["trialing_subscriptions"] == 1
    assert manager.audit.enabled is True


def test_change_plan_with_proration():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    changed = manager.change_plan(sub.id, "professional")
    assert changed.plan_id == "professional"
    assert changed.price == 99.0
    invoices = manager.list_invoices("t1")
    assert len(invoices) == 1
    assert invoices[0].lines[0].description.startswith("Plan change proration")
    assert manager.get_subscription_by_tenant("t1").plan_id == "professional"


def test_change_plan_downgrade_and_seats():
    manager = make_manager()
    sub = manager.create_subscription("t1", "professional", trial_days=0)
    manager.record_usage("t1", "tokens", 10)
    changed = manager.change_plan(sub.id, "starter", seats=2)
    assert changed.seats == 2
    assert changed.price == 58.0
    no_prorate = make_manager(config_kwargs={"prorate_changes": False})
    sub2 = no_prorate.create_subscription("t2", "starter", trial_days=0)
    no_prorate.change_plan(sub2.id, "professional")
    assert no_prorate.list_invoices("t2") == []
    cancelled = make_manager()
    sub3 = cancelled.create_subscription("t3", "starter", trial_days=0)
    cancelled.cancel_subscription(sub3.id, at_period_end=False)
    with pytest.raises(BillingError):
        cancelled.change_plan(sub3.id, "professional")


def test_cancel_subscription_at_period_end_and_immediate():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    flagged = manager.cancel_subscription(sub.id, at_period_end=True)
    assert flagged.status == SubscriptionStatus.ACTIVE
    assert flagged.cancel_at_period_end is True
    immediate = manager.cancel_subscription(sub.id, at_period_end=False)
    assert immediate.status == SubscriptionStatus.CANCELLED
    assert manager.cancel_subscription(sub.id) is immediate
    assert manager.metrics_summary()["cancelled_subscriptions"] == 1
    assert manager.metrics_summary()["mrr"] == 0


def test_cancel_trial_subscription():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter")
    assert sub.status == SubscriptionStatus.TRIAL
    cancelled = manager.cancel_subscription(sub.id)
    assert cancelled.status == SubscriptionStatus.CANCELLED
    assert cancelled.cancelled_at > 0


def test_resume_subscription():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.cancel_subscription(sub.id, at_period_end=False)
    resumed = manager.resume_subscription(sub.id)
    assert resumed.status == SubscriptionStatus.ACTIVE
    assert resumed.cancelled_at == 0.0
    manager.pause_subscription(sub.id)
    assert sub.status == SubscriptionStatus.PAUSED
    manager.resume_subscription(sub.id)
    assert sub.status == SubscriptionStatus.ACTIVE
    active = manager.create_subscription("t2", "starter", trial_days=0)
    with pytest.raises(BillingError):
        manager.resume_subscription(active.id)


def test_resume_with_plan_change_and_metrics():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.cancel_subscription(sub.id, at_period_end=False)
    resumed = manager.resume_subscription(sub.id, plan_id="professional")
    assert resumed.plan_id == "professional"
    assert resumed.price == 99.0
    assert resumed.current_period_end > resumed.current_period_start
    assert manager.metrics_summary()["active_subscriptions"] == 1


def test_convert_trial_and_past_due_flow():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter")
    converted = manager.convert_trial(sub.id)
    assert converted.status == SubscriptionStatus.ACTIVE
    assert converted.trial_end == 0.0
    assert manager.convert_trial(sub.id) is sub
    past_due = manager.mark_past_due(sub.id, reason="card_declined")
    assert past_due.status == SubscriptionStatus.PAST_DUE
    assert past_due.grace_end > time.time()


def test_grace_period_expiry():
    manager = make_manager(config_kwargs={"grace_days": 0})
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.mark_past_due(sub.id)
    sub.grace_end = time.time() - 1
    assert manager.get_subscription(sub.id).status == SubscriptionStatus.CANCELLED
    sub2 = manager.create_subscription("t2", "starter", trial_days=0)
    manager.mark_past_due(sub2.id)
    sub2.grace_end = time.time() + 100
    assert manager.get_subscription(sub2.id).status == SubscriptionStatus.PAST_DUE


def test_pause_subscription():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.pause_subscription(sub.id)
    assert sub.status == SubscriptionStatus.PAUSED
    assert manager.metrics_summary()["mrr"] == 0


def test_get_usage():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.record_usage("t1", "tokens", 1500)
    manager.record_usage("t1", "api_requests", 10)
    usage = manager.get_usage(sub.id)
    assert usage["plan_id"] == "starter"
    assert usage["usage"] == {"tokens": 1500, "api_requests": 10}
    meters = {meter["category"].value: meter for meter in usage["meters"]}
    assert meters["tokens"]["used"] == 1500
    assert meters["tokens"]["limit"] == 2000000
    assert meters["tokens"]["overage"] is False
    assert manager.get_tenant_usage("t1")["tokens"] == 1500
    with pytest.raises(UsageRecordingError):
        manager.record_usage("t1", "bad")


def test_generate_invoice_with_usage_and_coupon():
    manager = make_manager(config_kwargs={"tax_rate": 0.2})
    manager.create_coupon("PCT10", "percent", value=10.0)
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.record_usage("t1", "tokens", 1000)
    invoice = manager.generate_invoice(sub.id)
    assert invoice.status == InvoiceStatus.PENDING
    assert invoice.number.startswith("AIR-")
    assert invoice.subtotal == 29.0
    assert invoice.tax == pytest.approx(5.8)
    assert invoice.total == pytest.approx(34.8)
    invoice2 = manager.generate_invoice(sub.id, coupon_code="pct10", country_code="GB")
    assert invoice2.coupon_code == "PCT10"
    assert invoice2.discount == pytest.approx(2.9)
    assert invoice2.tax == pytest.approx(5.22)
    assert manager.get_invoice(invoice.id) is invoice
    assert len(manager.list_invoices("t1")) == 2
    assert len(manager.list_invoices("ghost")) == 0
    with pytest.raises(InvoiceNotFoundError):
        manager.get_invoice("nope")
    assert manager.get_invoice(manager.void_invoice(invoice2.id).id).status == InvoiceStatus.VOID
    assert len(manager.invoices.summaries("t1")) == 2


def test_record_payment_external_completes_trial():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter")
    invoice = manager.generate_invoice(sub.id)
    payment = manager.record_payment(invoice.id, external=True)
    assert payment.status == PaymentStatus.COMPLETED
    assert invoice.status == InvoiceStatus.PAID
    assert sub.status == SubscriptionStatus.ACTIVE
    assert invoice.paid_at > 0
    with pytest.raises(InvoiceAlreadyPaidError):
        manager.record_payment(invoice.id, external=True)
    assert manager.metrics_summary()["active_subscriptions"] == 1


def test_record_payment_manual_provider():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    payment = manager.record_payment(invoice.id, provider="manual", method="bank_transfer")
    assert payment.status == PaymentStatus.PENDING
    assert payment.provider == "manual"
    assert invoice.status != InvoiceStatus.PAID


def test_record_payment_stripe_provider():
    manager = make_manager()
    manager.register_provider(StripeProvider(secret="s", settings={"transport": transport(200)}))
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    payment = manager.record_payment(invoice.id, provider="stripe")
    assert payment.status == PaymentStatus.COMPLETED
    assert invoice.status == InvoiceStatus.PAID


def test_record_payment_failed_sets_past_due():
    manager = make_manager()
    manager.register_provider(StripeProvider(secret="s", settings={"transport": transport(402)}))
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    with pytest.raises(PaymentFailedError):
        manager.record_payment(invoice.id, provider="stripe")
    assert sub.status == SubscriptionStatus.PAST_DUE
    assert sub.grace_end > 0


def test_record_payment_provider_created_on_demand():
    manager = make_manager()
    manager.config.provider_settings["stripe"] = {"secret": "s", "settings": {"transport": transport(200)}}
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    payment = manager.record_payment(invoice.id, provider="stripe")
    assert payment.status == PaymentStatus.COMPLETED
    assert "stripe" in manager._providers


def test_record_payment_void_invoice():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    manager.void_invoice(invoice.id)
    with pytest.raises(BillingError):
        manager.record_payment(invoice.id, external=True)


def test_refund_payment():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    payment = manager.record_payment(invoice.id, external=True)
    refunded = manager.refund_payment(payment.id)
    assert refunded.status == PaymentStatus.REFUNDED
    with pytest.raises(BillingError):
        manager.refund_payment("nope")


def test_sync_quota_plan_and_free_fallback():
    manager = make_manager()
    quota = QuotaManager()
    manager.quota_sync.register(GatewayQuotaTarget(quota))
    sub = manager.create_subscription("t1", "professional", trial_days=0)
    assert quota.limit_for("t1", "tokens") == 10000000
    manager.cancel_subscription(sub.id, at_period_end=False)
    results = manager.sync_quota(sub.id)
    assert quota.limit_for("t1", "tokens") == 100000
    assert results["gateway"] == "ok"


def test_sync_quota_paused_uses_free_plan():
    manager = make_manager()
    quota = QuotaManager()
    manager.quota_sync.register(GatewayQuotaTarget(quota))
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.pause_subscription(sub.id)
    manager.sync_quota(sub.id)
    assert quota.limit_for("t1", "tokens") == 100000


def test_sync_quota_with_rate_limiter():
    manager = make_manager()
    limiter = RateLimiter()
    manager.quota_sync.register(RateLimiterQuotaTarget(limiter, window_seconds=3600))
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.sync_quota(sub.id)
    assert limiter.limiter_for("plan:t1").limit == 50000


def test_manager_webhook_payment_succeeded():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    result = manager.handle_webhook({"type": "payment.succeeded", "id": "evt1", "invoice_id": invoice.id})
    assert result["processed"] is True
    assert invoice.status == InvoiceStatus.PAID
    duplicate = manager.handle_webhook({"type": "payment.succeeded", "id": "evt1", "invoice_id": invoice.id})
    assert duplicate["processed"] is False


def test_manager_webhook_payment_failed_and_deleted_and_resumed():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.handle_webhook({"type": "invoice.payment_failed", "id": "e1", "subscription_id": sub.id})
    assert sub.status == SubscriptionStatus.PAST_DUE
    manager.handle_webhook({"type": "subscription.deleted", "id": "e2", "subscription_id": sub.id})
    assert sub.status == SubscriptionStatus.CANCELLED
    manager.handle_webhook({"type": "subscription.resumed", "id": "e3", "subscription_id": sub.id})
    assert sub.status == SubscriptionStatus.ACTIVE
    manager.handle_webhook({"type": "subscription.updated", "id": "e4", "subscription_id": sub.id, "plan_id": "professional"})
    assert sub.plan_id == "professional"
    result = manager.handle_webhook({"type": "subscription.deleted", "id": "e5", "subscription_id": "ghost"})
    assert "error" in result


def test_manager_webhook_signature_required():
    manager = make_manager()
    manager.register_provider(StripeProvider(secret="sec"))
    with pytest.raises(WebhookVerificationError):
        manager.handle_webhook({"type": "payment.succeeded", "_raw": "x"}, signature="bad", provider="stripe")


def test_create_coupon_via_manager():
    manager = make_manager()
    coupon = manager.create_coupon("SPRING", "percent", value=15.0, max_redemptions=5)
    assert coupon.code == "SPRING"
    assert manager.coupons.get("spring").value == 15.0
    trial = manager.create_coupon("TRIAL+", CouponType.TRIAL_EXTENSION, value=7.0)
    assert trial.type == CouponType.TRIAL_EXTENSION


def test_manager_dependency_injection():
    repos = BillingRepositories()
    logger = BillingLogger(make_config(log_events=True))
    metrics = BillingMetricsTracker(make_config(), logger=logger)
    manager = create_billing_manager(
        config=make_config(),
        repositories=repos,
        logger=logger,
        metrics=metrics,
        catalog=PlanCatalog(),
        pricing=PricingEngine(PlanCatalog()),
    )
    assert manager.repositories is repos
    assert manager.logger is logger
    assert manager.metrics is metrics
    assert manager.config.default_free_plan == "free"
    assert manager.event_bus is not None
    assert manager.webhooks is not None
    assert manager.audit is not None
    assert manager.coupons is not None
    assert manager.invoices is not None
    assert manager.quota_sync is not None


def test_custom_plan_flow():
    manager = make_manager()
    manager.catalog.register(Plan(id="mega", name="Mega", tier=PlanTier.CUSTOM, price_monthly=499.0, price_annual=4990.0))
    sub = manager.create_subscription("t1", "mega", trial_days=0)
    assert sub.price == 499.0
    invoice = manager.generate_invoice(sub.id)
    assert invoice.subtotal == 499.0


def test_annual_subscription_periods():
    manager = make_manager()
    sub = manager.create_subscription("t1", "team", interval="annual", trial_days=0)
    assert sub.price == 2990.0
    assert sub.current_period_end - sub.current_period_start == pytest.approx(366 * DAY)


def test_subscription_not_found():
    manager = make_manager()
    with pytest.raises(SubscriptionNotFoundError):
        manager.get_subscription("nope")
    with pytest.raises(SubscriptionNotFoundError):
        manager.cancel_subscription("nope")


def test_sync_quota_missing_subscription():
    manager = make_manager()
    with pytest.raises(SubscriptionNotFoundError):
        manager.sync_quota("nope")


def test_record_payment_recovers_past_due():
    manager = make_manager()
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    manager.mark_past_due(sub.id)
    invoice = manager.generate_invoice(sub.id)
    payment = manager.record_payment(invoice.id, external=True)
    assert payment.status == PaymentStatus.COMPLETED
    assert sub.status == SubscriptionStatus.ACTIVE


def test_metrics_snapshots_property():
    metrics = BillingMetricsTracker(make_config())
    metrics.record_subscription("t1", "starter", "active", 29.0)
    assert metrics.snapshots[0]["plan_id"] == "starter"


def test_logger_json_failure_fallback():
    class BadStr:
        def __str__(self):
            raise RuntimeError("boom")

    logger = BillingLogger(make_config(log_events=True))
    logger.log_event("x", weird=BadStr())
    assert logger.events[0]["event"] == "billing_x"


def test_pricing_strategy_names():
    assert FlatPricingStrategy().name() == "flat"
    assert TieredPricingStrategy().name() == "tiered"
    assert UsageBasedPricingStrategy().name() == "usage"
    plan = Plan(id="u", name="U", tier=PlanTier.PROFESSIONAL, price_monthly=50.0, price_annual=450.0,
                limits={"_internal": 1, "tiers": [], "tokens": 1000}, metadata={"tokens_rate": 0.02})
    assert UsageBasedPricingStrategy().compute(plan, usage={"tokens": 1500}) == 60.0


def test_provider_post_fallback_transport():
    from unittest.mock import patch

    provider = StripeProvider(secret="s")
    url = "https://example.test/charges"
    with patch("urllib.request.urlopen") as mock_open:
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b"ok"

        mock_open.return_value = FakeResponse()
        assert provider._post(url, {"a": 1}) == {"status": 200, "body": "ok"}

    import urllib.error

    def raise_http_error(request, timeout=None):
        raise urllib.error.HTTPError(url, 402, "declined", {}, None)

    with patch("urllib.request.urlopen", side_effect=raise_http_error):
        result = provider._post(url, {})
        assert result["status"] == 402

    def raise_network_error(request, timeout=None):
        raise OSError("connection refused")

    with patch("urllib.request.urlopen", side_effect=raise_network_error):
        assert provider._post(url, {}) == {"status": 0, "body": ""}


def test_stripe_refund_failure():
    provider = StripeProvider(secret="s", settings={"transport": transport(400)})
    payment = Payment(id="p1", tenant_id="t", invoice_id="i", amount=1, provider="stripe")
    with pytest.raises(PaymentError):
        provider.refund(payment)


def test_payment_repository_list_all():
    repo = InMemoryPaymentRepository()
    repo.create(Payment(id="p1", tenant_id="t1", invoice_id="i1", amount=1, provider="m"))
    assert len(repo.list()) == 1


def test_rate_limiter_target_error():
    class BrokenLimiter:
        def set_policy(self, **kwargs):
            raise RuntimeError("boom")

    target = RateLimiterQuotaTarget(BrokenLimiter())
    with pytest.raises(QuotaSyncError):
        target.apply("t1", {"api_requests": 100}, "starter")


def test_base_state_methods():
    state = SubscriptionState()
    assert state.allowed_targets() == set()
    state.on_enter(Subscription(id="s", tenant_id="t", plan_id="p"))


def test_manager_property_accessors():
    manager = make_manager()
    assert manager.usage is manager._usage
    assert manager.get_tenant_usage("t1") == {}
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    manager.record_payment(invoice.id, external=True)
    assert len(manager.list_payments("t1")) == 1
    assert len(manager.list_payments("ghost")) == 0
    assert manager.list_payments() == manager._repositories.payments.list()


def test_proration_disabled_returns_none():
    manager = make_manager(config_kwargs={"prorate_changes": False})
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    previous = manager.catalog.get("starter")
    target = manager.catalog.get("professional")
    assert manager._build_proration_invoice(sub, previous, target, 1) is None


def test_invoice_service_properties():
    config = make_config()
    invoices = InvoiceService(config)
    assert invoices.repository is invoices._repository
    assert invoices.coupons is invoices._coupons


def test_coupon_manager_repository_property():
    manager = CouponManager()
    assert manager.repository is manager._repository


def test_custom_provider_returns_failed_payment():
    class FailingProvider(PaymentProvider):
        name = "failing"
        configured = True

        def _charge(self, tenant_id, amount, reference, method):
            return Payment(
                id="py_fail", tenant_id=tenant_id, invoice_id=reference,
                amount=amount, provider=self.name, status=PaymentStatus.FAILED,
            )

        def _refund(self, payment):
            return payment

    manager = make_manager()
    manager.register_provider(FailingProvider())
    sub = manager.create_subscription("t1", "starter", trial_days=0)
    invoice = manager.generate_invoice(sub.id)
    payment = manager.record_payment(invoice.id, provider="failing")
    assert payment.status == PaymentStatus.FAILED
    assert sub.status == SubscriptionStatus.PAST_DUE
