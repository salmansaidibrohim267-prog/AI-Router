from __future__ import annotations

import time
import uuid
from typing import Any

from app.auth.rbac import Principal

from .access import AccessGuard, validate_member_role
from .config import OrganizationConfig
from .exceptions import (
    MemberAlreadyExistsError,
    MemberLimitError,
    MemberNotFoundError,
    MemberRoleError,
    OrganizationArchivedError,
    OrganizationNotFoundError,
)
from .logging import OrganizationLogger
from .models import Member, MemberRole, Organization
from .repository import MemberRepository, OrganizationRepository
from .statistics import OrganizationMetricsTracker


class MemberManager:
    def __init__(
        self,
        members: MemberRepository | None = None,
        organizations: OrganizationRepository | None = None,
        guard: AccessGuard | None = None,
        config: OrganizationConfig | None = None,
        logger: OrganizationLogger | None = None,
        metrics: OrganizationMetricsTracker | None = None,
        audit: Any | None = None,
    ):
        self._members = members or MemberRepository()
        self._organizations = organizations or OrganizationRepository()
        self._guard = guard or AccessGuard()
        self._config = config or OrganizationConfig()
        self._logger = logger or OrganizationLogger()
        self._metrics = metrics or OrganizationMetricsTracker(self._config)
        self._audit = audit

    @property
    def repository(self) -> MemberRepository:
        return self._members

    def _audit_event(self, action: str, tenant_id: str, actor: str, **details: Any) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(action=action, tenant_id=tenant_id, actor=actor, resource="members", details=details)
        except Exception:
            pass

    def _require_org(self, organization: Organization, tenant_id: str) -> None:
        self._guard.assert_tenant(organization.tenant_id, tenant_id)
        if not organization.is_active:
            raise OrganizationArchivedError(organization.id)

    def _get_org(self, organization_id: str, tenant_id: str) -> Organization:
        org = self._organizations.get(organization_id)
        if org is None:
            raise OrganizationNotFoundError(organization_id)
        self._guard.assert_tenant(org.tenant_id, tenant_id)
        return org

    def add_member(
        self,
        organization_id: str,
        user_id: str,
        tenant_id: str = "",
        role: str = "member",
        actor: Principal | None = None,
    ) -> Member:
        organization = self._get_org(organization_id, tenant_id)
        self._require_org(organization, tenant_id)
        role = validate_member_role(role)
        if role == "owner" and actor is not None:
            raise MemberRoleError("Owner role can only be assigned via transfer of ownership")
        if self._members.get_by_user(organization_id, user_id) is not None:
            raise MemberAlreadyExistsError(organization_id, user_id)
        if self._members.count_for_organization(organization_id) >= self._config.max_members_per_org:
            raise MemberLimitError(organization_id, self._config.max_members_per_org)
        if actor is not None:
            actor_member = self._members.get_by_user(organization_id, actor.user_id)
            if actor_member is None:
                raise MemberNotFoundError(organization_id, actor.user_id)
            self._guard.require(actor, actor_member, "org:manage_members")
        member = Member(
            id=f"mem_{uuid.uuid4().hex[:16]}",
            organization_id=organization_id,
            tenant_id=organization.tenant_id,
            user_id=user_id,
            role=MemberRole(role),
        )
        self._members.create(member)
        self._metrics.record("member_added", organization_id)
        self._logger.log_event(
            "member_added",
            tenant_id=organization.tenant_id,
            organization_id=organization_id,
            user_id=user_id,
            role=role,
        )
        self._audit_event(
            "org.member_added", organization.tenant_id, actor.user_id if actor else user_id, user_id=user_id, role=role
        )  # noqa: E501
        return member

    def remove_member(
        self, organization_id: str, user_id: str, tenant_id: str = "", actor: Principal | None = None
    ) -> bool:
        organization = self._get_org(organization_id, tenant_id)
        member = self._members.get_by_user(organization_id, user_id)
        if member is None:
            raise MemberNotFoundError(organization_id, user_id)
        if member.role == MemberRole.OWNER:
            raise MemberRoleError("The organization owner cannot be removed")
        if actor is not None:
            actor_member = self._members.get_by_user(organization_id, actor.user_id)
            if actor_member is None:
                raise MemberNotFoundError(organization_id, actor.user_id)
            self._guard.require(actor, actor_member, "org:manage_members")
        deleted = self._members.delete(member.id)
        self._metrics.record("member_removed", organization_id)
        self._audit_event(
            "org.member_removed", organization.tenant_id, actor.user_id if actor else user_id, user_id=user_id
        )  # noqa: E501
        return deleted

    def set_role(
        self,
        organization_id: str,
        user_id: str,
        role: str,
        tenant_id: str = "",
        actor: Principal | None = None,
    ) -> Member:
        organization = self._get_org(organization_id, tenant_id)
        role = validate_member_role(role)
        member = self._members.get_by_user(organization_id, user_id)
        if member is None:
            raise MemberNotFoundError(organization_id, user_id)
        if member.role == MemberRole.OWNER:
            raise MemberRoleError("The organization owner role cannot be changed directly")
        if role == "owner":
            raise MemberRoleError("Owner role can only be assigned via transfer of ownership")
        if actor is not None:
            actor_member = self._members.get_by_user(organization_id, actor.user_id)
            if actor_member is None:
                raise MemberNotFoundError(organization_id, actor.user_id)
            self._guard.require(actor, actor_member, "org:manage_members")
        member.role = MemberRole(role)
        member.updated_at = time.time()
        self._members.update(member)
        self._metrics.record("member_role_changed", organization_id)
        self._audit_event(
            "org.member_role_changed",
            organization.tenant_id,
            actor.user_id if actor else user_id,
            user_id=user_id,
            role=role,
        )  # noqa: E501
        return member

    def get_member(self, organization_id: str, user_id: str, tenant_id: str = "") -> Member:
        _ = self._get_org(organization_id, tenant_id)
        member = self._members.get_by_user(organization_id, user_id)
        if member is None:
            raise MemberNotFoundError(organization_id, user_id)
        return member

    def is_member(self, organization_id: str, user_id: str) -> bool:
        return self._members.get_by_user(organization_id, user_id) is not None

    def list_members(self, organization_id: str, tenant_id: str = "") -> list[Member]:
        organization = self._get_org(organization_id, tenant_id)
        return self._members.list_for_organization(organization.id)

    def count(self, organization_id: str) -> int:
        return self._members.count_for_organization(organization_id)

    def require_permission(
        self, principal: Principal, organization_id: str, permission: str, tenant_id: str = ""
    ) -> Member:
        organization = self._get_org(organization_id, tenant_id)
        member = self._members.get_by_user(organization.id, principal.user_id)
        if member is None:
            raise MemberNotFoundError(organization.id, principal.user_id)
        self._guard.require(principal, member, permission)
        return member

    def has_permission(self, principal: Principal, organization_id: str, permission: str, tenant_id: str = "") -> bool:
        try:
            self.require_permission(principal, organization_id, permission, tenant_id)
            return True
        except (MemberNotFoundError, OrganizationNotFoundError):
            return False
        except Exception:
            return False

    async def add_member_async(
        self,
        organization_id: str,
        user_id: str,
        tenant_id: str = "",
        role: str = "member",
        actor: Principal | None = None,
    ) -> Member:  # noqa: E501
        return self.add_member(organization_id, user_id, tenant_id, role, actor)

    async def remove_member_async(
        self, organization_id: str, user_id: str, tenant_id: str = "", actor: Principal | None = None
    ) -> bool:  # noqa: E501
        return self.remove_member(organization_id, user_id, tenant_id, actor)

    async def set_role_async(
        self, organization_id: str, user_id: str, role: str, tenant_id: str = "", actor: Principal | None = None
    ) -> Member:  # noqa: E501
        return self.set_role(organization_id, user_id, role, tenant_id, actor)

    async def list_members_async(self, organization_id: str, tenant_id: str = "") -> list[Member]:
        return self.list_members(organization_id, tenant_id)


def create_member_manager(
    members: MemberRepository | None = None,
    organizations: OrganizationRepository | None = None,
    guard: AccessGuard | None = None,
    config: OrganizationConfig | None = None,
    logger: OrganizationLogger | None = None,
    metrics: OrganizationMetricsTracker | None = None,
    audit: Any | None = None,
) -> MemberManager:
    return MemberManager(
        members=members,
        organizations=organizations,
        guard=guard,
        config=config,
        logger=logger,
        metrics=metrics,
        audit=audit,
    )
