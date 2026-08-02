"""Webhook framework for the API Gateway (Stage 10.4).

Webhooks deliver gateway events to registered subscribers with retry and
backoff, HMAC signing when a shared secret is configured, and delivery
history for observability.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from typing import Any, Callable

from .config import GatewayConfig
from .exceptions import WebhookError
from .logging import GatewayLogger
from .models import Webhook, WebhookDelivery

DeliveryTransport = Callable[[str, dict[str, str], Any], int]


def _default_transport(url: str, headers: dict[str, str], payload: Any) -> int:
    """Local transport used by tests and in-process deployments."""
    return 200


class WebhookManager:
    """Thread-safe registry and dispatcher of webhook subscriptions."""

    def __init__(
        self,
        config: GatewayConfig | None = None,
        logger: GatewayLogger | None = None,
        transport: DeliveryTransport | None = None,
    ):
        self._config = config or GatewayConfig()
        self._logger = logger or GatewayLogger(enabled=False)
        self._transport = transport or _default_transport
        self._lock = threading.RLock()
        self._webhooks: dict[str, Webhook] = {}
        self._deliveries: list[WebhookDelivery] = []

    @property
    def enabled(self) -> bool:
        return self._config.webhooks_enabled

    def register(self, url: str, events: list[str] | None = None, secret: str = "", active: bool = True) -> Webhook:
        if not url.startswith(("http://", "https://")):
            raise WebhookError("Webhook URL must be absolute")
        webhook = Webhook(url=url, events=events or ["*"], secret=secret or self._config.webhook_secret, active=active)
        with self._lock:
            self._webhooks[webhook.id] = webhook
        if self._logger.enabled:
            self._logger.log_event("webhook.registered", webhook_id=webhook.id, url=url)
        return webhook

    def unregister(self, webhook_id: str) -> bool:
        with self._lock:
            return self._webhooks.pop(webhook_id, None) is not None

    def get(self, webhook_id: str) -> Webhook | None:
        with self._lock:
            return self._webhooks.get(webhook_id)

    def list(self, event: str = "") -> list[Webhook]:
        with self._lock:
            hooks = [hook for hook in self._webhooks.values() if hook.active]
            if event:
                hooks = [hook for hook in hooks if "*" in hook.events or event in hook.events]
            return sorted(hooks, key=lambda hook: hook.created_at)

    def set_active(self, webhook_id: str, active: bool) -> Webhook:
        with self._lock:
            webhook = self._webhooks.get(webhook_id)
            if webhook is None:
                raise WebhookError("Webhook not found", webhook_id=webhook_id)
            webhook.active = active
            return webhook

    def _sign(self, webhook: Webhook, payload: Any) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if webhook.secret:
            body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
            signature = hmac.new(webhook.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
        return headers

    def deliver(self, event: str, payload: dict[str, Any]) -> list[WebhookDelivery]:
        """Deliver an event to all matching webhooks, honoring retries."""
        if not self._config.webhooks_enabled:
            return []
        results: list[WebhookDelivery] = []
        for webhook in self.list(event):
            results.append(self._deliver_one(webhook, event, payload))
        return results

    def _deliver_one(self, webhook: Webhook, event: str, payload: dict[str, Any]) -> WebhookDelivery:
        max_retries = self._config.webhook_max_retries
        last_status = 500
        last_error = ""
        attempts = 0
        for attempt in range(1, max_retries + 1):
            attempts = attempt
            if attempt > 1:
                time.sleep(self._config.webhook_retry_backoff_seconds * (2 ** (attempt - 2)))
            try:
                headers = self._sign(webhook, payload)
                last_status = self._transport(webhook.url, headers, payload)
                if 200 <= last_status < 300:
                    break
                last_error = f"HTTP {last_status}"
            except Exception as exc:  # pragma: no cover - transport dependent
                last_status = 502
                last_error = str(exc)
        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            url=webhook.url,
            event=event,
            payload=dict(payload),
            status_code=last_status,
            attempts=attempts,
            error=last_error,
        )
        with self._lock:
            self._deliveries.append(delivery)
        if self._logger.enabled:
                self._logger.log_event(
                    "webhook.delivered", webhook_id=webhook.id, event_name=event,
                status_code=last_status, attempts=attempts,
            )
        return delivery

    def deliveries(self, webhook_id: str = "", event: str = "", limit: int = 100) -> list[WebhookDelivery]:
        with self._lock:
            items = self._deliveries
            if webhook_id:
                items = [d for d in items if d.webhook_id == webhook_id]
            if event:
                items = [d for d in items if d.event == event]
            return list(reversed(items))[:limit]
