from __future__ import annotations

import time
import uuid
from typing import Any

from app.auth.rbac import Principal

from .access import AccessGuard
from .config import OrganizationConfig
from .exceptions import (
    OrganizationAlreadyExistsError,
    OrganizationArchivedError,
    OrganizationLimitError,
    OrganizationNotFoundError,
    OwnershipTransferError,
)
from .logging import OrganizationLogger
from .members import MemberManager
from .models import (
    MemberRole,
    Organization,
    OrganizationStatus,
    make_slug,
)
from .repository import (
    InvitationRepository,
    MemberRepository,
    OrganizationRepository,
    ProjectRepository,
    TeamRepository,
    WorkspaceRepository,
)
from .statistics import OrganizationMetricsTracker


class OrganizationManager:
    def __init__(
        self,
        organizations: OrganizationRepository | None = None,
        workspaces: WorkspaceRepository | None = None,
        teams: TeamRepository | None = None,
        members: MemberManager | None = None,
        member_repository: MemberRepository | None = None,
        projects: ProjectRepository | None = None,
        invitations: InvitationRepository | None = None,
        guard: AccessGuard | None = None,
        config: OrganizationConfig | None = None,
        logger: OrganizationLogger | None = None,
        metrics: OrganizationMetricsTracker | None = None,
        audit: Any | None = None,
    ):
        self._organizations = organizations or OrganizationRepository()
        self._workspaces = workspaces or WorkspaceRepository()
        self._teams = teams or TeamRepository()
        self._members = members or MemberManager(
            members=member_repository,
            organizations=self._organizations,
            guard=guard,
            config=config,
            logger=logger,
            metrics=metrics,
            audit=audit,
        )
        self._projects = projects or ProjectRepository()
        self._invitations = invitations or InvitationRepository()
        self._guard = guard or AccessGuard()
        self._config = config or OrganizationConfig()
        self._logger = logger or OrganizationLogger()
        self._metrics = metrics or OrganizationMetricsTracker(self._config)
        self._audit = audit

    @property
    def repository(self) -> OrganizationRepository:
        return self._organizations

    @property
    def members(self) -> MemberManager:
        return self._members

    def _audit_event(self, action: str, tenant_id: str, actor: str, **details: Any) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(action=action, tenant_id=tenant_id, actor=actor, resource="organizations", details=details)
        except Exception:
            pass

    def create(
        self,
        tenant_id: str,
        name: str,
        owner_user_id: str,
        description: str = "",
        slug: str | None = None,
        plan: str = "free",
        metadata: dict[str, Any] | None = None,
    ) -> Organization:
        if len(name) > self._config.org_name_max_length:
            raise ValueError(f"Organization name exceeds {self._config.org_name_max_length} characters")
        if self._organizations.count_for_tenant(tenant_id) >= self._config.max_organizations_per_tenant:
            raise OrganizationLimitError(tenant_id, self._config.max_organizations_per_tenant)
        slug = slug or make_slug(name, self._config.org_slug_max_length)
        if self._organizations.get_by_slug(slug, tenant_id) is not None:
            raise OrganizationAlreadyExistsError(slug)
        organization = Organization(
            id=f"org_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            owner_user_id=owner_user_id,
            description=description,
            plan=plan,
            metadata=metadata or {},
        )
        self._organizations.create(organization)
        self._members.add_member(
            organization_id=organization.id,
            user_id=owner_user_id,
            tenant_id=tenant_id,
            role="owner",
        )
        self._metrics.record("organization_created", organization.id)
        self._logger.log_event("created", tenant_id=tenant_id, organization_id=organization.id, name=name)
        self._audit_event("org.created", tenant_id, owner_user_id, organization_id=organization.id, name=name)
        return organization

    def update(self, tenant_id: str, organization_id: str, **fields: Any) -> Organization:
        organization = self.get(tenant_id, organization_id)
        allowed = {"name", "description", "slug", "plan", "metadata"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unknown organization field {key!r}")
            if key == "slug":
                existing = self._organizations.get_by_slug(value, tenant_id)
                if existing is not None and existing.id != organization_id:
                    raise OrganizationAlreadyExistsError(value)
            setattr(organization, key, value)
        organization.updated_at = time.time()
        self._organizations.update(organization)
        self._audit_event("org.updated", tenant_id, "", organization_id=organization_id)
        return organization

    def delete(self, tenant_id: str, organization_id: str) -> bool:
        organization = self.get(tenant_id, organization_id)
        for workspace in self._workspaces.list_for_organization(organization_id):
            for project in self._projects.list_for_workspace(workspace.id):
                self._projects.delete(project.id)
            self._workspaces.delete(workspace.id)
        for team in self._teams.list_for_organization(organization_id):
            self._teams.delete(team.id)
        self._members.repository.delete_for_organization(organization_id)
        for invitation in self._invitations.list_for_organization(organization_id):
            self._invitations.delete(invitation.id)
        deleted = self._organizations.delete(organization_id)
        self._metrics.record("organization_deleted", organization_id)
        self._logger.log_event("deleted", tenant_id=tenant_id, organization_id=organization_id)
        self._audit_event("org.deleted", tenant_id, "", organization_id=organization_id)
        return deleted

    def archive(self, tenant_id: str, organization_id: str) -> Organization:
        organization = self.get(tenant_id, organization_id)
        if organization.is_archived:
            return organization
        organization.status = OrganizationStatus.ARCHIVED
        organization.updated_at = time.time()
        self._organizations.update(organization)
        self._metrics.record("organization_archived", organization_id)
        self._audit_event("org.archived", tenant_id, "", organization_id=organization_id)
        return organization

    def restore(self, tenant_id: str, organization_id: str) -> Organization:
        organization = self.get(tenant_id, organization_id)
        if organization.is_active:
            return organization
        organization.status = OrganizationStatus.ACTIVE
        organization.updated_at = time.time()
        self._organizations.update(organization)
        self._metrics.record("organization_restored", organization_id)
        self._audit_event("org.restored", tenant_id, "", organization_id=organization_id)
        return organization

    def get(self, tenant_id: str, organization_id: str) -> Organization:
        organization = self._organizations.get(organization_id)
        if organization is None:
            raise OrganizationNotFoundError(organization_id)
        if organization.tenant_id != tenant_id:
            raise OrganizationNotFoundError(organization_id)
        return organization

    def get_by_slug(self, tenant_id: str, slug: str) -> Organization:
        organization = self._organizations.get_by_slug(slug, tenant_id)
        if organization is None:
            raise OrganizationNotFoundError(slug)
        return organization

    def list(self, tenant_id: str, status: str = "") -> list[Organization]:
        organizations = self._organizations.list_for_tenant(tenant_id)
        if status:
            organizations = [o for o in organizations if o.status.value == status]
        return organizations

    def transfer_ownership(
        self,
        principal: Principal,
        organization_id: str,
        new_owner_user_id: str,
        tenant_id: str = "",
    ) -> Organization:
        organization = self.get(tenant_id, organization_id)
        if new_owner_user_id == organization.owner_user_id:
            return organization
        actor_member = self._members.repository.get_by_user(organization_id, principal.user_id)
        if actor_member is None:
            raise OwnershipTransferError(f"User {principal.user_id!r} is not a member of the organization")
        self._guard.require(principal, actor_member, "org:transfer")
        new_owner_member = self._members.repository.get_by_user(organization_id, new_owner_user_id)
        if new_owner_member is None:
            raise OwnershipTransferError(f"User {new_owner_user_id!r} is not a member of the organization")
        if new_owner_member.role == MemberRole.OWNER:
            return organization
        old_owner = self._members.repository.get_by_user(organization_id, organization.owner_user_id)
        if old_owner is not None:
            old_owner.role = MemberRole.ADMIN
            self._members.repository.update(old_owner)
        new_owner_member.role = MemberRole.OWNER
        self._members.repository.update(new_owner_member)
        organization.owner_user_id = new_owner_user_id
        organization.updated_at = time.time()
        self._organizations.update(organization)
        self._metrics.record("organization_transferred", organization_id)
        self._logger.log_event("ownership_transferred", tenant_id=tenant_id, organization_id=organization_id, new_owner=new_owner_user_id)
        self._audit_event("org.transferred", tenant_id, principal.user_id, organization_id=organization_id, new_owner=new_owner_user_id)
        return organization

    async def create_async(self, tenant_id: str, name: str, owner_user_id: str, description: str = "", slug: str | None = None, plan: str = "free", metadata: dict[str, Any] | None = None) -> Organization:
        return self.create(tenant_id, name, owner_user_id, description, slug, plan, metadata)

    async def update_async(self, tenant_id: str, organization_id: str, **fields: Any) -> Organization:
        return self.update(tenant_id, organization_id, **fields)

    async def delete_async(self, tenant_id: str, organization_id: str) -> bool:
        return self.delete(tenant_id, organization_id)

    async def archive_async(self, tenant_id: str, organization_id: str) -> Organization:
        return self.archive(tenant_id, organization_id)

    async def restore_async(self, tenant_id: str, organization_id: str) -> Organization:
        return self.restore(tenant_id, organization_id)

    async def list_async(self, tenant_id: str, status: str = "") -> list[Organization]:
        return self.list(tenant_id, status)

    async def transfer_ownership_async(self, principal: Principal, organization_id: str, new_owner_user_id: str, tenant_id: str = "") -> Organization:
        return self.transfer_ownership(principal, organization_id, new_owner_user_id, tenant_id)


def create_organization_manager(
    organizations: OrganizationRepository | None = None,
    workspaces: WorkspaceRepository | None = None,
    teams: TeamRepository | None = None,
    members: MemberManager | None = None,
    member_repository: MemberRepository | None = None,
    projects: ProjectRepository | None = None,
    invitations: InvitationRepository | None = None,
    guard: AccessGuard | None = None,
    config: OrganizationConfig | None = None,
    logger: OrganizationLogger | None = None,
    metrics: OrganizationMetricsTracker | None = None,
    audit: Any | None = None,
) -> OrganizationManager:
    return OrganizationManager(
        organizations=organizations,
        workspaces=workspaces,
        teams=teams,
        members=members,
        member_repository=member_repository,
        projects=projects,
        invitations=invitations,
        guard=guard,
        config=config,
        logger=logger,
        metrics=metrics,
        audit=audit,
    )
