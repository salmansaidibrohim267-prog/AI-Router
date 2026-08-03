from __future__ import annotations

import time
import uuid
from typing import Any

from app.auth.rbac import Principal

from .config import OrganizationConfig
from .exceptions import (
    MemberNotFoundError,
    OrganizationArchivedError,
    OrganizationNotFoundError,
    WorkspaceAlreadyExistsError,
    WorkspaceLimitError,
    WorkspaceNotFoundError,
)
from .logging import OrganizationLogger
from .manager import OrganizationManager
from .members import MemberManager
from .models import Project, Workspace, WorkspaceStatus, make_slug
from .repository import ProjectRepository, WorkspaceRepository
from .statistics import OrganizationMetricsTracker


class WorkspaceManager:
    def __init__(
        self,
        workspaces: WorkspaceRepository | None = None,
        projects: ProjectRepository | None = None,
        organizations: OrganizationManager | None = None,
        members: MemberManager | None = None,
        config: OrganizationConfig | None = None,
        logger: OrganizationLogger | None = None,
        metrics: OrganizationMetricsTracker | None = None,
        audit: Any | None = None,
    ):
        self._workspaces = workspaces or WorkspaceRepository()
        self._projects = projects or ProjectRepository()
        self._organizations = organizations
        self._members = members
        self._config = config or OrganizationConfig()
        self._logger = logger or OrganizationLogger()
        self._metrics = metrics or OrganizationMetricsTracker(self._config)
        self._audit = audit

    @property
    def repository(self) -> WorkspaceRepository:
        return self._workspaces

    def _audit_event(self, action: str, tenant_id: str, actor: str, **details: Any) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(action=action, tenant_id=tenant_id, actor=actor, resource="workspaces", details=details)
        except Exception:
            pass

    def _get_org(self, organization_id: str, tenant_id: str) -> Any:
        if self._organizations is None:
            raise OrganizationNotFoundError(organization_id)
        try:
            return self._organizations.get(tenant_id, organization_id)
        except OrganizationNotFoundError:
            raise OrganizationNotFoundError(organization_id) from None

    def create(
        self,
        organization_id: str,
        name: str,
        owner_user_id: str,
        tenant_id: str = "",
        description: str = "",
        slug: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Workspace:
        org = self._get_org(organization_id, tenant_id)
        if not org.is_active:
            raise OrganizationArchivedError(organization_id)
        if len(name) > self._config.workspace_name_max_length:
            raise ValueError(f"Workspace name exceeds {self._config.workspace_name_max_length} characters")
        slug = slug or make_slug(name, self._config.workspace_slug_max_length)
        if self._workspaces.get_by_slug(slug, organization_id) is not None:
            raise WorkspaceAlreadyExistsError(slug)
        if self._workspaces.count_for_organization(organization_id) >= self._config.max_workspaces_per_org:
            raise WorkspaceLimitError(organization_id, self._config.max_workspaces_per_org)
        workspace = Workspace(
            id=f"ws_{uuid.uuid4().hex[:16]}",
            organization_id=organization_id,
            tenant_id=org.tenant_id,
            name=name,
            slug=slug,
            owner_user_id=owner_user_id,
            description=description,
            metadata=metadata or {},
        )
        self._workspaces.create(workspace)
        self._metrics.record("workspace_created", organization_id)
        self._logger.log_event(
            "workspace_created",
            tenant_id=org.tenant_id,
            organization_id=organization_id,
            workspace_id=workspace.id,
        )
        self._audit_event("org.workspace_created", org.tenant_id, owner_user_id, workspace_id=workspace.id, name=name)
        return workspace

    def update(self, organization_id: str, workspace_id: str, tenant_id: str = "", **fields: Any) -> Workspace:
        org = self._get_org(organization_id, tenant_id)
        workspace = self._workspaces.get(workspace_id)
        if workspace is None or workspace.organization_id != organization_id or workspace.tenant_id != tenant_id:
            raise WorkspaceNotFoundError(workspace_id)
        allowed = {"name", "description", "slug", "metadata"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unknown workspace field {key!r}")
            if key == "slug":
                if self._workspaces.get_by_slug(value, organization_id) is not None:
                    raise WorkspaceAlreadyExistsError(value)
            setattr(workspace, key, value)
        workspace.updated_at = time.time()
        self._workspaces.update(workspace)
        self._audit_event("org.workspace_updated", org.tenant_id, "", workspace_id=workspace_id)
        return workspace

    def delete(self, organization_id: str, workspace_id: str, tenant_id: str = "") -> bool:
        org = self._get_org(organization_id, tenant_id)
        workspace = self._workspaces.get(workspace_id)
        if workspace is None or workspace.organization_id != organization_id or workspace.tenant_id != tenant_id:
            raise WorkspaceNotFoundError(workspace_id)
        for project in self._projects.list_for_workspace(workspace_id):
            self._projects.delete(project.id)
        deleted = self._workspaces.delete(workspace_id)
        self._metrics.record("workspace_deleted", organization_id)
        self._audit_event("org.workspace_deleted", org.tenant_id, "", workspace_id=workspace_id)
        return deleted

    def archive(self, organization_id: str, workspace_id: str, tenant_id: str = "") -> Workspace:
        org = self._get_org(organization_id, tenant_id)
        workspace = self._workspaces.get(workspace_id)
        if workspace is None or workspace.organization_id != organization_id or workspace.tenant_id != tenant_id:
            raise WorkspaceNotFoundError(workspace_id)
        workspace.status = WorkspaceStatus.ARCHIVED
        workspace.updated_at = time.time()
        self._workspaces.update(workspace)
        self._metrics.record("workspace_archived", organization_id)
        self._audit_event("org.workspace_archived", org.tenant_id, "", workspace_id=workspace_id)
        return workspace

    def restore(self, organization_id: str, workspace_id: str, tenant_id: str = "") -> Workspace:
        _ = self._get_org(organization_id, tenant_id)
        workspace = self._workspaces.get(workspace_id)
        if workspace is None or workspace.organization_id != organization_id or workspace.tenant_id != tenant_id:
            raise WorkspaceNotFoundError(workspace_id)
        workspace.status = WorkspaceStatus.ACTIVE
        workspace.updated_at = time.time()
        self._workspaces.update(workspace)
        return workspace

    def clone(
        self,
        organization_id: str,
        workspace_id: str,
        tenant_id: str = "",
        name: str | None = None,
        include_projects: bool = True,
    ) -> Workspace:
        org = self._get_org(organization_id, tenant_id)
        workspace = self._workspaces.get(workspace_id)
        if workspace is None or workspace.organization_id != organization_id or workspace.tenant_id != tenant_id:
            raise WorkspaceNotFoundError(workspace_id)
        if not org.is_active:
            raise OrganizationArchivedError(organization_id)
        new_name = name or f"{workspace.name} (copy)"
        clone = self.create(
            organization_id=organization_id,
            name=new_name,
            owner_user_id=workspace.owner_user_id,
            tenant_id=tenant_id,
            description=workspace.description,
            metadata=dict(workspace.metadata),
        )
        if include_projects:
            for project in self._projects.list_for_workspace(workspace_id):
                self._projects.create(
                    Project(
                        id=f"proj_{uuid.uuid4().hex[:16]}",
                        workspace_id=clone.id,
                        organization_id=organization_id,
                        tenant_id=org.tenant_id,
                        name=project.name,
                        description=project.description,
                        metadata=dict(project.metadata),
                    )
                )
        self._metrics.record("workspace_cloned", organization_id)
        self._audit_event("org.workspace_cloned", org.tenant_id, "", source=workspace_id, target=clone.id)
        return clone

    def transfer(
        self,
        organization_id: str,
        workspace_id: str,
        new_owner_user_id: str,
        tenant_id: str = "",
        actor: Principal | None = None,
    ) -> Workspace:
        org = self._get_org(organization_id, tenant_id)
        workspace = self._workspaces.get(workspace_id)
        if workspace is None or workspace.organization_id != organization_id or workspace.tenant_id != tenant_id:
            raise WorkspaceNotFoundError(workspace_id)
        if self._members is not None and not self._members.is_member(organization_id, new_owner_user_id):
            raise MemberNotFoundError(organization_id, new_owner_user_id)
        if actor is not None and self._members is not None:
            self._members.require_permission(actor, organization_id, "workspace:transfer", tenant_id)
        workspace.owner_user_id = new_owner_user_id
        workspace.updated_at = time.time()
        self._workspaces.update(workspace)
        self._metrics.record("workspace_transferred", organization_id)
        self._audit_event(
            "org.workspace_transferred",
            org.tenant_id,
            actor.user_id if actor else "",
            workspace_id=workspace_id,
            new_owner=new_owner_user_id,
        )  # noqa: E501
        return workspace

    def get(self, organization_id: str, workspace_id: str, tenant_id: str = "") -> Workspace:
        self._get_org(organization_id, tenant_id)
        workspace = self._workspaces.get(workspace_id)
        if workspace is None or workspace.organization_id != organization_id or workspace.tenant_id != tenant_id:
            raise WorkspaceNotFoundError(workspace_id)
        return workspace

    def list(self, organization_id: str | None = None, tenant_id: str = "") -> list[Workspace]:
        if organization_id is not None:
            self._get_org(organization_id, tenant_id)
            return self._workspaces.list_for_organization(organization_id)
        return self._workspaces.list_for_tenant(tenant_id)

    async def create_async(
        self,
        organization_id: str,
        name: str,
        owner_user_id: str,
        tenant_id: str = "",
        description: str = "",
        slug: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Workspace:  # noqa: E501
        return self.create(organization_id, name, owner_user_id, tenant_id, description, slug, metadata)

    async def update_async(
        self, organization_id: str, workspace_id: str, tenant_id: str = "", **fields: Any
    ) -> Workspace:  # noqa: E501
        return self.update(organization_id, workspace_id, tenant_id, **fields)

    async def delete_async(self, organization_id: str, workspace_id: str, tenant_id: str = "") -> bool:
        return self.delete(organization_id, workspace_id, tenant_id)

    async def archive_async(self, organization_id: str, workspace_id: str, tenant_id: str = "") -> Workspace:
        return self.archive(organization_id, workspace_id, tenant_id)

    async def clone_async(
        self,
        organization_id: str,
        workspace_id: str,
        tenant_id: str = "",
        name: str | None = None,
        include_projects: bool = True,
    ) -> Workspace:  # noqa: E501
        return self.clone(organization_id, workspace_id, tenant_id, name, include_projects)

    async def transfer_async(
        self,
        organization_id: str,
        workspace_id: str,
        new_owner_user_id: str,
        tenant_id: str = "",
        actor: Principal | None = None,
    ) -> Workspace:  # noqa: E501
        return self.transfer(organization_id, workspace_id, new_owner_user_id, tenant_id, actor)

    async def list_async(self, organization_id: str | None = None, tenant_id: str = "") -> list[Workspace]:
        return self.list(organization_id, tenant_id)


def create_workspace_manager(
    workspaces: WorkspaceRepository | None = None,
    projects: ProjectRepository | None = None,
    organizations: OrganizationManager | None = None,
    members: MemberManager | None = None,
    config: OrganizationConfig | None = None,
    logger: OrganizationLogger | None = None,
    metrics: OrganizationMetricsTracker | None = None,
    audit: Any | None = None,
) -> WorkspaceManager:
    return WorkspaceManager(
        workspaces=workspaces,
        projects=projects,
        organizations=organizations,
        members=members,
        config=config,
        logger=logger,
        metrics=metrics,
        audit=audit,
    )
