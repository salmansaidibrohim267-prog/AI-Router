from __future__ import annotations

import time
import uuid
from typing import Any

from .config import BillingConfig
from .coupons import CouponManager
from .exceptions import (
    BillingError,
    InvoiceAlreadyPaidError,
    PaymentFailedError,
    SubscriptionAlreadyExistsError,
)
from .invoicing import InvoiceService
from .lifecycle import SubscriptionLifecycle
from .logging import BillingLogger
from .metrics import BillingMetricsTracker
from .models import (
    BillingAuditLogger,
    BillingEventType,
    CouponType,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from .plans import PlanCatalog, PricingEngine
from .providers import PaymentProvider, PaymentProviderFactory
from .repository import BillingRepositories
from .sync import BillingEventBus, QuotaSyncCoordinator
from .taxation import TaxCalculator
from .usage import UsageMeter
from .webhooks import BillingWebhookHandler

_SECONDS_PER_DAY = 86400


class BillingManager:
    """Orchestrates subscriptions, billing, payments and quota synchronization."""

    def __init__(
        self,
        config: BillingConfig | None = None,
        repositories: BillingRepositories | None = None,
        catalog: PlanCatalog | None = None,
        pricing: PricingEngine | None = None,
        usage: UsageMeter | None = None,
        coupons: CouponManager | None = None,
        tax: TaxCalculator | None = None,
        invoices: InvoiceService | None = None,
        lifecycle: SubscriptionLifecycle | None = None,
        quota_sync: QuotaSyncCoordinator | None = None,
        event_bus: BillingEventBus | None = None,
        webhooks: BillingWebhookHandler | None = None,
        logger: BillingLogger | None = None,
        metrics: BillingMetricsTracker | None = None,
        audit: BillingAuditLogger | None = None,
        providers: dict[str, PaymentProvider] | None = None,
    ) -> None:
        self._config = config or BillingConfig()
        self._repositories = repositories or BillingRepositories()
        self._catalog = catalog or PlanCatalog()
        self._pricing = pricing or PricingEngine(self._catalog)
        self._usage = usage or UsageMeter(self._repositories.usage)
        self._coupons = coupons or CouponManager(self._repositories.coupons)
        self._tax = tax or TaxCalculator(self._config)
        self._invoices = invoices or InvoiceService(
            self._config,
            repository=self._repositories.invoices,
            coupons=self._coupons,
            tax=self._tax,
        )
        self._lifecycle = lifecycle or SubscriptionLifecycle()
        self._quota_sync = quota_sync or QuotaSyncCoordinator(logger or BillingLogger(self._config))
        self._event_bus = event_bus or BillingEventBus()
        self._logger = logger or BillingLogger(self._config)
        self._metrics = metrics or BillingMetricsTracker(self._config, self._logger)
        self._audit = audit or BillingAuditLogger(self._config, self._logger)
        self._providers = providers if providers is not None else {}
        self._webhooks = webhooks or BillingWebhookHandler(logger=self._logger)

    # ------------------------------------------------------------------ props

    @property
    def config(self) -> BillingConfig:
        return self._config

    @property
    def repositories(self) -> BillingRepositories:
        return self._repositories

    @property
    def catalog(self) -> PlanCatalog:
        return self._catalog

    @property
    def usage(self) -> UsageMeter:
        return self._usage

    @property
    def coupons(self) -> CouponManager:
        return self._coupons

    @property
    def invoices(self) -> InvoiceService:
        return self._invoices

    @property
    def quota_sync(self) -> QuotaSyncCoordinator:
        return self._quota_sync

    @property
    def event_bus(self) -> BillingEventBus:
        return self._event_bus

    @property
    def metrics(self) -> BillingMetricsTracker:
        return self._metrics

    @property
    def logger(self) -> BillingLogger:
        return self._logger

    @property
    def audit(self) -> BillingAuditLogger:
        return self._audit

    @property
    def webhooks(self) -> BillingWebhookHandler:
        return self._webhooks

    # ------------------------------------------------------------- providers

    def register_provider(self, provider: PaymentProvider) -> None:
        self._providers[provider.name] = provider

    def _provider_for(self, name: str) -> PaymentProvider:
        provider = self._providers.get(name)
        if provider is not None:
            return provider
        settings = self._config.provider_settings.get(name, {})
        provider = PaymentProviderFactory.create(
            name,
            secret=settings.get("secret", ""),
            settings=settings.get("settings") or {},
        )
        self._providers[name] = provider
        return provider

    # ---------------------------------------------------------- subscriptions

    def create_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        interval: str = "",
        seats: int = 1,
        coupon_code: str = "",
        provider: str = "",
        auto_renew: bool | None = None,
        trial_days: int | None = None,
    ) -> Subscription:
        plan = self._catalog.get(plan_id)
        interval = interval or self._config.default_interval
        provider = provider or self._config.default_provider
        existing = self._repositories.subscriptions.by_tenant(tenant_id)
        if existing is not None and existing.status not in (SubscriptionStatus.CANCELLED,):
            raise SubscriptionAlreadyExistsError(tenant_id)
        price = self._pricing.price(plan_id, seats=seats, interval=interval)["amount"]
        now = time.time()
        period_end = now + self._period_seconds(interval)
        trial_days = trial_days if trial_days is not None else self._config.trial_days
        supports_trial = plan.supports_trial and trial_days > 0
        if coupon_code:
            self._coupons.redeem(coupon_code, plan_id=plan_id)
        subscription = Subscription(
            id=f"sub_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            plan_id=plan_id,
            status=SubscriptionStatus.TRIAL if supports_trial else SubscriptionStatus.ACTIVE,
            interval=interval,
            seats=max(1, seats),
            price=price,
            started_at=now,
            current_period_start=now,
            current_period_end=period_end,
            trial_end=now + trial_days * _SECONDS_PER_DAY if supports_trial else 0.0,
            auto_renew=self._config.auto_renew if auto_renew is None else auto_renew,
            provider=provider,
            coupon_code=coupon_code.upper() if coupon_code else "",
        )
        if existing is not None:
            subscription.id = existing.id
            subscription.created_at = existing.created_at
        self._repositories.subscriptions.create(subscription)
        self._audit.record(
            "subscription.created",
            tenant_id=tenant_id,
            subscription_id=subscription.id,
            plan_id=plan_id,
            interval=interval,
            seats=seats,
        )
        self._metrics.record_subscription(
            tenant_id,
            plan_id,
            subscription.status.value,
            plan.price_for(interval),
            seats=seats,
            interval=interval,
        )
        self._event_bus.publish(
            BillingEventType.SUBSCRIPTION_CREATED.value,
            subscription,
            {"plan_id": plan_id},
        )
        self.sync_quota(subscription.id)
        self._logger.log_event(
            "subscription.created",
            tenant_id=tenant_id,
            subscription_id=subscription.id,
            plan_id=plan_id,
            status=subscription.status.value,
        )
        return subscription

    def change_plan(
        self,
        subscription_id: str,
        plan_id: str,
        seats: int | None = None,
        prorate: bool | None = None,
    ) -> Subscription:
        subscription = self._get_subscription(subscription_id)
        plan = self._catalog.get(plan_id)
        if subscription.status == SubscriptionStatus.CANCELLED:
            raise BillingError("Cannot change plan of a cancelled subscription", subscription_id=subscription_id)
        previous = self._catalog.get(subscription.plan_id)
        if prorate if prorate is not None else self._config.prorate_changes:
            self._build_proration_invoice(subscription, previous, plan, seats or subscription.seats)
        subscription.plan_id = plan_id
        subscription.seats = seats or subscription.seats
        subscription.price = self._pricing.price(plan_id, seats=subscription.seats, interval=subscription.interval)[
            "amount"
        ]  # noqa: E501
        subscription.updated_at = time.time()
        self._repositories.subscriptions.update(subscription)
        self._metrics.record_subscription(
            subscription.tenant_id,
            plan_id,
            subscription.status.value,
            plan.price_for(subscription.interval),
            seats=subscription.seats,
            interval=subscription.interval,
        )
        self._event_bus.publish(
            BillingEventType.SUBSCRIPTION_UPDATED.value,
            subscription,
            {"plan_id": plan_id, "previous_plan_id": previous.id},
        )
        self._audit.record(
            "subscription.plan_changed",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription_id,
            previous_plan=previous.id,
            plan_id=plan_id,
        )
        self.sync_quota(subscription_id)
        return subscription

    def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> Subscription:
        subscription = self._get_subscription(subscription_id)
        if subscription.status == SubscriptionStatus.CANCELLED:
            return subscription
        now = time.time()
        if at_period_end and subscription.status == SubscriptionStatus.ACTIVE:
            subscription.cancel_at_period_end = True
            self._repositories.subscriptions.update(subscription)
            return subscription
        self._lifecycle.transition(subscription, SubscriptionStatus.CANCELLED)
        subscription.cancelled_at = now
        subscription.cancel_at_period_end = False
        self._repositories.subscriptions.update(subscription)
        free_plan = self._catalog.get(self._config.default_free_plan)
        self._quota_sync.sync(subscription.tenant_id, free_plan, subscription)
        self._metrics.record_subscription(
            subscription.tenant_id,
            subscription.plan_id,
            SubscriptionStatus.CANCELLED.value,
            self._catalog.get(subscription.plan_id).price_for(subscription.interval),
            seats=subscription.seats,
            interval=subscription.interval,
        )
        self._event_bus.publish(
            BillingEventType.SUBSCRIPTION_CANCELLED.value,
            subscription,
            {"at_period_end": at_period_end},
        )
        self._audit.record(
            "subscription.cancelled",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription_id,
            at_period_end=at_period_end,
        )
        self._logger.log_event("subscription.cancelled", subscription_id=subscription_id, at_period_end=at_period_end)
        return subscription

    def resume_subscription(self, subscription_id: str, plan_id: str = "") -> Subscription:
        subscription = self._get_subscription(subscription_id)
        if subscription.status == SubscriptionStatus.CANCELLED:
            self._lifecycle.transition(subscription, SubscriptionStatus.ACTIVE)
            subscription.cancelled_at = 0.0
        elif subscription.status == SubscriptionStatus.PAUSED:
            self._lifecycle.transition(subscription, SubscriptionStatus.ACTIVE)
        else:
            raise BillingError(
                f"Cannot resume subscription in {subscription.status.value!r} state",
                subscription_id=subscription_id,
            )
        if plan_id:
            plan = self._catalog.get(plan_id)
            subscription.plan_id = plan_id
            subscription.price = self._pricing.price(plan_id, seats=subscription.seats, interval=subscription.interval)[
                "amount"
            ]  # noqa: E501
        else:
            plan = self._catalog.get(subscription.plan_id)
        now = time.time()
        subscription.current_period_start = now
        subscription.current_period_end = now + self._period_seconds(subscription.interval)
        subscription.updated_at = now
        self._repositories.subscriptions.update(subscription)
        self._metrics.record_subscription(
            subscription.tenant_id,
            subscription.plan_id,
            SubscriptionStatus.ACTIVE.value,
            plan.price_for(subscription.interval),
            seats=subscription.seats,
            interval=subscription.interval,
        )
        self._event_bus.publish(BillingEventType.SUBSCRIPTION_RESUMED.value, subscription, {})
        self._audit.record(
            "subscription.resumed",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription_id,
            plan_id=subscription.plan_id,
        )
        self.sync_quota(subscription_id)
        return subscription

    def pause_subscription(self, subscription_id: str) -> Subscription:
        subscription = self._get_subscription(subscription_id)
        self._lifecycle.transition(subscription, SubscriptionStatus.PAUSED)
        subscription.updated_at = time.time()
        self._metrics.record_subscription(
            subscription.tenant_id,
            subscription.plan_id,
            SubscriptionStatus.PAUSED.value,
            self._catalog.get(subscription.plan_id).price_for(subscription.interval),
            seats=subscription.seats,
            interval=subscription.interval,
        )
        self._repositories.subscriptions.update(subscription)
        self._event_bus.publish(BillingEventType.SUBSCRIPTION_PAUSED.value, subscription, {})
        self._audit.record(
            "subscription.paused",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription_id,
        )
        return subscription

    def convert_trial(self, subscription_id: str) -> Subscription:
        subscription = self._get_subscription(subscription_id)
        if subscription.status != SubscriptionStatus.TRIAL:
            return subscription
        self._lifecycle.transition(subscription, SubscriptionStatus.ACTIVE)
        subscription.trial_end = 0.0
        subscription.updated_at = time.time()
        self._repositories.subscriptions.update(subscription)
        self._audit.record(
            "subscription.trial_converted",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription_id,
        )
        self.sync_quota(subscription_id)
        return subscription

    def mark_past_due(self, subscription_id: str, reason: str = "payment_failed") -> Subscription:
        subscription = self._get_subscription(subscription_id)
        self._lifecycle.transition(subscription, SubscriptionStatus.PAST_DUE)
        subscription.grace_end = time.time() + self._config.grace_days * _SECONDS_PER_DAY
        subscription.updated_at = time.time()
        self._repositories.subscriptions.update(subscription)
        self._event_bus.publish(
            BillingEventType.INVOICE_OVERDUE.value,
            subscription,
            {"reason": reason},
        )
        self._audit.record(
            "subscription.past_due",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription_id,
            reason=reason,
        )
        return subscription

    def _enforce_grace(self, subscription: Subscription) -> None:
        if (
            subscription.status == SubscriptionStatus.PAST_DUE
            and subscription.grace_end
            and time.time() > subscription.grace_end
        ):  # noqa: E501
            self._lifecycle.transition(subscription, SubscriptionStatus.CANCELLED)
            subscription.updated_at = time.time()
            self._repositories.subscriptions.update(subscription)
            self._logger.log_event("subscription.cancelled.grace", subscription_id=subscription.id)

    def _get_subscription(self, subscription_id: str) -> Subscription:
        subscription = self._repositories.subscriptions.get(subscription_id)
        self._enforce_grace(subscription)
        return subscription

    # ----------------------------------------------------------------- usage

    def record_usage(
        self,
        tenant_id: str,
        category: str,
        amount: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._usage.record(tenant_id, category, amount, metadata=metadata)

    def get_usage(self, subscription_id: str) -> dict[str, Any]:
        subscription = self._get_subscription(subscription_id)
        plan = self._catalog.get(subscription.plan_id)
        since = subscription.current_period_start
        meters = self._usage.snapshot(subscription.tenant_id, limits=plan.limits, since=since)
        usage = self._usage.usage_by_category(subscription.tenant_id, since=since)
        return {
            "subscription_id": subscription_id,
            "tenant_id": subscription.tenant_id,
            "plan_id": plan.id,
            "period_start": subscription.current_period_start,
            "period_end": subscription.current_period_end,
            "usage": usage,
            "meters": [meter.__dict__ for meter in meters],
        }

    def get_tenant_usage(self, tenant_id: str) -> dict[str, int]:
        return self._usage.usage_by_category(tenant_id)

    def get_subscription(self, subscription_id: str) -> Subscription:
        return self._get_subscription(subscription_id)

    def get_subscription_by_tenant(self, tenant_id: str) -> Subscription | None:
        subscription = self._repositories.subscriptions.by_tenant(tenant_id)
        if subscription is not None:
            self._enforce_grace(subscription)
        return subscription

    def list_subscriptions(self) -> list[Subscription]:
        return self._repositories.subscriptions.list()

    # ---------------------------------------------------------------- invoices

    def generate_invoice(
        self,
        subscription_id: str,
        coupon_code: str = "",
        country_code: str = "",
        tax_rate: float | None = None,
    ) -> Invoice:
        subscription = self._get_subscription(subscription_id)
        plan = self._catalog.get(subscription.plan_id)
        invoice = self._invoices.create_draft(
            subscription.tenant_id,
            subscription,
            plan,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
        )
        usage = self._usage.usage_by_category(
            subscription.tenant_id,
            since=subscription.current_period_start,
        )
        invoice = self._invoices.build(
            invoice,
            plan,
            subscription,
            usage=usage,
            coupon_code=coupon_code or subscription.coupon_code,
            country_code=country_code,
            tax_rate=tax_rate,
        )
        self._event_bus.publish(
            BillingEventType.INVOICE_CREATED.value,
            subscription,
            {"invoice_id": invoice.id, "total": invoice.total},
        )
        self._audit.record(
            "invoice.generated",
            tenant_id=subscription.tenant_id,
            subscription_id=subscription_id,
            invoice_id=invoice.id,
            total=invoice.total,
        )
        self._logger.log_event(
            "invoice.generated",
            invoice_id=invoice.id,
            subscription_id=subscription_id,
            total=invoice.total,
        )
        return invoice

    def _build_proration_invoice(self, subscription: Subscription, previous: Plan, target: Plan, seats: int) -> Invoice:
        if not self._config.prorate_changes:
            return None
        remaining = max(
            0.0, (subscription.current_period_end - time.time()) / self._period_seconds(subscription.interval)
        )  # noqa: E501
        delta = (
            (target.price_for(subscription.interval) - previous.price_for(subscription.interval)) * seats * remaining
        )  # noqa: E501
        invoice = self._invoices.create_draft(
            subscription.tenant_id,
            subscription,
            previous,
            period_start=time.time(),
            period_end=subscription.current_period_end,
        )
        invoice.lines = [
            InvoiceLine(
                description=f"Plan change proration ({previous.id} → {target.id})",
                quantity=1,
                unit_amount=round(delta, 4),
            )
        ]
        invoice.subtotal = round(delta, 4)
        invoice.discount = 0.0
        invoice.tax = round(delta * self._tax.rate_for(), 4)
        invoice.total = round(delta + invoice.tax, 4)
        invoice.status = InvoiceStatus.PENDING
        self._repositories.invoices.update(invoice)
        return invoice

    def get_invoice(self, invoice_id: str) -> Invoice:
        return self._repositories.invoices.get(invoice_id)

    def list_invoices(self, tenant_id: str = "") -> list[Invoice]:
        return self._repositories.invoices.list(tenant_id)

    def void_invoice(self, invoice_id: str) -> Invoice:
        invoice = self._invoices.void(invoice_id)
        self._audit.record("invoice.voided", invoice_id=invoice_id)
        return invoice

    # ---------------------------------------------------------------- payments

    def record_payment(
        self,
        invoice_id: str,
        provider: str = "",
        method: str = "card",
        amount: float | None = None,
        external: bool = False,
    ) -> Payment:
        invoice = self._repositories.invoices.get(invoice_id)
        if invoice.status == InvoiceStatus.PAID:
            raise InvoiceAlreadyPaidError(invoice_id)
        if invoice.status == InvoiceStatus.VOID:
            raise BillingError("Cannot record a payment on a void invoice", invoice_id=invoice_id)
        subscription = self._repositories.subscriptions.get(invoice.subscription_id)
        provider_name = provider or subscription.provider or self._config.default_provider
        payment_provider = self._provider_for(provider_name)
        amount = amount if amount is not None else invoice.total
        if external:
            payment = Payment(
                id=f"py_{uuid.uuid4().hex[:12]}",
                tenant_id=invoice.tenant_id,
                invoice_id=invoice_id,
                amount=amount,
                provider=provider_name,
                method=method,
                status=PaymentStatus.COMPLETED,
                reference=f"ext_{uuid.uuid4().hex[:12]}",
            )
        else:
            try:
                payment = payment_provider.charge(invoice.tenant_id, amount, invoice_id, method=method)
            except PaymentFailedError:
                payment = Payment(
                    id=f"py_{uuid.uuid4().hex[:12]}",
                    tenant_id=invoice.tenant_id,
                    invoice_id=invoice_id,
                    amount=amount,
                    provider=provider_name,
                    method=method,
                    status=PaymentStatus.FAILED,
                )
                self._repositories.payments.create(payment)
                if subscription.status == SubscriptionStatus.ACTIVE:
                    self.mark_past_due(subscription.id, reason="payment_failed")
                raise
        self._repositories.payments.create(payment)
        self._audit.record(
            "payment.recorded",
            tenant_id=invoice.tenant_id,
            invoice_id=invoice_id,
            payment_id=payment.id,
            amount=amount,
            provider=provider_name,
            status=payment.status.value,
        )
        self._logger.log_event(
            "payment.recorded",
            payment_id=payment.id,
            invoice_id=invoice_id,
            amount=amount,
            status=payment.status.value,
        )
        if payment.status == PaymentStatus.COMPLETED:
            self._invoices.mark_paid(invoice_id)
            if subscription.status in (SubscriptionStatus.TRIAL, SubscriptionStatus.PAST_DUE):
                if subscription.status == SubscriptionStatus.TRIAL:
                    self.convert_trial(subscription.id)
                if subscription.status == SubscriptionStatus.PAST_DUE:
                    self._lifecycle.transition(subscription, SubscriptionStatus.ACTIVE)
                    subscription.updated_at = time.time()
                    self._repositories.subscriptions.update(subscription)
            self._event_bus.publish(
                BillingEventType.INVOICE_PAID.value,
                subscription,
                {"invoice_id": invoice_id, "payment_id": payment.id},
            )
            self._metrics.record_subscription(
                invoice.tenant_id,
                subscription.plan_id,
                SubscriptionStatus.ACTIVE.value,
                self._catalog.get(subscription.plan_id).price_for(subscription.interval),
                seats=subscription.seats,
                interval=subscription.interval,
            )
        elif payment.status == PaymentStatus.FAILED:
            if subscription.status == SubscriptionStatus.ACTIVE:
                self.mark_past_due(subscription.id, reason="payment_failed")
            self._event_bus.publish(
                BillingEventType.PAYMENT_RECORDED.value,
                subscription,
                {"payment_id": payment.id, "status": payment.status.value},
            )
        else:
            self._event_bus.publish(
                BillingEventType.PAYMENT_RECORDED.value,
                subscription,
                {"payment_id": payment.id, "status": payment.status.value},
            )
        return payment

    def list_payments(self, tenant_id: str = "") -> list[Payment]:
        return self._repositories.payments.list(tenant_id)

    def refund_payment(self, payment_id: str) -> Payment:
        payment = self._repositories.payments.get(payment_id)
        provider = self._provider_for(payment.provider)
        refunded = provider.refund(payment)
        self._repositories.payments.update(refunded)
        self._audit.record(
            "payment.refunded",
            tenant_id=payment.tenant_id,
            payment_id=payment_id,
        )
        return refunded

    # ------------------------------------------------------------------ quota

    def sync_quota(self, subscription_id: str) -> dict[str, Any]:
        subscription = self._get_subscription(subscription_id)
        if subscription.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.PAUSED):
            plan = self._catalog.get(self._config.default_free_plan)
        else:
            plan = self._catalog.get(subscription.plan_id)
        results = self._quota_sync.sync(subscription.tenant_id, plan, subscription)
        self._event_bus.publish(
            BillingEventType.QUOTA_SYNCED.value,
            subscription,
            {"plan_id": plan.id, "results": results},
        )
        return results

    # ---------------------------------------------------------------- webhooks

    def handle_webhook(self, payload: dict[str, Any], signature: str = "", provider: str = "") -> dict[str, Any]:
        webhook_provider = None
        if provider:
            webhook_provider = self._provider_for(provider)
        self._webhooks._provider = webhook_provider
        result = self._webhooks.handle_payload(payload, signature=signature)
        if not result.get("processed"):
            return result
        event = result.get("event", "")
        try:
            if event == "payment.succeeded":
                invoice_id = result.get("invoice_id", "")
                if invoice_id:
                    self.record_payment(invoice_id, provider=provider or "", external=True)
            elif event in ("invoice.payment_failed", "payment.failed"):
                subscription_id = result.get("subscription_id", "")
                if subscription_id:
                    self.mark_past_due(subscription_id, reason="webhook_payment_failed")
            elif event == "subscription.deleted":
                subscription_id = result.get("subscription_id", "")
                if subscription_id:
                    self.cancel_subscription(subscription_id, at_period_end=False)
            elif event == "subscription.resumed":
                subscription_id = result.get("subscription_id", "")
                if subscription_id:
                    self.resume_subscription(subscription_id)
            elif event == "subscription.updated":
                subscription_id = result.get("subscription_id", "")
                plan_id = result.get("plan_id", "")
                if subscription_id and plan_id:
                    self.change_plan(subscription_id, plan_id)
        except BillingError as exc:
            result["error"] = exc.message
        return result

    # ------------------------------------------------------------------ admin

    def create_coupon(
        self,
        code: str,
        coupon_type: str | CouponType = "percent",
        value: float = 0.0,
        max_redemptions: int = 0,
        expires_at: float = 0.0,
        applies_to: list[str] | None = None,
    ) -> Any:
        coupon = self._coupons.create(
            code,
            coupon_type,
            value=value,
            max_redemptions=max_redemptions,
            expires_at=expires_at,
            applies_to=applies_to,
        )
        self._audit.record("coupon.created", coupon_code=coupon.code, value=coupon.value)
        return coupon

    def metrics_summary(self) -> dict[str, Any]:
        return self._metrics.summary()

    @staticmethod
    def _period_seconds(interval: str) -> float:
        if interval == "annual":
            return 366 * _SECONDS_PER_DAY
        return 30 * _SECONDS_PER_DAY


def create_billing_manager(
    config: BillingConfig | None = None,
    repositories: BillingRepositories | None = None,
    catalog: PlanCatalog | None = None,
    pricing: PricingEngine | None = None,
    usage: UsageMeter | None = None,
    coupons: CouponManager | None = None,
    tax: TaxCalculator | None = None,
    invoices: InvoiceService | None = None,
    lifecycle: SubscriptionLifecycle | None = None,
    quota_sync: QuotaSyncCoordinator | None = None,
    event_bus: BillingEventBus | None = None,
    webhooks: BillingWebhookHandler | None = None,
    logger: BillingLogger | None = None,
    metrics: BillingMetricsTracker | None = None,
    audit: BillingAuditLogger | None = None,
    providers: dict[str, PaymentProvider] | None = None,
) -> BillingManager:
    return BillingManager(
        config=config,
        repositories=repositories,
        catalog=catalog,
        pricing=pricing,
        usage=usage,
        coupons=coupons,
        tax=tax,
        invoices=invoices,
        lifecycle=lifecycle,
        quota_sync=quota_sync,
        event_bus=event_bus,
        webhooks=webhooks,
        logger=logger,
        metrics=metrics,
        audit=audit,
        providers=providers,
    )
