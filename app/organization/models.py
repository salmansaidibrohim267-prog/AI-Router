from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def make_slug(name: str, max_length: int = 64) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug[:max_length] or "item").rstrip("-")


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class OrganizationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


class WorkspaceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MemberRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class MemberStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INVITED = "invited"


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass
class Organization:
    id: str
    tenant_id: str
    name: str
    slug: str
    owner_user_id: str
    description: str = ""
    plan: str = "free"
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_active(self) -> bool:
        return self.status == OrganizationStatus.ACTIVE

    @property
    def is_archived(self) -> bool:
        return self.status == OrganizationStatus.ARCHIVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "slug": self.slug,
            "owner_user_id": self.owner_user_id,
            "description": self.description,
            "plan": self.plan,
            "status": self.status.value,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Workspace:
    id: str
    organization_id: str
    tenant_id: str
    name: str
    slug: str
    owner_user_id: str
    description: str = ""
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_active(self) -> bool:
        return self.status == WorkspaceStatus.ACTIVE

    @property
    def is_archived(self) -> bool:
        return self.status == WorkspaceStatus.ARCHIVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "slug": self.slug,
            "owner_user_id": self.owner_user_id,
            "description": self.description,
            "status": self.status.value,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Team:
    id: str
    organization_id: str
    tenant_id: str
    name: str
    description: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Member:
    id: str
    organization_id: str
    tenant_id: str
    user_id: str
    role: MemberRole = MemberRole.MEMBER
    status: MemberStatus = MemberStatus.ACTIVE
    team_ids: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "role": self.role.value,
            "status": self.status.value,
            "team_ids": list(self.team_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Project:
    id: str
    workspace_id: str
    organization_id: str
    tenant_id: str
    name: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "organization_id": self.organization_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Invitation:
    id: str
    organization_id: str
    tenant_id: str
    email: str
    role: MemberRole
    invited_by: str
    token: str
    status: InvitationStatus = InvitationStatus.PENDING
    expires_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    accepted_at: float = 0.0
    accepted_by: str = ""

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at) and time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "role": self.role.value,
            "invited_by": self.invited_by,
            "status": self.status.value,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "accepted_at": self.accepted_at,
            "accepted_by": self.accepted_by,
        }
