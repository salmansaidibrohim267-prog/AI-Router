from __future__ import annotations

import time
import uuid
from typing import Any

from .config import OrganizationConfig
from .exceptions import (
    OrganizationArchivedError,
    OrganizationNotFoundError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    WorkspaceArchivedError,
    WorkspaceNotFoundError,
)
from .logging import OrganizationLogger
from .models import Project
from .repository import OrganizationRepository, ProjectRepository, WorkspaceRepository
from .statistics import OrganizationMetricsTracker


class ProjectManager:
    def __init__(
        self,
        projects: ProjectRepository | None = None,
        workspaces: WorkspaceRepository | None = None,
        organizations: OrganizationRepository | None = None,
        config: OrganizationConfig | None = None,
        logger: OrganizationLogger | None = None,
        metrics: OrganizationMetricsTracker | None = None,
        audit: Any | None = None,
    ):
        self._projects = projects or ProjectRepository()
        self._workspaces = workspaces or WorkspaceRepository()
        self._organizations = organizations or OrganizationRepository()
        self._config = config or OrganizationConfig()
        self._logger = logger or OrganizationLogger()
        self._metrics = metrics or OrganizationMetricsTracker(self._config)
        self._audit = audit

    @property
    def repository(self) -> ProjectRepository:
        return self._projects

    def _audit_event(self, action: str, tenant_id: str, actor: str, **details: Any) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(action=action, tenant_id=tenant_id, actor=actor, resource="projects", details=details)
        except Exception:
            pass

    def _get_org(self, organization_id: str, tenant_id: str) -> Any:
        org = self._organizations.get(organization_id)
        if org is None or org.tenant_id != tenant_id:
            raise OrganizationNotFoundError(organization_id)
        return org

    def _get_workspace(self, workspace_id: str, organization_id: str, tenant_id: str) -> Any:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None or workspace.tenant_id != tenant_id or workspace.organization_id != organization_id:
            raise WorkspaceNotFoundError(workspace_id)
        return workspace

    def create(
        self,
        organization_id: str,
        workspace_id: str,
        name: str,
        tenant_id: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Project:
        org = self._get_org(organization_id, tenant_id)
        workspace = self._get_workspace(workspace_id, organization_id, tenant_id)
        if not org.is_active:
            raise OrganizationArchivedError(organization_id)
        if not workspace.is_active:
            raise WorkspaceArchivedError(workspace_id)
        if len(name) > self._config.project_name_max_length:
            raise ValueError(f"Project name exceeds {self._config.project_name_max_length} characters")
        if self._projects.get_by_name(workspace_id, name) is not None:
            raise ProjectAlreadyExistsError(name, workspace_id)
        if self._projects.count_for_workspace(workspace_id) >= self._config.max_projects_per_workspace:
            raise ValueError(
                f"Project limit of {self._config.max_projects_per_workspace} reached for workspace {workspace_id!r}"
            )  # noqa: E501
        project = Project(
            id=f"proj_{uuid.uuid4().hex[:16]}",
            workspace_id=workspace_id,
            organization_id=organization_id,
            tenant_id=org.tenant_id,
            name=name,
            description=description,
            metadata=metadata or {},
        )
        self._projects.create(project)
        self._metrics.record("project_created", workspace_id)
        self._logger.log_event(
            "project_created",
            tenant_id=org.tenant_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            project_id=project.id,
        )
        self._audit_event("org.project_created", org.tenant_id, "", project_id=project.id, workspace_id=workspace_id)
        return project

    def update(
        self,
        organization_id: str,
        workspace_id: str,
        project_id: str,
        tenant_id: str = "",
        **fields: Any,
    ) -> Project:
        org = self._get_org(organization_id, tenant_id)
        self._get_workspace(workspace_id, organization_id, tenant_id)
        project = self._projects.get(project_id)
        if project is None or project.organization_id != organization_id or project.workspace_id != workspace_id:
            raise ProjectNotFoundError(project_id)
        allowed = {"name", "description", "metadata"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unknown project field {key!r}")
            setattr(project, key, value)
        project.updated_at = time.time()
        self._projects.update(project)
        self._audit_event("org.project_updated", org.tenant_id, "", project_id=project_id)
        return project

    def delete(self, organization_id: str, workspace_id: str, project_id: str, tenant_id: str = "") -> bool:
        org = self._get_org(organization_id, tenant_id)
        self._get_workspace(workspace_id, organization_id, tenant_id)
        project = self._projects.get(project_id)
        if project is None or project.organization_id != organization_id or project.workspace_id != workspace_id:
            raise ProjectNotFoundError(project_id)
        deleted = self._projects.delete(project_id)
        self._metrics.record("project_deleted", workspace_id)
        self._audit_event("org.project_deleted", org.tenant_id, "", project_id=project_id)
        return deleted

    def get(self, organization_id: str, workspace_id: str, project_id: str, tenant_id: str = "") -> Project:
        self._get_org(organization_id, tenant_id)
        self._get_workspace(workspace_id, organization_id, tenant_id)
        project = self._projects.get(project_id)
        if project is None or project.organization_id != organization_id or project.workspace_id != workspace_id:
            raise ProjectNotFoundError(project_id)
        return project

    def list_for_workspace(self, organization_id: str, workspace_id: str, tenant_id: str = "") -> list[Project]:
        self._get_org(organization_id, tenant_id)
        self._get_workspace(workspace_id, organization_id, tenant_id)
        return self._projects.list_for_workspace(workspace_id)

    def list_for_organization(self, organization_id: str, tenant_id: str = "") -> list[Project]:
        self._get_org(organization_id, tenant_id)
        projects: list[Project] = []
        for workspace in self._workspaces.list_for_organization(organization_id):
            projects.extend(self._projects.list_for_workspace(workspace.id))
        return sorted(projects, key=lambda p: p.created_at)

    async def create_async(
        self,
        organization_id: str,
        workspace_id: str,
        name: str,
        tenant_id: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Project:  # noqa: E501
        return self.create(organization_id, workspace_id, name, tenant_id, description, metadata)

    async def update_async(
        self, organization_id: str, workspace_id: str, project_id: str, tenant_id: str = "", **fields: Any
    ) -> Project:  # noqa: E501
        return self.update(organization_id, workspace_id, project_id, tenant_id, **fields)

    async def delete_async(self, organization_id: str, workspace_id: str, project_id: str, tenant_id: str = "") -> bool:
        return self.delete(organization_id, workspace_id, project_id, tenant_id)

    async def list_async(
        self, organization_id: str, workspace_id: str | None = None, tenant_id: str = ""
    ) -> list[Project]:  # noqa: E501
        if workspace_id is not None:
            return self.list_for_workspace(organization_id, workspace_id, tenant_id)
        return self.list_for_organization(organization_id, tenant_id)


def create_project_manager(
    projects: ProjectRepository | None = None,
    workspaces: WorkspaceRepository | None = None,
    organizations: OrganizationRepository | None = None,
    config: OrganizationConfig | None = None,
    logger: OrganizationLogger | None = None,
    metrics: OrganizationMetricsTracker | None = None,
    audit: Any | None = None,
) -> ProjectManager:
    return ProjectManager(
        projects=projects,
        workspaces=workspaces,
        organizations=organizations,
        config=config,
        logger=logger,
        metrics=metrics,
        audit=audit,
    )
