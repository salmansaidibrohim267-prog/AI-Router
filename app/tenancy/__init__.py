from __future__ import annotations

from typing import Any

from .audit import AuditEvent, AuditLogger
from .config import TenancyConfig
from .config_service import (
    DEFAULT_TENANT_CONFIG,
    TenantConfigService,
)
from .context import (
    TenantContextManager,
    get_current_tenant,
    get_tenant_context_manager,
    require_current_tenant,
    set_current_tenant,
)
from .exceptions import (
    TenancyError,
    TenantAlreadyExistsError,
    TenantContextMissingError,
    TenantDeletedError,
    TenantIsolationError,
    TenantLimitError,
    TenantNotFoundError,
    TenantResolutionError,
    TenantSuspendedError,
)
from .isolation import TenantIsolation
from .logging import TenancyLogger
from .manager import TenantManager, create_tenant_manager
from .middleware import TenantMiddleware, create_tenant_middleware
from .models import (
    CONFIG_SECTIONS,
    Tenant,
    TenantContext,
    TenantLimits,
    TenantStatus,
)
from .repository import (
    InMemoryTenantRepository,
    TenantRepository,
)
from .resolver import (
    APIKeyStrategy,
    CustomDomainStrategy,
    HeaderStrategy,
    JWTStrategy,
    SubdomainStrategy,
    TenantResolutionStrategy,
    TenantResolver,
    create_tenant_resolver,
    decode_jwt_claims,
)
from .statistics import TenancyMetricsTracker

__all__ = [
    "TenancyConfig",
    "TenancyLogger",
    "TenancyMetricsTracker",
    "TenancyError",
    "TenantNotFoundError",
    "TenantAlreadyExistsError",
    "TenantSuspendedError",
    "TenantDeletedError",
    "TenantResolutionError",
    "TenantContextMissingError",
    "TenantIsolationError",
    "TenantLimitError",
    "Tenant",
    "TenantStatus",
    "TenantLimits",
    "TenantContext",
    "CONFIG_SECTIONS",
    "TenantRepository",
    "InMemoryTenantRepository",
    "TenantManager",
    "TenantResolver",
    "TenantResolutionStrategy",
    "HeaderStrategy",
    "JWTStrategy",
    "APIKeyStrategy",
    "SubdomainStrategy",
    "CustomDomainStrategy",
    "decode_jwt_claims",
    "TenantContextManager",
    "TenantMiddleware",
    "TenantIsolation",
    "AuditLogger",
    "AuditEvent",
    "TenantConfigService",
    "DEFAULT_TENANT_CONFIG",
    "get_current_tenant",
    "get_tenant_context_manager",
    "require_current_tenant",
    "set_current_tenant",
    "create_tenant_manager",
    "create_tenant_resolver",
    "create_tenant_middleware",
    "create_tenant_context",
    "create_tenant_config_service",
]


def create_tenant_context(
    tenant_id: str,
    tenant_name: str = "",
    status: str = "active",
    user_id: str = "",
    auth_method: str = "explicit",
    resolved_by: str = "explicit",
    attributes: dict[str, Any] | None = None,
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        status=status,
        user_id=user_id,
        auth_method=auth_method,
        resolved_by=resolved_by,
        attributes=attributes or {},
    )


def create_tenant_config_service(
    manager: TenantManager,
    defaults: dict[str, dict[str, Any]] | None = None,
    config: TenancyConfig | None = None,
) -> TenantConfigService:
    return TenantConfigService(manager=manager, defaults=defaults, config=config)
