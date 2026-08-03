from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from abc import ABC
from typing import Any

from .exceptions import PaymentError, PaymentFailedError, ProviderConfigurationError
from .models import Payment, PaymentProviderName, PaymentStatus


def _verify_hmac(secret: str, payload: str, signature: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class PaymentProvider(ABC):  # noqa: B024
    """Strategy: a pluggable payment provider integration."""

    name: str = ""

    def __init__(self, secret: str = "", settings: dict[str, Any] | None = None) -> None:
        self._secret = secret
        self._settings = settings or {}
        self._transport = self._settings.get("transport")

    @property
    def configured(self) -> bool:
        return bool(self._secret)

    def charge(self, tenant_id: str, amount: float, reference: str, method: str = "card") -> Payment:
        if not self.configured:
            raise ProviderConfigurationError(self.name)
        return self._charge(tenant_id, amount, reference, method)

    def refund(self, payment: Payment) -> Payment:
        if not self.configured:
            raise ProviderConfigurationError(self.name)
        return self._refund(payment)

    def verify_webhook(self, payload: str, signature: str) -> bool:
        return _verify_hmac(self._secret, payload, signature)

    def _charge(self, tenant_id: str, amount: float, reference: str, method: str) -> Payment:
        raise NotImplementedError

    def _refund(self, payment: Payment) -> Payment:
        raise NotImplementedError

    def _post(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        if self._transport is not None:
            return self._transport(url, data)
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"}
        )  # noqa: E501
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return {"status": response.status, "body": response.read().decode()}
        except urllib.error.HTTPError as exc:
            return {"status": exc.code, "body": exc.read().decode()}
        except Exception:
            return {"status": 0, "body": ""}


class StripeProvider(PaymentProvider):
    name = PaymentProviderName.STRIPE.value

    def _charge(self, tenant_id: str, amount: float, reference: str, method: str) -> Payment:
        result = self._post(
            "https://api.stripe.com/v1/charges", {"amount": amount, "currency": "usd", "reference": reference}
        )  # noqa: E501
        if result["status"] == 402:
            raise PaymentFailedError("Stripe declined the charge", provider=self.name, reference=reference)
        if result["status"] == 0:
            raise PaymentError("Stripe charge request failed", provider=self.name, reference=reference)
        return Payment(
            id=f"py_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            invoice_id=reference,
            amount=amount,
            provider=self.name,
            method=method,
            status=PaymentStatus.COMPLETED,
            reference=f"ch_{uuid.uuid4().hex[:12]}",
        )

    def _refund(self, payment: Payment) -> Payment:
        result = self._post("https://api.stripe.com/v1/refunds", {"payment": payment.reference})
        if result["status"] != 200:
            raise PaymentError("Stripe refund failed", provider=self.name)
        payment.status = PaymentStatus.REFUNDED
        return payment


class PaddleProvider(PaymentProvider):
    name = PaymentProviderName.PADDLE.value

    def _charge(self, tenant_id: str, amount: float, reference: str, method: str) -> Payment:
        result = self._post("https://vendors.paddle.com/api/2.0/payment", {"amount": amount, "reference": reference})
        if result["status"] != 200:
            raise PaymentFailedError("Paddle could not process the payment", provider=self.name)
        return Payment(
            id=f"py_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            invoice_id=reference,
            amount=amount,
            provider=self.name,
            method=method,
            status=PaymentStatus.COMPLETED,
            reference=f"pd_{uuid.uuid4().hex[:12]}",
        )

    def _refund(self, payment: Payment) -> Payment:
        payment.status = PaymentStatus.REFUNDED
        return payment


class LemonSqueezyProvider(PaymentProvider):
    name = PaymentProviderName.LEMON_SQUEEZY.value

    def _charge(self, tenant_id: str, amount: float, reference: str, method: str) -> Payment:
        result = self._post("https://api.lemonsqueezy.com/v1/checkouts", {"amount": amount, "reference": reference})
        if result["status"] != 200:
            raise PaymentFailedError("Lemon Squeezy could not process the payment", provider=self.name)
        return Payment(
            id=f"py_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            invoice_id=reference,
            amount=amount,
            provider=self.name,
            method=method,
            status=PaymentStatus.COMPLETED,
            reference=f"ls_{uuid.uuid4().hex[:12]}",
        )

    def _refund(self, payment: Payment) -> Payment:
        payment.status = PaymentStatus.REFUNDED
        return payment


class MidtransProvider(PaymentProvider):
    name = PaymentProviderName.MIDTRANS.value

    def _charge(self, tenant_id: str, amount: float, reference: str, method: str) -> Payment:
        result = self._post(
            "https://api.midtrans.com/v2/charge",
            {"gross_amount": amount, "payment_type": method, "reference": reference},
        )
        if result["status"] not in (200, 201):
            raise PaymentFailedError("Midtrans could not process the payment", provider=self.name)
        return Payment(
            id=f"py_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            invoice_id=reference,
            amount=amount,
            provider=self.name,
            method=method,
            status=PaymentStatus.PENDING,
            reference=f"mt_{uuid.uuid4().hex[:12]}",
        )

    def _refund(self, payment: Payment) -> Payment:
        payment.status = PaymentStatus.REFUNDED
        return payment


class XenditProvider(PaymentProvider):
    name = PaymentProviderName.XENDIT.value

    def _charge(self, tenant_id: str, amount: float, reference: str, method: str) -> Payment:
        result = self._post(
            "https://api.xendit.co/charges",
            {"amount": amount, "payment_method": method, "reference": reference},
        )
        if result["status"] != 200:
            raise PaymentFailedError("Xendit could not process the payment", provider=self.name)
        return Payment(
            id=f"py_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            invoice_id=reference,
            amount=amount,
            provider=self.name,
            method=method,
            status=PaymentStatus.PENDING,
            reference=f"xd_{uuid.uuid4().hex[:12]}",
        )

    def _refund(self, payment: Payment) -> Payment:
        payment.status = PaymentStatus.REFUNDED
        return payment


class PayPalProvider(PaymentProvider):
    name = PaymentProviderName.PAYPAL.value

    def _charge(self, tenant_id: str, amount: float, reference: str, method: str) -> Payment:
        result = self._post(
            "https://api-m.paypal.com/v1/payments/payment",
            {"transactions": [{"amount": {"total": amount, "currency": "USD"}, "reference": reference}]},
        )
        if result["status"] != 201:
            raise PaymentFailedError("PayPal could not process the payment", provider=self.name)
        return Payment(
            id=f"py_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            invoice_id=reference,
            amount=amount,
            provider=self.name,
            method=method,
            status=PaymentStatus.COMPLETED,
            reference=f"pp_{uuid.uuid4().hex[:12]}",
        )

    def _refund(self, payment: Payment) -> Payment:
        payment.status = PaymentStatus.REFUNDED
        return payment


class ManualInvoiceProvider(PaymentProvider):
    name = PaymentProviderName.MANUAL.value

    @property
    def configured(self) -> bool:
        return True

    def _charge(self, tenant_id: str, amount: float, reference: str, method: str) -> Payment:
        return Payment(
            id=f"py_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            invoice_id=reference,
            amount=amount,
            provider=self.name,
            method=method or "bank_transfer",
            status=PaymentStatus.PENDING,
            reference=f"inv_{int(time.time())}",
        )

    def _refund(self, payment: Payment) -> Payment:
        payment.status = PaymentStatus.REFUNDED
        return payment


class PaymentProviderFactory:
    """Factory: builds payment provider strategies by name."""

    _registry: dict[str, type[PaymentProvider]] = {
        PaymentProviderName.STRIPE.value: StripeProvider,
        PaymentProviderName.PADDLE.value: PaddleProvider,
        PaymentProviderName.LEMON_SQUEEZY.value: LemonSqueezyProvider,
        PaymentProviderName.MIDTRANS.value: MidtransProvider,
        PaymentProviderName.XENDIT.value: XenditProvider,
        PaymentProviderName.PAYPAL.value: PayPalProvider,
        PaymentProviderName.MANUAL.value: ManualInvoiceProvider,
    }

    @classmethod
    def create(cls, name: str, secret: str = "", settings: dict[str, Any] | None = None) -> PaymentProvider:
        provider_cls = cls._registry.get(name)
        if provider_cls is None:
            raise ProviderConfigurationError(name, "unknown")
        return provider_cls(secret=secret, settings=settings)

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._registry.keys())
