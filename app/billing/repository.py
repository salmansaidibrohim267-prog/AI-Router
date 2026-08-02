from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any

from .exceptions import CouponNotFoundError, InvoiceNotFoundError, SubscriptionNotFoundError
from .models import Coupon, Invoice, Payment, Subscription, UsageRecord


class SubscriptionRepository(ABC):
    @abstractmethod
    def create(self, subscription: Subscription) -> Subscription:
        raise NotImplementedError

    @abstractmethod
    def get(self, subscription_id: str) -> Subscription:
        raise NotImplementedError

    @abstractmethod
    def update(self, subscription: Subscription) -> Subscription:
        raise NotImplementedError

    @abstractmethod
    def delete(self, subscription_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Subscription]:
        raise NotImplementedError

    @abstractmethod
    def by_tenant(self, tenant_id: str) -> Subscription | None:
        raise NotImplementedError


class InvoiceRepository(ABC):
    @abstractmethod
    def create(self, invoice: Invoice) -> Invoice:
        raise NotImplementedError

    @abstractmethod
    def get(self, invoice_id: str) -> Invoice:
        raise NotImplementedError

    @abstractmethod
    def update(self, invoice: Invoice) -> Invoice:
        raise NotImplementedError

    @abstractmethod
    def list(self, tenant_id: str = "") -> list[Invoice]:
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        raise NotImplementedError


class PaymentRepository(ABC):
    @abstractmethod
    def create(self, payment: Payment) -> Payment:
        raise NotImplementedError

    @abstractmethod
    def get(self, payment_id: str) -> Payment:
        raise NotImplementedError

    @abstractmethod
    def update(self, payment: Payment) -> Payment:
        raise NotImplementedError

    @abstractmethod
    def list(self, tenant_id: str = "") -> list[Payment]:
        raise NotImplementedError


class CouponRepository(ABC):
    @abstractmethod
    def create(self, coupon: Coupon) -> Coupon:
        raise NotImplementedError

    @abstractmethod
    def get(self, code: str) -> Coupon:
        raise NotImplementedError

    @abstractmethod
    def update(self, coupon: Coupon) -> Coupon:
        raise NotImplementedError

    @abstractmethod
    def delete(self, code: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[Coupon]:
        raise NotImplementedError


class UsageRepository(ABC):
    @abstractmethod
    def record(self, record: UsageRecord) -> UsageRecord:
        raise NotImplementedError

    @abstractmethod
    def usage(self, tenant_id: str, category: str, since: float = 0.0) -> int:
        raise NotImplementedError

    @abstractmethod
    def usage_by_category(self, tenant_id: str, since: float = 0.0) -> dict[str, int]:
        raise NotImplementedError

    @abstractmethod
    def reset(self, tenant_id: str, category: str = "") -> None:
        raise NotImplementedError


class InMemorySubscriptionRepository(SubscriptionRepository):
    def __init__(self) -> None:
        self._subscriptions: dict[str, Subscription] = {}
        self._lock = threading.Lock()

    def create(self, subscription: Subscription) -> Subscription:
        with self._lock:
            self._subscriptions[subscription.id] = subscription
        return subscription

    def get(self, subscription_id: str) -> Subscription:
        with self._lock:
            subscription = self._subscriptions.get(subscription_id)
        if subscription is None:
            raise SubscriptionNotFoundError(subscription_id)
        return subscription

    def update(self, subscription: Subscription) -> Subscription:
        with self._lock:
            if subscription.id not in self._subscriptions:
                raise SubscriptionNotFoundError(subscription.id)
            self._subscriptions[subscription.id] = subscription
        return subscription

    def delete(self, subscription_id: str) -> bool:
        with self._lock:
            if subscription_id not in self._subscriptions:
                return False
            del self._subscriptions[subscription_id]
        return True

    def list(self) -> list[Subscription]:
        with self._lock:
            return list(self._subscriptions.values())

    def by_tenant(self, tenant_id: str) -> Subscription | None:
        for subscription in self.list():
            if subscription.tenant_id == tenant_id:
                return subscription
        return None


class InMemoryInvoiceRepository(InvoiceRepository):
    def __init__(self) -> None:
        self._invoices: dict[str, Invoice] = {}
        self._lock = threading.Lock()

    def create(self, invoice: Invoice) -> Invoice:
        with self._lock:
            self._invoices[invoice.id] = invoice
        return invoice

    def get(self, invoice_id: str) -> Invoice:
        with self._lock:
            invoice = self._invoices.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        return invoice

    def update(self, invoice: Invoice) -> Invoice:
        with self._lock:
            if invoice.id not in self._invoices:
                raise InvoiceNotFoundError(invoice.id)
            self._invoices[invoice.id] = invoice
        return invoice

    def list(self, tenant_id: str = "") -> list[Invoice]:
        with self._lock:
            invoices = list(self._invoices.values())
        if not tenant_id:
            return invoices
        return [invoice for invoice in invoices if invoice.tenant_id == tenant_id]

    def count(self) -> int:
        with self._lock:
            return len(self._invoices)


class InMemoryPaymentRepository(PaymentRepository):
    def __init__(self) -> None:
        self._payments: dict[str, Payment] = {}
        self._lock = threading.Lock()

    def create(self, payment: Payment) -> Payment:
        with self._lock:
            self._payments[payment.id] = payment
        return payment

    def get(self, payment_id: str) -> Payment:
        with self._lock:
            payment = self._payments.get(payment_id)
        if payment is None:
            from .exceptions import BillingError

            raise BillingError(f"Payment {payment_id!r} does not exist", payment_id=payment_id)
        return payment

    def update(self, payment: Payment) -> Payment:
        with self._lock:
            if payment.id not in self._payments:
                from .exceptions import BillingError

                raise BillingError(f"Payment {payment.id!r} does not exist", payment_id=payment.id)
            self._payments[payment.id] = payment
        return payment

    def list(self, tenant_id: str = "") -> list[Payment]:
        with self._lock:
            payments = list(self._payments.values())
        if not tenant_id:
            return payments
        return [payment for payment in payments if payment.tenant_id == tenant_id]


class InMemoryCouponRepository(CouponRepository):
    def __init__(self) -> None:
        self._coupons: dict[str, Coupon] = {}
        self._lock = threading.Lock()

    def create(self, coupon: Coupon) -> Coupon:
        with self._lock:
            self._coupons[coupon.code.upper()] = coupon
        return coupon

    def get(self, code: str) -> Coupon:
        with self._lock:
            coupon = self._coupons.get(code.upper())
        if coupon is None:
            raise CouponNotFoundError(code)
        return coupon

    def update(self, coupon: Coupon) -> Coupon:
        with self._lock:
            if coupon.code.upper() not in self._coupons:
                raise CouponNotFoundError(coupon.code)
            self._coupons[coupon.code.upper()] = coupon
        return coupon

    def list(self) -> list[Coupon]:
        with self._lock:
            return list(self._coupons.values())

    def delete(self, code: str) -> bool:
        with self._lock:
            key = code.upper()
            if key not in self._coupons:
                return False
            del self._coupons[key]
        return True


class InMemoryUsageRepository(UsageRepository):
    def __init__(self) -> None:
        self._records: list[UsageRecord] = []
        self._lock = threading.Lock()

    def record(self, record: UsageRecord) -> UsageRecord:
        with self._lock:
            self._records.append(record)
        return record

    def usage(self, tenant_id: str, category: str, since: float = 0.0) -> int:
        total = 0
        with self._lock:
            for record in self._records:
                if record.tenant_id == tenant_id and record.category.value == category and record.recorded_at >= since:
                    total += record.amount
        return total

    def usage_by_category(self, tenant_id: str, since: float = 0.0) -> dict[str, int]:
        result: dict[str, int] = {}
        with self._lock:
            for record in self._records:
                if record.tenant_id == tenant_id and record.recorded_at >= since:
                    key = record.category.value
                    result[key] = result.get(key, 0) + record.amount
        return result

    def reset(self, tenant_id: str, category: str = "") -> None:
        with self._lock:
            self._records = [
                record
                for record in self._records
                if not (record.tenant_id == tenant_id and (not category or record.category.value == category))
            ]


class BillingRepositories:
    """Aggregates all repositories for dependency injection."""

    def __init__(
        self,
        subscriptions: SubscriptionRepository | None = None,
        invoices: InvoiceRepository | None = None,
        payments: PaymentRepository | None = None,
        coupons: CouponRepository | None = None,
        usage: UsageRepository | None = None,
    ) -> None:
        self.subscriptions = subscriptions or InMemorySubscriptionRepository()
        self.invoices = invoices or InMemoryInvoiceRepository()
        self.payments = payments or InMemoryPaymentRepository()
        self.coupons = coupons or InMemoryCouponRepository()
        self.usage = usage or InMemoryUsageRepository()

    def as_dict(self) -> dict[str, Any]:
        return {
            "subscriptions": self.subscriptions,
            "invoices": self.invoices,
            "payments": self.payments,
            "coupons": self.coupons,
            "usage": self.usage,
        }
