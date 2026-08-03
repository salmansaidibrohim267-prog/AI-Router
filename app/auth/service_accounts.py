from __future__ import annotations

import hashlib
import secrets
import time
import uuid

from .config import AuthConfig
from .exceptions import ServiceAccountError
from .logging import AuthLogger
from .models import ServiceAccount
from .repository import ServiceAccountRepository
from .statistics import AuthMetricsTracker


class ServiceAccountManager:
    def __init__(
        self,
        config: AuthConfig | None = None,
        repository: ServiceAccountRepository | None = None,
        logger: AuthLogger | None = None,
        metrics: AuthMetricsTracker | None = None,
    ):
        self._config = config or AuthConfig()
        self._repository = repository or ServiceAccountRepository()
        self._logger = logger or AuthLogger()
        self._metrics = metrics or AuthMetricsTracker(self._config)

    @property
    def repository(self) -> ServiceAccountRepository:
        return self._repository

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(f"sa:{token}".encode()).hexdigest()

    def create(
        self,
        tenant_id: str,
        name: str,
        scopes: list[str] | None = None,
        description: str = "",
        ttl: int | None = None,
    ) -> tuple[ServiceAccount, str]:
        raw = f"sa_{secrets.token_hex(32)}"
        now = time.time()
        expires_at = now + (ttl if ttl is not None else self._config.service_account_ttl_default)
        account = ServiceAccount(
            id=f"saacc_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            name=name,
            token_hash=self._hash(raw),
            scopes=scopes or [],
            description=description,
            expires_at=expires_at,
        )
        self._repository.create(account)
        self._logger.log_event("service_account_created", tenant_id=tenant_id, name=name)
        self._metrics.record("service_account_created", tenant_id)
        return account, raw

    def authenticate(self, raw_token: str, require_scopes: list[str] | None = None) -> ServiceAccount:
        account = self._repository.get_by_token_hash(self._hash(raw_token))
        if account is None:
            raise ServiceAccountError("Invalid service account token")
        if account.revoked:
            raise ServiceAccountError("Service account revoked")
        if account.is_expired:
            raise ServiceAccountError("Service account expired")
        if require_scopes and not set(require_scopes).issubset(set(account.scopes)):
            raise ServiceAccountError(f"Service account missing scopes: {require_scopes}")
        account.usage_count += 1
        account.last_used_at = time.time()
        self._repository.update(account)
        return account

    def revoke(self, account_id: str) -> bool:
        account = self._repository.get(account_id)
        if account is None:
            raise ServiceAccountError("Service account not found")
        account.revoked = True
        self._repository.update(account)
        return True

    def rotate(self, account_id: str) -> tuple[ServiceAccount, str]:
        account = self._repository.get(account_id)
        if account is None:
            raise ServiceAccountError("Service account not found")
        remaining = int(account.expires_at - time.time()) if account.expires_at else None
        ttl = remaining if remaining is not None and remaining > 0 else None
        return self.create(
            tenant_id=account.tenant_id,
            name=account.name,
            scopes=account.scopes,
            description=account.description,
            ttl=ttl,
        )

    def list(self, tenant_id: str | None = None) -> list[ServiceAccount]:
        if tenant_id is not None:
            return self._repository.list_for_tenant(tenant_id)
        return self._repository.list_all()
