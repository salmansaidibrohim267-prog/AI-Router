from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .exceptions import TenantContextMissingError, TenantNotFoundError


class TenantStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


CONFIG_SECTIONS = ("llm", "embeddings", "reranker", "prompts", "mcp")


@dataclass
class TenantLimits:
    max_requests_per_min: int = 1000
    max_tokens_per_day: int = 1_000_000
    max_storage_bytes: int = 1_000_000_000
    max_memory_items: int = 10_000
    max_kb_documents: int = 10_000
    max_seats: int = 5

    def to_dict(self) -> dict[str, int]:
        return {
            "max_requests_per_min": self.max_requests_per_min,
            "max_tokens_per_day": self.max_tokens_per_day,
            "max_storage_bytes": self.max_storage_bytes,
            "max_memory_items": self.max_memory_items,
            "max_kb_documents": self.max_kb_documents,
            "max_seats": self.max_seats,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TenantLimits:
        return cls(
            max_requests_per_min=int(payload.get("max_requests_per_min", 1000)),
            max_tokens_per_day=int(payload.get("max_tokens_per_day", 1_000_000)),
            max_storage_bytes=int(payload.get("max_storage_bytes", 1_000_000_000)),
            max_memory_items=int(payload.get("max_memory_items", 10_000)),
            max_kb_documents=int(payload.get("max_kb_documents", 10_000)),
            max_seats=int(payload.get("max_seats", 5)),
        )


@dataclass
class Tenant:
    id: str
    name: str = ""
    status: TenantStatus = TenantStatus.ACTIVE
    plan: str = "free"
    limits: TenantLimits = field(default_factory=TenantLimits)
    config: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_active(self) -> bool:
        return self.status == TenantStatus.ACTIVE

    @property
    def is_suspended(self) -> bool:
        return self.status == TenantStatus.SUSPENDED

    @property
    def is_deleted(self) -> bool:
        return self.status == TenantStatus.DELETED

    def config_section(self, section: str) -> dict[str, Any]:
        return self.config.get(section, {})

    def set_config(self, section: str, values: dict[str, Any]) -> None:
        self.config.setdefault(section, {}).update(values)
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "plan": self.plan,
            "limits": self.limits.to_dict(),
            "config": self.config,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Tenant:
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            status=TenantStatus(payload.get("status", "active")),
            plan=str(payload.get("plan", "free")),
            limits=TenantLimits.from_dict(payload.get("limits", {})),
            config=dict(payload.get("config", {})),
            metadata=dict(payload.get("metadata", {})),
            created_at=float(payload.get("created_at", time.time())),
            updated_at=float(payload.get("updated_at", time.time())),
        )


@dataclass
class TenantContext:
    tenant_id: str
    tenant_name: str = ""
    status: str = "active"
    user_id: str = ""
    auth_method: str = "none"
    resolved_by: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_isolated(self) -> bool:
        return bool(self.tenant_id)

    def require_tenant(self) -> TenantContext:
        if not self.tenant_id:
            raise TenantContextMissingError()
        return self

    def merged(self, tenant: Any | None) -> TenantContext:
        if tenant is None:
            return self
        return TenantContext(
            tenant_id=tenant.id,
            tenant_name=tenant.name,
            status=tenant.status.value,
            user_id=self.user_id,
            auth_method=self.auth_method,
            resolved_by=self.resolved_by,
            attributes=self.attributes,
        )

    def with_attribute(self, key: str, value: Any) -> TenantContext:
        self.attributes[key] = value
        return self

    @classmethod
    def anonymous(cls, tenant_id: str = "default") -> TenantContext:
        return cls(
            tenant_id=tenant_id,
            tenant_name=tenant_id,
            status="active",
            auth_method="anonymous",
            resolved_by="anonymous",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "status": self.status,
            "user_id": self.user_id,
            "auth_method": self.auth_method,
            "resolved_by": self.resolved_by,
            "attributes": self.attributes,
        }


def tenant_not_found(tenant_id: str) -> TenantNotFoundError:
    return TenantNotFoundError(tenant_id)
