from __future__ import annotations

from typing import Any

from .config import TenancyConfig
from .exceptions import TenantContextMissingError, TenantIsolationError, TenantSuspendedError
from .models import TenantContext


class TenantIsolation:
    def __init__(self, config: TenancyConfig | None = None):
        self._config = config or TenancyConfig()

    @property
    def config(self) -> TenancyConfig:
        return self._config

    def prefix_for(self, namespace: str, tenant_id: str) -> str:
        return f"{self._config.isolation_prefix}:{tenant_id}:{namespace}"

    def key(self, tenant_id: str, key: str) -> str:
        return f"{self._config.isolation_prefix}:{tenant_id}:{key}"

    def cache_key(self, tenant_id: str, key: str) -> str:
        return self.key(tenant_id, f"{self._config.cache_namespace}:{key}")

    def kb_namespace(self, tenant_id: str) -> str:
        return self.prefix_for(self._config.kb_namespace, tenant_id)

    def vector_namespace(self, tenant_id: str) -> str:
        return self.prefix_for(self._config.vector_namespace, tenant_id)

    def memory_scope(
        self,
        tenant_id: str,
        workspace_id: str = "",
        user_id: str = "",
        session_id: str = "",
    ) -> dict[str, str]:
        scope: dict[str, str] = {"tenant_id": tenant_id}
        if workspace_id:
            scope["workspace_id"] = workspace_id
        if user_id:
            scope["user_id"] = user_id
        if session_id:
            scope["session_id"] = session_id
        return scope

    def citation_namespace(self, tenant_id: str) -> str:
        return self.prefix_for(self._config.citation_namespace, tenant_id)

    def mcp_prefix(self, tenant_id: str) -> str:
        return self.prefix_for(self._config.mcp_namespace, tenant_id)

    def metrics_name(self, tenant_id: str, name: str) -> str:
        return f"{self.prefix_for(self._config.metrics_namespace, tenant_id)}:{name}"

    def log_name(self, tenant_id: str, name: str) -> str:
        return f"{self.prefix_for(self._config.log_namespace, tenant_id)}:{name}"

    def enforce(self, context: TenantContext | None) -> TenantContext:
        if context is None or not context.tenant_id:
            raise TenantContextMissingError()
        if self._config.enforce_active and context.status == "suspended":
            raise TenantSuspendedError(context.tenant_id)
        if self._config.enforce_active and context.status == "deleted":
            raise TenantIsolationError(
                f"Tenant {context.tenant_id!r} is deleted and cannot be accessed"
            )
        return context

    def assert_isolated(self, context: TenantContext | None, other: TenantContext | None) -> None:
        if context is None or other is None:
            return
        if context.tenant_id and other.tenant_id and context.tenant_id != other.tenant_id:
            raise TenantIsolationError(
                f"Cross-tenant access denied: {context.tenant_id} != {other.tenant_id}"
            )
