from __future__ import annotations


class OrganizationError(Exception):
    pass


class OrganizationNotFoundError(OrganizationError):
    def __init__(self, organization_id: str):
        super().__init__(f"Organization {organization_id!r} not found")
        self.organization_id = organization_id


class OrganizationAlreadyExistsError(OrganizationError):
    def __init__(self, slug: str):
        super().__init__(f"Organization with slug {slug!r} already exists")
        self.slug = slug


class OrganizationLimitError(OrganizationError):
    def __init__(self, tenant_id: str, limit: int):
        super().__init__(f"Organization limit of {limit} reached for tenant {tenant_id!r}")
        self.tenant_id = tenant_id
        self.limit = limit


class OrganizationArchivedError(OrganizationError):
    def __init__(self, organization_id: str):
        super().__init__(f"Organization {organization_id!r} is archived")
        self.organization_id = organization_id


class WorkspaceNotFoundError(OrganizationError):
    def __init__(self, workspace_id: str):
        super().__init__(f"Workspace {workspace_id!r} not found")
        self.workspace_id = workspace_id


class WorkspaceAlreadyExistsError(OrganizationError):
    def __init__(self, slug: str):
        super().__init__(f"Workspace with slug {slug!r} already exists")
        self.slug = slug


class WorkspaceLimitError(OrganizationError):
    def __init__(self, organization_id: str, limit: int):
        super().__init__(f"Workspace limit of {limit} reached for organization {organization_id!r}")
        self.organization_id = organization_id
        self.limit = limit


class WorkspaceArchivedError(OrganizationError):
    def __init__(self, workspace_id: str):
        super().__init__(f"Workspace {workspace_id!r} is archived")
        self.workspace_id = workspace_id


class TeamNotFoundError(OrganizationError):
    def __init__(self, team_id: str):
        super().__init__(f"Team {team_id!r} not found")
        self.team_id = team_id


class TeamLimitError(OrganizationError):
    def __init__(self, organization_id: str, limit: int):
        super().__init__(f"Team limit of {limit} reached for organization {organization_id!r}")
        self.organization_id = organization_id
        self.limit = limit


class MemberNotFoundError(OrganizationError):
    def __init__(self, organization_id: str, user_id: str = ""):
        super().__init__(f"Member not found in organization {organization_id!r}" + (f" for user {user_id!r}" if user_id else ""))
        self.organization_id = organization_id
        self.user_id = user_id


class MemberAlreadyExistsError(OrganizationError):
    def __init__(self, organization_id: str, user_id: str):
        super().__init__(f"User {user_id!r} is already a member of organization {organization_id!r}")
        self.organization_id = organization_id
        self.user_id = user_id


class MemberLimitError(OrganizationError):
    def __init__(self, organization_id: str, limit: int):
        super().__init__(f"Member limit of {limit} reached for organization {organization_id!r}")
        self.organization_id = organization_id
        self.limit = limit


class MemberRoleError(OrganizationError):
    def __init__(self, message: str):
        super().__init__(message)


class ProjectNotFoundError(OrganizationError):
    def __init__(self, project_id: str):
        super().__init__(f"Project {project_id!r} not found")
        self.project_id = project_id


class ProjectAlreadyExistsError(OrganizationError):
    def __init__(self, name: str, workspace_id: str):
        super().__init__(f"Project {name!r} already exists in workspace {workspace_id!r}")
        self.name = name
        self.workspace_id = workspace_id


class InvitationNotFoundError(OrganizationError):
    def __init__(self, token: str):
        super().__init__(f"Invitation {token!r} not found")
        self.token = token


class InvitationExpiredError(OrganizationError):
    def __init__(self, token: str):
        super().__init__(f"Invitation {token!r} has expired")
        self.token = token


class InvitationAlreadyAcceptedError(OrganizationError):
    def __init__(self, token: str):
        super().__init__(f"Invitation {token!r} was already accepted")
        self.token = token


class InvitationLimitError(OrganizationError):
    def __init__(self, organization_id: str, limit: int):
        super().__init__(f"Pending invitation limit of {limit} reached for organization {organization_id!r}")
        self.organization_id = organization_id
        self.limit = limit


class OwnershipTransferError(OrganizationError):
    pass


class IsolationError(OrganizationError):
    def __init__(self, message: str):
        super().__init__(message)
