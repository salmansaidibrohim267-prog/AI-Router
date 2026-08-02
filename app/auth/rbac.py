from __future__ import annotations

from typing import Any, Iterable

from .exceptions import PermissionDeniedError
from .models import User

DEFAULT_ROLES: dict[str, set[str]] = {
    "admin": {"*"},
    "operator": {"read:*", "write:*", "manage:keys", "manage:sa", "manage:sessions"},
    "viewer": {"read:*"},
    "billing": {"read:*", "billing:manage"},
}

# Explicit denies take precedence: {"role": {"permission": ...}} never needed,
# deny list is global per tenant via TenantPolicy.deny_permissions.


class Principal:
    def __init__(
        self,
        user_id: str,
        tenant_id: str,
        roles: Iterable[str] = (),
        scopes: Iterable[str] = (),
        method: str = "token",
        username: str = "",
        service: bool = False,
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.roles = list(roles)
        self.scopes = list(scopes)
        self.method = method
        self.username = username
        self.service = service

    @classmethod
    def from_user(cls, user: User, method: str = "token") -> Principal:
        return cls(
            user_id=user.id,
            tenant_id=user.tenant_id,
            roles=user.roles,
            method=method,
            username=user.username,
        )

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "roles": list(self.roles),
            "scopes": list(self.scopes),
            "method": self.method,
            "username": self.username,
            "service": self.service,
        }


class PermissionPolicy:
    def __init__(
        self,
        roles: dict[str, set[str]] | None = None,
        deny_permissions: set[str] | None = None,
    ):
        self._roles = {k: set(v) for k, v in (roles or DEFAULT_ROLES).items()}
        self._deny = set(deny_permissions or ())

    def register_role(self, name: str, permissions: Iterable[str]) -> None:
        self._roles[name] = set(permissions)

    def permissions_for(self, roles: Iterable[str]) -> set[str]:
        merged: set[str] = set()
        for role in roles:
            merged |= self._roles.get(role, set())
        return merged

    def check(self, principal: Principal, permission: str, tenant_id: str | None = None) -> bool:
        if principal.tenant_id and tenant_id and principal.tenant_id != tenant_id:
            return False
        if permission in self._deny:
            return False
        permissions = self.permissions_for(principal.roles)
        if "*" in permissions:
            return True
        if permission in permissions:
            return True
        namespace = permission.split(":", 1)[0]
        return f"{namespace}:*" in permissions

    def enforce(self, principal: Principal, permission: str, tenant_id: str | None = None) -> None:
        if not self.check(principal, permission, tenant_id):
            raise PermissionDeniedError(permission, principal.user_id)

    def scopes_allow(self, principal: Principal, permission: str) -> bool:
        if "*" in principal.scopes:
            return True
        return permission in principal.scopes
