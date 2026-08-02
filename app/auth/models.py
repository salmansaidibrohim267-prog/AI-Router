from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LOCKED = "locked"
    DISABLED = "disabled"


@dataclass
class User:
    id: str
    username: str
    email: str = ""
    password_hash: str = ""
    status: UserStatus = UserStatus.ACTIVE
    roles: list[str] = field(default_factory=list)
    tenant_id: str = ""
    mfa_secret: str = ""
    failed_attempts: int = 0
    locked_until: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_locked(self) -> bool:
        if self.status == UserStatus.LOCKED:
            return time.time() < self.locked_until
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "status": self.status.value,
            "roles": list(self.roles),
            "tenant_id": self.tenant_id,
            "failed_attempts": self.failed_attempts,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ProviderUser:
    id: str
    username: str
    email: str = ""
    display_name: str = ""
    roles: list[str] = field(default_factory=list)
    tenant_id: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    id: str
    user_id: str
    tenant_id: str = ""
    device: str = "default"
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    expires_at: float = 0.0
    refresh_jti: str = ""
    revoked: bool = False

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at) and time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "device": self.device,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
        }


@dataclass
class TokenClaims:
    sub: str
    tenant_id: str = ""
    roles: list[str] = field(default_factory=list)
    token_type: str = "access"
    jti: str = ""
    session_id: str = ""
    iat: float = 0.0
    exp: float = 0.0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TokenClaims:
        return cls(
            sub=str(payload.get("sub", "")),
            tenant_id=str(payload.get("tenant_id", "")),
            roles=list(payload.get("roles", [])),
            token_type=str(payload.get("type", "access")),
            jti=str(payload.get("jti", "")),
            session_id=str(payload.get("sid", "")),
            iat=float(payload.get("iat", 0)),
            exp=float(payload.get("exp", 0)),
        )


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    access_jti: str
    refresh_jti: str
    expires_in: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": "bearer",
            "expires_in": self.expires_in,
        }


@dataclass
class APIKey:
    id: str
    tenant_id: str
    name: str
    key_prefix: str
    key_hash: str
    scopes: list[str] = field(default_factory=list)
    user_id: str = ""
    expires_at: float = 0.0
    revoked: bool = False
    usage_count: int = 0
    last_used_at: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at) and time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "scopes": list(self.scopes),
            "user_id": self.user_id,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at,
            "created_at": self.created_at,
        }


@dataclass
class ServiceAccount:
    id: str
    tenant_id: str
    name: str
    token_hash: str
    scopes: list[str] = field(default_factory=list)
    description: str = ""
    expires_at: float = 0.0
    revoked: bool = False
    usage_count: int = 0
    last_used_at: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at) and time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "token_hash": self.token_hash,
            "scopes": list(self.scopes),
            "description": self.description,
            "expires_at": self.expires_at,
            "revoked": self.revoked,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at,
            "created_at": self.created_at,
        }


@dataclass
class AuthResult:
    user: User | None
    token_pair: TokenPair | None = None
    session: Session | None = None
    mfa_required: bool = False
    method: str = "local"
    principal: Any = None
    scopes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user": self.user.to_dict() if self.user else None,
            "token_pair": self.token_pair.to_dict() if self.token_pair else None,
            "session": self.session.to_dict() if self.session else None,
            "mfa_required": self.mfa_required,
            "method": self.method,
            "scopes": list(self.scopes),
        }
