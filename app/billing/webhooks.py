from __future__ import annotations

import uuid
from typing import Any, Callable

from .exceptions import WebhookEventError, WebhookVerificationError
from .logging import BillingLogger
from .providers import PaymentProvider


class BillingWebhookHandler:
    """Receives and processes billing provider webhooks.

    Events handled: ``payment.succeeded``, ``payment.failed``,
    ``invoice.payment_failed``, ``invoice.overdue``, ``subscription.updated``,
    ``subscription.deleted``, ``subscription.resumed``.
    """

    def __init__(
        self,
        provider: PaymentProvider | None = None,
        logger: BillingLogger | None = None,
    ) -> None:
        self._provider = provider
        self._logger = logger or BillingLogger()
        self._processed: set[str] = set()
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "payment.succeeded": self._on_payment_succeeded,
            "payment.failed": self._on_payment_failed,
            "invoice.payment_failed": self._on_payment_failed,
            "invoice.overdue": self._on_invoice_overdue,
            "subscription.updated": self._on_subscription_updated,
            "subscription.deleted": self._on_subscription_deleted,
            "subscription.resumed": self._on_subscription_resumed,
        }

    def handle(self, event_type: str, data: dict[str, Any], signature: str = "") -> dict[str, Any]:
        provider = self._provider
        if provider is not None:
            raw = data.get("_raw", "")
            if not provider.verify_webhook(raw, signature):
                raise WebhookVerificationError(provider.name)
        event_id = str(data.get("id", ""))
        if event_id and event_id in self._processed:
            return {"event": event_type, "processed": False, "reason": "duplicate"}
        self._processed.add(event_id)
        handler = self._handlers.get(event_type)
        if handler is None:
            raise WebhookEventError(f"Unsupported webhook event {event_type!r}", event_type=event_type)
        result = handler(data)
        result["event"] = event_type
        result["processed"] = True
        payload = {key: value for key, value in result.items() if key != "event"}
        self._logger.log_event("webhook", event_name=event_type, **payload)
        return result

    def _on_payment_succeeded(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "invoice_id": data.get("invoice_id", ""),
            "payment_id": data.get("payment_id", f"wh_{uuid.uuid4().hex[:12]}"),
        }

    def _on_payment_failed(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "invoice_id": data.get("invoice_id", ""),
            "subscription_id": data.get("subscription_id", ""),
            "failure_reason": data.get("failure_reason", "declined"),
        }

    def _on_invoice_overdue(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "invoice_id": data.get("invoice_id", ""),
            "subscription_id": data.get("subscription_id", ""),
        }

    def _on_subscription_updated(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "subscription_id": data.get("subscription_id", ""),
            "plan_id": data.get("plan_id", ""),
            "status": data.get("status", ""),
        }

    def _on_subscription_deleted(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "subscription_id": data.get("subscription_id", ""),
        }

    def _on_subscription_resumed(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "subscription_id": data.get("subscription_id", ""),
        }

    def handle_payload(self, payload: dict[str, Any], signature: str = "") -> dict[str, Any]:
        event_type = payload.get("type") or payload.get("event")
        if not event_type:
            raise WebhookEventError("Webhook payload is missing an event type")
        return self.handle(event_type, payload, signature=signature)

    @property
    def processed(self) -> int:
        return len(self._processed)

    @property
    def handlers(self) -> list[str]:
        return list(self._handlers.keys())
