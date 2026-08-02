from __future__ import annotations

from typing import Iterable

from app.auth.exceptions import PermissionDeniedError
from app.auth.rbac import PermissionPolicy, Principal

from .exceptions import IsolationError, MemberRoleError, OrganizationNotFoundError
from .models import Member, MemberRole, Organization

ORG_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {"*"},
    "admin": {
        "org:view",
        "org:update",
        "org:manage_members",
        "org:manage_teams",
        "org:manage_invitations",
        "org:manage_workspaces",
        "workspace:create",
        "workspace:view",
        "workspace:update",
        "workspace:archive",
        "workspace:delete",
        "workspace:clone",
        "workspace:transfer",
        "project:create",
        "project:view",
        "project:update",
        "project:delete",
        "team:create",
        "team:update",
        "team:delete",
        "team:view",
    },
    "member": {
        "org:view",
        "workspace:view",
        "workspace:create_project",
        "project:create",
        "project:view",
        "project:update",
        "team:view",
    },
    "viewer": {"org:view", "workspace:view", "project:view", "team:view"},
}

VALID_MEMBER_ROLES = {role.value for role in MemberRole}


def validate_member_role(role: str) -> str:
    if role not in VALID_MEMBER_ROLES:
        raise MemberRoleError(f"Invalid member role {role!r}")
    return role


class AccessGuard:
    def __init__(
        self,
        policy: PermissionPolicy | None = None,
        role_permissions: dict[str, set[str]] | None = None,
    ):
        self._policy = policy or PermissionPolicy()
        self._role_permissions = {
            k: set(v) for k, v in (role_permissions or ORG_ROLE_PERMISSIONS).items()
        }

    @property
    def policy(self) -> PermissionPolicy:
        return self._policy

    def register_role_permissions(self, role: str, permissions: Iterable[str]) -> None:
        self._role_permissions[role] = set(permissions)

    def permissions_for_role(self, role: str) -> set[str]:
        return set(self._role_permissions.get(role, set()))

    def member_allowed(self, member: Member, permission: str) -> bool:
        if member.status.value != "active":
            return False
        permissions = self.permissions_for_role(member.role.value)
        if "*" in permissions:
            return True
        if permission in permissions:
            return True
        namespace = permission.split(":", 1)[0]
        return f"{namespace}:*" in permissions

    def require_member(self, member: Member, permission: str) -> None:
        if not self.member_allowed(member, permission):
            raise PermissionDeniedError(permission, member.user_id)

    def verify_principal(self, principal: Principal, member: Member) -> None:
        if principal.tenant_id and member.tenant_id and principal.tenant_id != member.tenant_id:
            raise IsolationError(
                f"Principal tenant {principal.tenant_id!r} does not match member tenant {member.tenant_id!r}"
            )
        if principal.user_id != member.user_id:
            raise PermissionDeniedError("org:access", principal.user_id)

    def require(self, principal: Principal, member: Member, permission: str) -> None:
        self.verify_principal(principal, member)
        self.require_member(member, permission)

    @staticmethod
    def assert_tenant(entity_tenant_id: str, tenant_id: str) -> None:
        if entity_tenant_id and tenant_id and entity_tenant_id != tenant_id:
            raise IsolationError(
                f"Entity tenant {entity_tenant_id!r} does not match expected tenant {tenant_id!r}"
            )

    def require_org_owner(self, organization: Organization, user_id: str) -> None:
        if organization.owner_user_id != user_id:
            raise PermissionDeniedError("org:ownership", user_id)


def create_access_guard(
    policy: PermissionPolicy | None = None,
    role_permissions: dict[str, set[str]] | None = None,
) -> AccessGuard:
    return AccessGuard(policy=policy, role_permissions=role_permissions)
