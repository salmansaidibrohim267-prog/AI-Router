from __future__ import annotations

import time
from typing import Any, Callable

from .config import BillingConfig
from .coupons import CouponManager
from .exceptions import InvoiceError
from .models import (
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    InvoiceSummary,
    Plan,
    Subscription,
    generate_id,
)
from .repository import InvoiceRepository
from .taxation import TaxCalculator


class InvoiceNumberStrategy:
    """Strategy: generates sequential invoice numbers."""

    def __init__(self, prefix: str = "AIR-", start: int = 1) -> None:
        self._prefix = prefix
        self._counter = start
        self._last: str = ""

    @property
    def last(self) -> str:
        return self._last

    def next(self) -> str:
        number = f"{self._prefix}{self._counter:04d}"
        self._counter += 1
        self._last = number
        return number

    def from_count(self, count: int) -> None:
        self._counter = max(self._counter, count + 1)


class InvoiceService:
    """Builds invoices: plan lines, usage overage lines, coupons, tax, totals."""

    def __init__(
        self,
        config: BillingConfig | None = None,
        repository: InvoiceRepository | None = None,
        coupons: CouponManager | None = None,
        tax: TaxCalculator | None = None,
        number_strategy: Callable[[], str] | None = None,
    ) -> None:
        from .repository import InMemoryInvoiceRepository

        self._config = config or BillingConfig()
        self._repository = repository or InMemoryInvoiceRepository()
        self._coupons = coupons or CouponManager()
        self._tax = tax or TaxCalculator(self._config)
        self._strategy = number_strategy or self._default_number

    @property
    def repository(self) -> InvoiceRepository:
        return self._repository

    @property
    def coupons(self) -> CouponManager:
        return self._coupons

    def _default_number(self) -> str:
        strategy = InvoiceNumberStrategy(self._config.invoice_prefix)
        strategy.from_count(self._repository.count())
        return strategy.next()

    def create_draft(
        self,
        tenant_id: str,
        subscription: Subscription,
        plan: Plan,
        period_start: float,
        period_end: float,
    ) -> Invoice:
        invoice = Invoice(
            id=generate_id("inv"),
            number=self._strategy(),
            tenant_id=tenant_id,
            subscription_id=subscription.id,
            currency=self._config.currency,
            status=InvoiceStatus.DRAFT,
            period_start=period_start,
            period_end=period_end,
            due_at=period_end + self._config.invoice_due_days * 86400,
        )
        return self._repository.create(invoice)

    def build(
        self,
        invoice: Invoice,
        plan: Plan,
        subscription: Subscription,
        usage: dict[str, int] | None = None,
        coupon_code: str = "",
        country_code: str = "",
        tax_rate: float | None = None,
    ) -> Invoice:
        usage = usage or {}
        plan_price = plan.price_for(subscription.interval) * subscription.seats
        invoice.lines = [
            InvoiceLine(
                description=f"{plan.name} subscription ({subscription.interval})",
                quantity=subscription.seats,
                unit_amount=round(plan.price_for(subscription.interval), 4),
            )
        ]
        for category, used in sorted(usage.items()):
            if used > 0:
                invoice.lines.append(
                    InvoiceLine(
                        description=f"{category} usage",
                        quantity=used,
                        unit_amount=0.0,
                        category=category,
                    )
                )
        subtotal = plan_price + sum(line.amount for line in invoice.lines[1:])
        invoice.subtotal = round(subtotal, 4)
        invoice.discount = 0.0
        invoice.coupon_code = ""
        if coupon_code:
            discount, _description = self._coupons.discount(coupon_code, subtotal, plan_id=plan.id)
            invoice.discount = round(discount, 4)
            invoice.coupon_code = coupon_code.upper()
        taxable = subtotal - invoice.discount
        if tax_rate is not None:
            invoice.tax = round(taxable * tax_rate, 4)
        else:
            invoice.tax = self._tax.tax(taxable, country_code)
        invoice.total = round(taxable + invoice.tax, 4)
        invoice.status = InvoiceStatus.PENDING
        return self._repository.update(invoice)

    def itemize(self, invoice: Invoice, lines: list[InvoiceLine]) -> Invoice:
        invoice.lines = lines
        invoice.subtotal = round(sum(line.amount for line in lines), 4)
        invoice.tax = self._tax.tax(invoice.subtotal)
        invoice.total = round(invoice.subtotal + invoice.tax, 4)
        return self._repository.update(invoice)

    def void(self, invoice_id: str) -> Invoice:
        invoice = self._repository.get(invoice_id)
        if invoice.status == InvoiceStatus.PAID:
            raise InvoiceError("Cannot void a paid invoice", invoice_id=invoice_id)
        invoice.status = InvoiceStatus.VOID
        return self._repository.update(invoice)

    def mark_paid(self, invoice_id: str, paid_at: float | None = None) -> Invoice:
        invoice = self._repository.get(invoice_id)
        invoice.status = InvoiceStatus.PAID
        invoice.paid_at = paid_at or time.time()
        return self._repository.update(invoice)

    def summaries(self, tenant_id: str) -> list[InvoiceSummary]:
        return [
            InvoiceSummary(
                invoice_id=invoice.id,
                number=invoice.number,
                total=invoice.total,
                status=invoice.status.value,
                period_start=invoice.period_start,
                period_end=invoice.period_end,
            )
            for invoice in self._repository.list(tenant_id)
        ]
