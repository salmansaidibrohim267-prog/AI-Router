from __future__ import annotations

import time
import uuid
from typing import Any

from .audit import AuditLogger
from .config import TenancyConfig
from .exceptions import (
    TenantAlreadyExistsError,
    TenantDeletedError,
    TenantNotFoundError,
    TenantSuspendedError,
)
from .logging import TenancyLogger
from .models import CONFIG_SECTIONS, Tenant, TenantLimits, TenantStatus
from .repository import InMemoryTenantRepository, TenantRepository
from .statistics import TenancyMetricsTracker


class TenantManager:
    def __init__(
        self,
        repository: TenantRepository | None = None,
        config: TenancyConfig | None = None,
        logger: TenancyLogger | None = None,
        metrics: TenancyMetricsTracker | None = None,
        audit: AuditLogger | None = None,
    ):
        self._repository = repository or InMemoryTenantRepository()
        self._config = config or TenancyConfig()
        self._logger = logger or TenancyLogger()
        self._metrics = metrics or TenancyMetricsTracker(self._config)
        self._audit = audit or AuditLogger(self._config, self._logger)

    @property
    def repository(self) -> TenantRepository:
        return self._repository

    @property
    def audit(self) -> AuditLogger:
        return self._audit

    def create(
        self,
        name: str,
        tenant_id: str | None = None,
        plan: str = "free",
        limits: TenantLimits | None = None,
        config: dict[str, dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Tenant:
        tenant_id = tenant_id or f"t_{uuid.uuid4().hex[:12]}"
        self._guard_config_sections(config)
        tenant = Tenant(
            id=tenant_id,
            name=name,
            plan=plan,
            limits=limits or TenantLimits(),
            config=config or {},
            metadata=metadata or {},
            status=TenantStatus.ACTIVE,
        )
        try:
            self._repository.get(tenant_id)
        except TenantNotFoundError:
            pass
        else:
            self._metrics.record_error(tenant_id, "duplicate_create")
            raise TenantAlreadyExistsError(tenant_id)
        self._repository.create(tenant)
        self._audit.record(
            action="tenant.created",
            tenant_id=tenant_id,
            resource=f"tenant:{tenant_id}",
            details={"name": name, "plan": plan},
        )
        self._logger.log_event("created", tenant_id=tenant_id, name=name, plan=plan)
        return tenant

    def _guard_config_sections(self, config: dict[str, dict[str, Any]] | None) -> None:
        if config is None:
            return
        for section in config:
            if section not in CONFIG_SECTIONS:
                raise ValueError(f"Unknown tenant config section {section!r}")

    def update(self, tenant_id: str, **fields: Any) -> Tenant:
        tenant = self.get(tenant_id)
        if tenant.is_deleted:
            raise TenantDeletedError(tenant_id)
        allowed = {"name", "plan", "limits", "config", "metadata", "status"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unknown tenant field {key!r}")
            if key == "limits" and isinstance(value, dict):
                value = TenantLimits.from_dict(value)
            setattr(tenant, key, value)
        tenant.updated_at = time.time()
        self._repository.update(tenant)
        self._audit.record(
            action="tenant.updated",
            tenant_id=tenant_id,
            resource=f"tenant:{tenant_id}",
            details={k: str(v) for k, v in fields.items()},
        )
        return tenant

    def delete(self, tenant_id: str) -> bool:
        tenant = self.get(tenant_id)
        if tenant.is_deleted:
            raise TenantDeletedError(tenant_id)
        tenant.status = TenantStatus.DELETED
        tenant.updated_at = time.time()
        self._repository.update(tenant)
        self._audit.record(
            action="tenant.deleted",
            tenant_id=tenant_id,
            resource=f"tenant:{tenant_id}",
            outcome="success",
        )
        self._logger.log_event("deleted", tenant_id=tenant_id)
        return True

    def suspend(self, tenant_id: str) -> Tenant:
        tenant = self.get(tenant_id)
        if tenant.is_deleted:
            raise TenantDeletedError(tenant_id)
        tenant.status = TenantStatus.SUSPENDED
        tenant.updated_at = time.time()
        self._repository.update(tenant)
        self._audit.record(
            action="tenant.suspended",
            tenant_id=tenant_id,
            resource=f"tenant:{tenant_id}",
            outcome="success",
        )
        self._logger.log_event("suspended", tenant_id=tenant_id)
        return tenant

    def activate(self, tenant_id: str) -> Tenant:
        tenant = self.get(tenant_id)
        if tenant.is_deleted:
            raise TenantDeletedError(tenant_id)
        tenant.status = TenantStatus.ACTIVE
        tenant.updated_at = time.time()
        self._repository.update(tenant)
        self._audit.record(
            action="tenant.activated",
            tenant_id=tenant_id,
            resource=f"tenant:{tenant_id}",
            outcome="success",
        )
        self._logger.log_event("activated", tenant_id=tenant_id)
        return tenant

    def get(self, tenant_id: str) -> Tenant:
        return self._repository.get(tenant_id)

    def get_active(self, tenant_id: str) -> Tenant:
        tenant = self.get(tenant_id)
        if tenant.is_deleted:
            raise TenantDeletedError(tenant_id)
        if tenant.is_suspended and self._config.enforce_active:
            raise TenantSuspendedError(tenant_id)
        return tenant

    def list(
        self,
        status: TenantStatus | str | None = None,
        plan: str | None = None,
        include_deleted: bool = False,
    ) -> list[Tenant]:
        tenants = self._repository.list()
        if not include_deleted:
            tenants = [t for t in tenants if not t.is_deleted]
        if status is not None:
            status_value = status.value if isinstance(status, TenantStatus) else status
            tenants = [t for t in tenants if t.status.value == status_value]
        if plan is not None:
            tenants = [t for t in tenants if t.plan == plan]
        return sorted(tenants, key=lambda t: t.created_at)

    def count(self, status: TenantStatus | str | None = None) -> int:
        return len(self.list(status=status))

    def set_config(self, tenant_id: str, section: str, values: dict[str, Any]) -> Tenant:
        if section not in CONFIG_SECTIONS:
            raise ValueError(f"Unknown tenant config section {section!r}")
        tenant = self.get(tenant_id)
        tenant.set_config(section, values)
        self._repository.update(tenant)
        return tenant

    async def create_async(self, name: str, **kwargs: Any) -> Tenant:
        return self.create(name, **kwargs)

    async def update_async(self, tenant_id: str, **fields: Any) -> Tenant:
        return self.update(tenant_id, **fields)

    async def delete_async(self, tenant_id: str) -> bool:
        return self.delete(tenant_id)

    async def suspend_async(self, tenant_id: str) -> Tenant:
        return self.suspend(tenant_id)

    async def activate_async(self, tenant_id: str) -> Tenant:
        return self.activate(tenant_id)

    async def get_async(self, tenant_id: str) -> Tenant:
        return self.get(tenant_id)

    async def list_async(self, **kwargs: Any) -> list[Tenant]:
        return self.list(**kwargs)


def create_tenant_manager(
    repository: TenantRepository | None = None,
    config: TenancyConfig | None = None,
    logger: TenancyLogger | None = None,
    metrics: TenancyMetricsTracker | None = None,
    audit: AuditLogger | None = None,
) -> TenantManager:
    return TenantManager(
        repository=repository,
        config=config,
        logger=logger,
        metrics=metrics,
        audit=audit,
    )
