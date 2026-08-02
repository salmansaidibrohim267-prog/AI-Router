from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any

from .config import AuthConfig
from .exceptions import APIKeyError
from .logging import AuthLogger
from .models import APIKey
from .repository import APIKeyRepository
from .statistics import AuthMetricsTracker


class APIKeyManager:
    def __init__(
        self,
        config: AuthConfig | None = None,
        repository: APIKeyRepository | None = None,
        logger: AuthLogger | None = None,
        metrics: AuthMetricsTracker | None = None,
    ):
        self._config = config or AuthConfig()
        self._repository = repository or APIKeyRepository()
        self._logger = logger or AuthLogger()
        self._metrics = metrics or AuthMetricsTracker(self._config)

    @property
    def repository(self) -> APIKeyRepository:
        return self._repository

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(f"apikey:{key}".encode()).hexdigest()

    def generate(
        self,
        tenant_id: str,
        name: str,
        scopes: list[str] | None = None,
        ttl: int | None = None,
        user_id: str = "",
    ) -> tuple[APIKey, str]:
        raw = f"ak_{secrets.token_hex(24)}"
        now = time.time()
        expires_at = now + (ttl if ttl is not None else self._config.api_key_ttl_default)
        key = APIKey(
            id=f"key_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            name=name,
            key_prefix=raw[:10],
            key_hash=self._hash(raw),
            scopes=scopes or [],
            user_id=user_id,
            expires_at=expires_at,
        )
        self._repository.create(key)
        self._logger.log_event("api_key_created", tenant_id=tenant_id, name=name)
        self._metrics.record("api_key_created", tenant_id)
        return key, raw

    def authenticate(self, raw_key: str, require_scopes: list[str] | None = None) -> APIKey:
        key = self._repository.get_by_hash(self._hash(raw_key))
        if key is None:
            raise APIKeyError("Invalid API key")
        if key.revoked:
            raise APIKeyError("API key revoked")
        if key.is_expired:
            raise APIKeyError("API key expired")
        if require_scopes and not set(require_scopes).issubset(set(key.scopes)):
            raise APIKeyError(f"API key missing scopes: {require_scopes}")
        key.usage_count += 1
        key.last_used_at = time.time()
        self._repository.update(key)
        return key

    def revoke(self, key_id: str) -> bool:
        key = self._repository.get(key_id)
        if key is None:
            raise APIKeyError("API key not found")
        key.revoked = True
        self._repository.update(key)
        return True

    def rotate(self, key_id: str) -> tuple[APIKey, str]:
        key = self._repository.get(key_id)
        if key is None:
            raise APIKeyError("API key not found")
        remaining = int(key.expires_at - time.time()) if key.expires_at else None
        ttl = remaining if remaining is not None and remaining > 0 else None
        return self.generate(
            tenant_id=key.tenant_id,
            name=key.name,
            scopes=key.scopes,
            ttl=ttl,
            user_id=key.user_id,
        )

    def list(self, tenant_id: str | None = None) -> list[APIKey]:
        if tenant_id is not None:
            return self._repository.list_for_tenant(tenant_id)
        return self._repository.list_all()
