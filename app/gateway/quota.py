"""Quota management for the API Gateway (Stage 10.4).

Tracks usage per client across five buckets: requests, tokens, storage,
embeddings, and MCP calls. Quotas are namespaced per scope (client id).
"""

from __future__ import annotations

import threading
from typing import Any

from .config import GatewayConfig
from .exceptions import QuotaExceededError
from .models import QuotaConsumption

QUOTA_BUCKET_NAMES = ("requests", "tokens", "storage", "embeddings", "mcp_calls")

BUCKET_KEYS = {
    "requests": "max_quota_requests",
    "tokens": "max_quota_tokens",
    "storage": "max_quota_storage",
    "embeddings": "max_quota_embeddings",
    "mcp_calls": "max_quota_mcp_calls",
}


class QuotaManager:
    """Thread-safe per-scope quota accounting."""

    def __init__(self, config: GatewayConfig | None = None):
        self._config = config or GatewayConfig()
        self._lock = threading.RLock()
        self._usage: dict[tuple[str, str], int] = {}
        self._limits: dict[tuple[str, str], int] = {}
        self._reset_at: dict[tuple[str, str], float] = {}
        self._scopes: dict[str, set[str]] = {}

    @property
    def config(self) -> GatewayConfig:
        return self._config

    def default_limit(self, bucket: str) -> int:
        key = BUCKET_KEYS.get(bucket, "max_quota_requests")
        return int(getattr(self._config, key, 100000))

    def set_limit(self, scope: str, bucket: str, limit: int) -> None:
        if bucket not in QUOTA_BUCKET_NAMES:
            raise ValueError(f"Unknown quota bucket {bucket!r}")
        with self._lock:
            self._limits[(scope, bucket)] = int(limit)
            self._scopes.setdefault(scope, set()).add(bucket)

    def limit_for(self, scope: str, bucket: str) -> int:
        with self._lock:
            return self._limits.get((scope, bucket), self.default_limit(bucket))

    def usage(self, scope: str, bucket: str) -> int:
        with self._lock:
            return self._usage.get((scope, bucket), 0)

    def consumption(self, scope: str, bucket: str) -> QuotaConsumption:
        limit = self.limit_for(scope, bucket)
        used = self.usage(scope, bucket)
        return QuotaConsumption(bucket=bucket, used=used, limit=limit, remaining=max(0, limit - used))

    def check(self, scope: str, bucket: str, amount: int = 1) -> QuotaConsumption:
        with self._lock:
            limit = self.limit_for(scope, bucket)
            used = self.usage(scope, bucket)
            if used + amount > limit:
                raise QuotaExceededError(bucket=bucket, limit=limit, used=used)
            self._usage[(scope, bucket)] = used + amount
            self._scopes.setdefault(scope, set()).add(bucket)
            return QuotaConsumption(bucket=bucket, used=used + amount, limit=limit, remaining=limit - used - amount)

    def try_check(self, scope: str, bucket: str, amount: int = 1) -> QuotaConsumption | None:
        """Non-raising variant; returns ``None`` when the quota is exceeded."""
        try:
            return self.check(scope, bucket, amount)
        except QuotaExceededError:
            return None

    def refund(self, scope: str, bucket: str, amount: int = 1) -> QuotaConsumption:
        with self._lock:
            used = max(0, self.usage(scope, bucket) - amount)
            self._usage[(scope, bucket)] = used
            limit = self.limit_for(scope, bucket)
            return QuotaConsumption(bucket=bucket, used=used, limit=limit, remaining=max(0, limit - used))

    def reset(self, scope: str | None = None, bucket: str | None = None) -> None:
        with self._lock:
            if scope is None:
                self._usage.clear()
                return
            if bucket is None:
                self._usage = {k: v for k, v in self._usage.items() if k[0] != scope}
                return
            self._usage.pop((scope, bucket), None)

    def usage_by_scope(self, scope: str) -> dict[str, int]:
        with self._lock:
            return {bucket: self._usage.get((scope, bucket), 0) for bucket in sorted(self._scopes.get(scope, set()))}

    def summary(self, scope: str) -> dict[str, Any]:
        with self._lock:
            result: dict[str, Any] = {"scope": scope}
            buckets = sorted(self._scopes.get(scope, set()))
            for bucket in buckets:
                result[bucket] = self.consumption(scope, bucket).to_dict()
            return result
