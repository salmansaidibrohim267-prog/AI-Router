from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any, Callable

from .exceptions import QuotaSyncError
from .logging import BillingLogger
from .models import Plan, Subscription


class QuotaSyncTarget(ABC):
    """Observer: a subsystem that can consume plan quota limits."""

    name: str = ""

    @abstractmethod
    def apply(self, scope: str, limits: dict[str, int], plan_id: str) -> None:
        raise NotImplementedError


class GatewayQuotaTarget(QuotaSyncTarget):
    """Applies limits to the API Gateway QuotaManager (per-bucket limits).

    Billing categories are mapped to gateway quota buckets; categories the
    gateway does not track are skipped so one unknown bucket cannot fail sync.
    """

    name = "gateway"

    DEFAULT_BUCKET_MAPPING: dict[str, str] = {
        "api_requests": "requests",
        "vector_storage": "storage",
    }

    def __init__(self, quota_manager: Any, bucket_mapping: dict[str, str] | None = None) -> None:
        from app.gateway.quota import QUOTA_BUCKET_NAMES

        self._quota_manager = quota_manager
        self._bucket_mapping = dict(self.DEFAULT_BUCKET_MAPPING)
        if bucket_mapping:
            self._bucket_mapping.update(bucket_mapping)
        self._gateway_buckets = set(QUOTA_BUCKET_NAMES)

    def apply(self, scope: str, limits: dict[str, int], plan_id: str) -> None:
        for bucket, limit in limits.items():
            gateway_bucket = self._bucket_mapping.get(bucket, bucket)
            if gateway_bucket not in self._gateway_buckets:
                continue
            try:
                self._quota_manager.set_limit(scope, gateway_bucket, int(limit))
            except Exception as exc:
                raise QuotaSyncError(self.name, detail=str(exc)) from exc


class RateLimiterQuotaTarget(QuotaSyncTarget):
    """Applies request limits to the Gateway RateLimiter as fixed-window policies."""

    name = "rate_limiter"

    def __init__(self, limiter: Any, key_prefix: str = "plan", window_seconds: float = 3600.0) -> None:
        self._limiter = limiter
        self._key_prefix = key_prefix
        self._window_seconds = window_seconds

    def apply(self, scope: str, limits: dict[str, int], plan_id: str) -> None:
        requests = int(limits.get("api_requests", 0))
        if requests <= 0:
            return
        key = f"{self._key_prefix}:{scope}"
        try:
            self._limiter.set_policy(
                key,
                strategy="fixed_window",
                limit=requests,
                window_seconds=self._window_seconds,
            )
        except Exception as exc:
            raise QuotaSyncError(self.name, detail=str(exc)) from exc


class VectorStoreQuotaTarget(QuotaSyncTarget):
    """Applies storage limits to the Vector Store subsystem.

    The vector store exposes no unified limits API, so limits are pushed into
    a per-scope settings registry that the store wiring consumes.
    """

    name = "vector_store"

    def __init__(self) -> None:
        self._limits: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    @property
    def limits(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {scope: dict(limits) for scope, limits in self._limits.items()}

    def apply(self, scope: str, limits: dict[str, int], plan_id: str) -> None:
        with self._lock:
            self._limits[scope] = {
                "storage_bytes": int(limits.get("vector_storage", 0)) * 1024,
                "embeddings": int(limits.get("embeddings", 0)),
                "plan": plan_id,
            }


class MCPQuotaTarget(QuotaSyncTarget):
    """Applies MCP call limits to the MCP subsystem."""

    name = "mcp"

    def __init__(self) -> None:
        self._limits: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    @property
    def limits(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {scope: dict(limits) for scope, limits in self._limits.items()}

    def apply(self, scope: str, limits: dict[str, int], plan_id: str) -> None:
        with self._lock:
            self._limits[scope] = {
                "mcp_calls": int(limits.get("mcp_calls", 0)),
                "plan": plan_id,
            }


class PluginQuotaTarget(QuotaSyncTarget):
    """Applies plugin and upload limits to the Plugin Platform."""

    name = "plugins"

    def __init__(self) -> None:
        self._limits: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    @property
    def limits(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {scope: dict(limits) for scope, limits in self._limits.items()}

    def apply(self, scope: str, limits: dict[str, int], plan_id: str) -> None:
        with self._lock:
            self._limits[scope] = {
                "plugins": int(limits.get("plugins", 0)),
                "uploads": int(limits.get("uploads", 0)),
                "plan": plan_id,
            }


class QuotaSyncCoordinator:
    """Subject for the Observer pattern: notifies all quota targets."""

    def __init__(self, logger: BillingLogger | None = None) -> None:
        self._targets: dict[str, QuotaSyncTarget] = {}
        self._logger = logger or BillingLogger()
        self._lock = threading.Lock()

    def register(self, target: QuotaSyncTarget) -> None:
        with self._lock:
            self._targets[target.name] = target

    def unregister(self, name: str) -> bool:
        with self._lock:
            if name not in self._targets:
                return False
            del self._targets[name]
        return True

    def targets(self) -> list[str]:
        with self._lock:
            return list(self._targets.keys())

    def sync(self, scope: str, plan: Plan, subscription: Subscription | None = None) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, target in list(self._targets.items()):
            try:
                target.apply(scope, plan.limits, plan.id)
                results[name] = "ok"
            except QuotaSyncError as exc:
                results[name] = exc.message
        self._logger.log_event(
            "quota.synced",
            scope=scope,
            plan_id=plan.id,
            results=results,
        )
        return results


class BillingEventBus:
    """Observer registry for billing lifecycle events."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[["Subscription", dict[str, Any]], None]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event: str, callback: Callable[["Subscription", dict[str, Any]], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(event, []).append(callback)

    def unsubscribe(self, event: str, callback: Callable[["Subscription", dict[str, Any]], None]) -> bool:
        with self._lock:
            callbacks = self._subscribers.get(event, [])
            if callback not in callbacks:
                return False
            callbacks.remove(callback)
            return True

    def publish(self, event: str, subscription: "Subscription", payload: dict[str, Any] | None = None) -> int:
        delivered = 0
        for callback in list(self._subscribers.get(event, [])):
            callback(subscription, payload or {})
            delivered += 1
        return delivered
