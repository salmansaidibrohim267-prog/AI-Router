from __future__ import annotations

import time
import uuid
from typing import Any

from .config import OrganizationConfig
from .exceptions import (
    OrganizationNotFoundError,
    TeamLimitError,
    TeamNotFoundError,
)
from .logging import OrganizationLogger
from .models import Team
from .repository import OrganizationRepository, TeamRepository
from .statistics import OrganizationMetricsTracker


class TeamManager:
    def __init__(
        self,
        teams: TeamRepository | None = None,
        organizations: OrganizationRepository | None = None,
        config: OrganizationConfig | None = None,
        logger: OrganizationLogger | None = None,
        metrics: OrganizationMetricsTracker | None = None,
        audit: Any | None = None,
    ):
        self._teams = teams or TeamRepository()
        self._organizations = organizations or OrganizationRepository()
        self._config = config or OrganizationConfig()
        self._logger = logger or OrganizationLogger()
        self._metrics = metrics or OrganizationMetricsTracker(self._config)
        self._audit = audit

    @property
    def repository(self) -> TeamRepository:
        return self._teams

    def _audit_event(self, action: str, tenant_id: str, actor: str, **details: Any) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(action=action, tenant_id=tenant_id, actor=actor, resource="teams", details=details)
        except Exception:
            pass

    def _get_org(self, organization_id: str, tenant_id: str) -> Any:
        org = self._organizations.get(organization_id)
        if org is None:
            raise OrganizationNotFoundError(organization_id)
        if org.tenant_id != tenant_id:
            raise OrganizationNotFoundError(organization_id)
        return org

    def create(
        self, organization_id: str, name: str, tenant_id: str = "", description: str = ""
    ) -> Team:
        org = self._get_org(organization_id, tenant_id)
        if len(name) > self._config.team_name_max_length:
            raise ValueError(f"Team name exceeds {self._config.team_name_max_length} characters")
        if self._teams.count_for_organization(organization_id) >= self._config.max_teams_per_org:
            raise TeamLimitError(organization_id, self._config.max_teams_per_org)
        team = Team(
            id=f"team_{uuid.uuid4().hex[:16]}",
            organization_id=organization_id,
            tenant_id=org.tenant_id,
            name=name,
            description=description,
        )
        self._teams.create(team)
        self._metrics.record("team_created", organization_id)
        self._logger.log_event("team_created", tenant_id=org.tenant_id, organization_id=organization_id, team_id=team.id)
        self._audit_event("org.team_created", org.tenant_id, "", team_id=team.id, name=name)
        return team

    def update(self, organization_id: str, team_id: str, tenant_id: str = "", **fields: Any) -> Team:
        org = self._get_org(organization_id, tenant_id)
        team = self._teams.get(team_id)
        if team is None or team.organization_id != organization_id:
            raise TeamNotFoundError(team_id)
        allowed = {"name", "description"}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unknown team field {key!r}")
            setattr(team, key, value)
        team.updated_at = time.time()
        self._teams.update(team)
        self._audit_event("org.team_updated", org.tenant_id, "", team_id=team_id)
        return team

    def delete(self, organization_id: str, team_id: str, tenant_id: str = "") -> bool:
        org = self._get_org(organization_id, tenant_id)
        team = self._teams.get(team_id)
        if team is None or team.organization_id != organization_id:
            raise TeamNotFoundError(team_id)
        deleted = self._teams.delete(team_id)
        self._metrics.record("team_deleted", organization_id)
        self._audit_event("org.team_deleted", org.tenant_id, "", team_id=team_id)
        return deleted

    def get(self, organization_id: str, team_id: str, tenant_id: str = "") -> Team:
        self._get_org(organization_id, tenant_id)
        team = self._teams.get(team_id)
        if team is None or team.organization_id != organization_id:
            raise TeamNotFoundError(team_id)
        return team

    def list(self, organization_id: str, tenant_id: str = "") -> list[Team]:
        self._get_org(organization_id, tenant_id)
        return self._teams.list_for_organization(organization_id)

    async def create_async(self, organization_id: str, name: str, tenant_id: str = "", description: str = "") -> Team:
        return self.create(organization_id, name, tenant_id, description)

    async def update_async(self, organization_id: str, team_id: str, tenant_id: str = "", **fields: Any) -> Team:
        return self.update(organization_id, team_id, tenant_id, **fields)

    async def delete_async(self, organization_id: str, team_id: str, tenant_id: str = "") -> bool:
        return self.delete(organization_id, team_id, tenant_id)

    async def list_async(self, organization_id: str, tenant_id: str = "") -> list[Team]:
        return self.list(organization_id, tenant_id)


def create_team_manager(
    teams: TeamRepository | None = None,
    organizations: OrganizationRepository | None = None,
    config: OrganizationConfig | None = None,
    logger: OrganizationLogger | None = None,
    metrics: OrganizationMetricsTracker | None = None,
    audit: Any | None = None,
) -> TeamManager:
    return TeamManager(
        teams=teams,
        organizations=organizations,
        config=config,
        logger=logger,
        metrics=metrics,
        audit=audit,
    )
