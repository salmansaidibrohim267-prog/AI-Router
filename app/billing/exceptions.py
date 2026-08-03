from __future__ import annotations

from typing import Any


class BillingError(Exception):
    """Base class for all billing platform errors."""

    status_code = 400
    error_code = "billing_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PlanNotFoundError(BillingError):
    status_code = 404
    error_code = "plan_not_found"

    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Plan {plan_id!r} does not exist", plan_id=plan_id)


class SubscriptionNotFoundError(BillingError):
    status_code = 404
    error_code = "subscription_not_found"

    def __init__(self, subscription_id: str) -> None:
        super().__init__(f"Subscription {subscription_id!r} does not exist", subscription_id=subscription_id)


class SubscriptionAlreadyExistsError(BillingError):
    status_code = 409
    error_code = "subscription_already_exists"

    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"Tenant {tenant_id!r} already has an active subscription", tenant_id=tenant_id)


class SubscriptionCancelledError(BillingError):
    status_code = 410
    error_code = "subscription_cancelled"

    def __init__(self, subscription_id: str) -> None:
        super().__init__(f"Subscription {subscription_id!r} is cancelled", subscription_id=subscription_id)


class InvalidTransitionError(BillingError):
    status_code = 409
    error_code = "invalid_transition"

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"Cannot transition subscription from {current!r} to {target!r}",
            current=current,
            target=target,
        )


class InvoiceNotFoundError(BillingError):
    status_code = 404
    error_code = "invoice_not_found"

    def __init__(self, invoice_id: str) -> None:
        super().__init__(f"Invoice {invoice_id!r} does not exist", invoice_id=invoice_id)


class InvoiceAlreadyPaidError(BillingError):
    status_code = 409
    error_code = "invoice_already_paid"

    def __init__(self, invoice_id: str) -> None:
        super().__init__(f"Invoice {invoice_id!r} is already paid", invoice_id=invoice_id)


class InvoiceError(BillingError):
    status_code = 422
    error_code = "invoice_error"


class PaymentFailedError(BillingError):
    status_code = 402
    error_code = "payment_failed"

    def __init__(self, message: str = "Payment was declined by the provider", **details: Any) -> None:
        super().__init__(message, **details)


class PaymentError(BillingError):
    status_code = 500
    error_code = "payment_error"

    def __init__(self, message: str = "Payment operation failed", **details) -> None:
        super().__init__(message, **details)


class ProviderConfigurationError(BillingError):
    status_code = 500
    error_code = "provider_configuration_error"

    def __init__(self, provider: str, detail: str = "not configured") -> None:
        super().__init__(f"Payment provider {provider!r} is {detail}", provider=provider, detail=detail)


class CouponNotFoundError(BillingError):
    status_code = 404
    error_code = "coupon_not_found"

    def __init__(self, code: str) -> None:
        super().__init__(f"Coupon {code!r} does not exist", code=code)


class CouponExpiredError(BillingError):
    status_code = 422
    error_code = "coupon_expired"

    def __init__(self, code: str) -> None:
        super().__init__(f"Coupon {code!r} has expired", code=code)


class CouponExhaustedError(BillingError):
    status_code = 422
    error_code = "coupon_exhausted"

    def __init__(self, code: str) -> None:
        super().__init__(f"Coupon {code!r} has reached its redemption limit", code=code)


class CouponInvalidError(BillingError):
    status_code = 422
    error_code = "coupon_invalid"

    def __init__(self, code: str, reason: str = "not applicable") -> None:
        super().__init__(f"Coupon {code!r} is {reason}", code=code, reason=reason)


class UsageRecordingError(BillingError):
    status_code = 422
    error_code = "usage_recording_error"


class WebhookVerificationError(BillingError):
    status_code = 401
    error_code = "webhook_verification_failed"

    def __init__(self, provider: str) -> None:
        super().__init__(f"Webhook signature verification failed for {provider!r}", provider=provider)


class WebhookEventError(BillingError):
    status_code = 422
    error_code = "webhook_event_error"


class QuotaSyncError(BillingError):
    status_code = 500
    error_code = "quota_sync_error"

    def __init__(self, target: str, detail: str = "failed to apply limits") -> None:
        super().__init__(f"Quota sync to {target!r} {detail}", target=target, detail=detail)


class TrialNotAllowedError(BillingError):
    status_code = 422
    error_code = "trial_not_allowed"

    def __init__(self, plan_id: str) -> None:
        super().__init__(f"Plan {plan_id!r} does not support trials", plan_id=plan_id)


class GracePeriodExceededError(BillingError):
    status_code = 410
    error_code = "grace_period_exceeded"

    def __init__(self, subscription_id: str) -> None:
        super().__init__(
            f"Grace period for subscription {subscription_id!r} has ended", subscription_id=subscription_id
        )  # noqa: E501
