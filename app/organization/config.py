from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class OrganizationConfig:
    org_name_max_length: int = 80
    org_slug_max_length: int = 64
    workspace_name_max_length: int = 80
    workspace_slug_max_length: int = 64
    team_name_max_length: int = 60
    project_name_max_length: int = 80
    max_organizations_per_tenant: int = 50
    max_workspaces_per_org: int = 100
    max_teams_per_org: int = 200
    max_members_per_org: int = 500
    max_projects_per_workspace: int = 500
    max_pending_invitations_per_org: int = 50
    invitation_ttl_seconds: int = 7 * 24 * 3600
    default_owner_role: str = "owner"
    log_events: bool = True
    track_metrics: bool = True
    audit_enabled: bool = True

    @classmethod
    def from_env(cls) -> OrganizationConfig:
        return cls(
            org_name_max_length=int(os.getenv("ORG_NAME_MAX", "80")),
            org_slug_max_length=int(os.getenv("ORG_SLUG_MAX", "64")),
            workspace_name_max_length=int(os.getenv("ORG_WS_NAME_MAX", "80")),
            workspace_slug_max_length=int(os.getenv("ORG_WS_SLUG_MAX", "64")),
            team_name_max_length=int(os.getenv("ORG_TEAM_NAME_MAX", "60")),
            project_name_max_length=int(os.getenv("ORG_PROJECT_NAME_MAX", "80")),
            max_organizations_per_tenant=int(os.getenv("ORG_MAX_PER_TENANT", "50")),
            max_workspaces_per_org=int(os.getenv("ORG_MAX_WS_PER_ORG", "100")),
            max_teams_per_org=int(os.getenv("ORG_MAX_TEAMS", "200")),
            max_members_per_org=int(os.getenv("ORG_MAX_MEMBERS", "500")),
            max_projects_per_workspace=int(os.getenv("ORG_MAX_PROJECTS", "500")),
            max_pending_invitations_per_org=int(os.getenv("ORG_MAX_INVITES", "50")),
            invitation_ttl_seconds=int(os.getenv("ORG_INVITE_TTL", str(7 * 24 * 3600))),
            default_owner_role=os.getenv("ORG_OWNER_ROLE", "owner"),
            log_events=os.getenv("ORG_LOG_EVENTS", "1") == "1",
            track_metrics=os.getenv("ORG_TRACK_METRICS", "1") == "1",
            audit_enabled=os.getenv("ORG_AUDIT_ENABLED", "1") == "1",
        )
