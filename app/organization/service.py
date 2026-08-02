from __future__ import annotations

from typing import Any

from app.auth.rbac import Principal

from .access import AccessGuard, create_access_guard
from .config import OrganizationConfig
from .invitations import InvitationManager
from .logging import OrganizationLogger
from .manager import OrganizationManager
from .members import MemberManager
from .models import Invitation, Member, Organization, Project, Team, Workspace
from .projects import ProjectManager
from .repository import (
    InvitationRepository,
    MemberRepository,
    OrganizationRepository,
    ProjectRepository,
    TeamRepository,
    WorkspaceRepository,
)
from .statistics import OrganizationMetricsTracker
from .teams import TeamManager
from .workspaces import WorkspaceManager


class OrganizationService:
    def __init__(
        self,
        organizations: OrganizationManager,
        workspaces: WorkspaceManager,
        teams: TeamManager,
        members: MemberManager,
        projects: ProjectManager,
        invitations: InvitationManager,
        guard: AccessGuard,
        config: OrganizationConfig,
        logger: OrganizationLogger,
        metrics: OrganizationMetricsTracker,
        audit: Any | None = None,
    ):
        self.organizations = organizations
        self.workspaces = workspaces
        self.teams = teams
        self.members = members
        self.projects = projects
        self.invitations = invitations
        self.guard = guard
        self.config = config
        self.logger = logger
        self.metrics = metrics
        self.audit = audit

    def create_organization(self, tenant_id: str, name: str, owner_user_id: str, **kwargs: Any) -> Organization:
        return self.organizations.create(tenant_id, name, owner_user_id, **kwargs)

    def create_workspace(self, organization_id: str, name: str, owner_user_id: str, tenant_id: str = "", **kwargs: Any) -> Workspace:
        return self.workspaces.create(organization_id, name, owner_user_id, tenant_id, **kwargs)

    def add_member(self, organization_id: str, user_id: str, tenant_id: str = "", role: str = "member", actor: Principal | None = None) -> Member:
        return self.members.add_member(organization_id, user_id, tenant_id, role, actor)

    def invite_member(self, organization_id: str, email: str, role: str = "member", tenant_id: str = "", invited_by: str = "") -> Invitation:
        return self.invitations.create(organization_id, email, role, tenant_id, invited_by)

    def create_team(self, organization_id: str, name: str, tenant_id: str = "", description: str = "") -> Team:
        return self.teams.create(organization_id, name, tenant_id, description)

    def create_project(self, organization_id: str, workspace_id: str, name: str, tenant_id: str = "", description: str = "", metadata: dict[str, Any] | None = None) -> Project:
        return self.projects.create(organization_id, workspace_id, name, tenant_id, description, metadata)

    def get_metrics(self) -> dict[str, Any]:
        return self.metrics.summary()

    def close(self) -> None:
        pass


def create_organization_service(
    organization_repository: OrganizationRepository | None = None,
    workspace_repository: WorkspaceRepository | None = None,
    team_repository: TeamRepository | None = None,
    member_repository: MemberRepository | None = None,
    project_repository: ProjectRepository | None = None,
    invitation_repository: InvitationRepository | None = None,
    guard: AccessGuard | None = None,
    config: OrganizationConfig | None = None,
    logger: OrganizationLogger | None = None,
    metrics: OrganizationMetricsTracker | None = None,
    audit: Any | None = None,
) -> OrganizationService:
    cfg = config or OrganizationConfig()
    log = logger or OrganizationLogger()
    met = metrics or OrganizationMetricsTracker(cfg)
    grd = guard or create_access_guard()

    org_repo = organization_repository or OrganizationRepository()
    ws_repo = workspace_repository or WorkspaceRepository()
    team_repo = team_repository or TeamRepository()
    mem_repo = member_repository or MemberRepository()
    proj_repo = project_repository or ProjectRepository()
    inv_repo = invitation_repository or InvitationRepository()

    organizations = OrganizationManager(
        organizations=org_repo,
        workspaces=ws_repo,
        teams=team_repo,
        members=None,
        member_repository=mem_repo,
        projects=proj_repo,
        invitations=inv_repo,
        guard=grd,
        config=cfg,
        logger=log,
        metrics=met,
        audit=audit,
    )
    members = MemberManager(
        members=mem_repo,
        organizations=org_repo,
        guard=grd,
        config=cfg,
        logger=log,
        metrics=met,
        audit=audit,
    )
    teams = TeamManager(
        teams=team_repo,
        organizations=org_repo,
        config=cfg,
        logger=log,
        metrics=met,
        audit=audit,
    )
    projects = ProjectManager(
        projects=proj_repo,
        workspaces=ws_repo,
        organizations=org_repo,
        config=cfg,
        logger=log,
        metrics=met,
        audit=audit,
    )
    invitations = InvitationManager(
        invitations=inv_repo,
        organizations=org_repo,
        members=members,
        config=cfg,
        logger=log,
        metrics=met,
        audit=audit,
    )
    workspaces = WorkspaceManager(
        workspaces=ws_repo,
        projects=proj_repo,
        organizations=organizations,
        members=members,
        config=cfg,
        logger=log,
        metrics=met,
        audit=audit,
    )
    return OrganizationService(
        organizations=organizations,
        workspaces=workspaces,
        teams=teams,
        members=members,
        projects=projects,
        invitations=invitations,
        guard=grd,
        config=cfg,
        logger=log,
        metrics=met,
        audit=audit,
    )
