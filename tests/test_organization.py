from __future__ import annotations

import asyncio
import time

import pytest

from app.auth import PermissionDeniedError, Principal, PermissionPolicy
from app.organization import (
    ORG_ROLE_PERMISSIONS,
    AccessGuard,
    BaseInMemoryRepository,
    Invitation,
    InvitationAlreadyAcceptedError,
    InvitationExpiredError,
    InvitationLimitError,
    InvitationManager,
    InvitationNotFoundError,
    InvitationRepository,
    InvitationStatus,
    IsolationError,    Member,
    MemberAlreadyExistsError,
    MemberLimitError,
    MemberManager,
    MemberNotFoundError,
    MemberRepository,
    MemberRole,
    MemberRoleError,
    MemberStatus,
    Organization,
    OrganizationAlreadyExistsError,
    OrganizationArchivedError,
    OrganizationConfig,
    OrganizationError,
    OrganizationLimitError,
    OrganizationLogger,
    OrganizationManager,
    OrganizationMetricsTracker,
    OrganizationNotFoundError,
    OrganizationRepository,
    OrganizationService,
    OrganizationStatus,
    OwnershipTransferError,
    Project,
    ProjectAlreadyExistsError,
    ProjectManager,
    ProjectNotFoundError,
    ProjectRepository,
    Team,
    TeamLimitError,
    TeamManager,
    TeamNotFoundError,
    TeamRepository,
    Workspace,
    WorkspaceAlreadyExistsError,
    WorkspaceArchivedError,
    WorkspaceLimitError,
    WorkspaceManager,
    WorkspaceNotFoundError,
    WorkspaceRepository,
    WorkspaceStatus,
    create_invitation_manager,
    create_member_manager,
    create_organization_manager,
    create_organization_service,
    create_workspace_manager,
    make_slug,
    validate_member_role,
)
from app.organization.access import AccessGuard as _AccessGuard
from app.organization.exceptions import MemberRoleError as _MemberRoleError
from app.organization.models import generate_id
from app.organization.projects import create_project_manager
from app.organization.service import OrganizationService as _OrganizationService
from app.organization.teams import create_team_manager
from app.tenancy import AuditLogger, TenancyConfig


def make_config(**kwargs):
    defaults = {"log_events": False, "track_metrics": True, "audit_enabled": False}
    defaults.update(kwargs)
    return OrganizationConfig(**defaults)


def make_service(**kwargs):
    defaults = {"config": make_config()}
    defaults.update(kwargs)
    return create_organization_service(**defaults)


def make_org(service=None, tenant_id="t1", name="Acme", owner="u_owner", **kw):
    service = service or make_service()
    org = service.organizations.create(tenant_id, name, owner, **kw)
    return service, org


def make_principal(user_id="u_owner", tenant_id="t1"):
    return Principal(user_id=user_id, tenant_id=tenant_id, roles=["viewer"])


async def _run_async(coro):
    return await coro


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- config

def test_config_defaults():
    cfg = OrganizationConfig()
    assert cfg.max_workspaces_per_org == 100
    assert cfg.max_members_per_org == 500
    assert cfg.invitation_ttl_seconds == 7 * 24 * 3600
    assert cfg.audit_enabled is True


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("ORG_MAX_WS_PER_ORG", "3")
    monkeypatch.setenv("ORG_MAX_MEMBERS", "10")
    monkeypatch.setenv("ORG_INVITE_TTL", "60")
    monkeypatch.setenv("ORG_TRACK_METRICS", "0")
    cfg = OrganizationConfig.from_env()
    assert cfg.max_workspaces_per_org == 3
    assert cfg.max_members_per_org == 10
    assert cfg.invitation_ttl_seconds == 60
    assert cfg.track_metrics is False


# ---------------------------------------------------------------- models

def test_make_slug_and_generate_id():
    assert make_slug("Hello World!") == "hello-world"
    assert make_slug("--") == "item"
    assert make_slug("a" * 100, max_length=10) == "a" * 10
    assert make_slug("ABC-DEF") == "abc-def"
    assert generate_id("org").startswith("org_")
    assert generate_id("ws") != generate_id("ws")


def test_org_status_and_to_dict():
    org = Organization(id="org_1", tenant_id="t1", name="Acme", slug="acme", owner_user_id="u1")
    assert org.is_active is True
    assert org.is_archived is False
    archived = Organization(id="org_2", tenant_id="t1", name="B", slug="b", owner_user_id="u1", status=OrganizationStatus.ARCHIVED)
    assert archived.is_archived is True
    assert archived.is_active is False
    d = org.to_dict()
    assert d["slug"] == "acme"
    assert d["status"] == "active"
    assert d["owner_user_id"] == "u1"


def test_workspace_model():
    ws = Workspace(id="ws_1", organization_id="org_1", tenant_id="t1", name="W", slug="w", owner_user_id="u1")
    assert ws.is_active is True
    ws2 = Workspace(id="ws_2", organization_id="org_1", tenant_id="t1", name="W", slug="w", owner_user_id="u1", status=WorkspaceStatus.ARCHIVED)
    assert ws2.is_archived is True
    assert ws2.to_dict()["status"] == "archived"
    assert ws.to_dict()["owner_user_id"] == "u1"


def test_team_member_project_invitation_models():
    team = Team(id="team_1", organization_id="org_1", tenant_id="t1", name="Core")
    assert team.to_dict()["name"] == "Core"
    member = Member(id="mem_1", organization_id="org_1", tenant_id="t1", user_id="u1", role=MemberRole.ADMIN)
    d = member.to_dict()
    assert d["role"] == "admin"
    assert d["team_ids"] == []
    project = Project(id="proj_1", workspace_id="ws_1", organization_id="org_1", tenant_id="t1", name="P")
    assert project.to_dict()["workspace_id"] == "ws_1"
    inv = Invitation(id="inv_1", organization_id="org_1", tenant_id="t1", email="a@b.io", role=MemberRole.MEMBER, invited_by="u1", token="tok")
    assert inv.is_expired is False
    inv2 = Invitation(id="inv_2", organization_id="org_1", tenant_id="t1", email="a@b.io", role=MemberRole.MEMBER, invited_by="u1", token="tok2", expires_at=time.time() - 5)
    assert inv2.is_expired is True
    d2 = inv.to_dict()
    assert d2["status"] == "pending"
    assert d2["role"] == "member"


# ---------------------------------------------------------------- logging + statistics

def test_logger(caplog):
    with caplog.at_level("INFO"):
        OrganizationLogger().log_event("created", tenant_id="t1", organization_id="org_1", name="Acme")
    assert any("organization_created" in r.message for r in caplog.records)


def test_logger_fallback(monkeypatch):
    import app.organization.logging as org_logging

    def boom(*args, **kwargs):
        raise RuntimeError("nope")
    monkeypatch.setattr(org_logging.json, "dumps", boom)
    logger = OrganizationLogger()
    logger.log_event("created", tenant_id="t1")
    logger.log_event("created")


def test_metrics_tracker():
    m = OrganizationMetricsTracker(make_config())
    m.record("organization_created", "org_1")
    m.record("organization_created", "org_1")
    m.record("workspace_created", "org_1")
    assert m.for_scope("org_1")["organization_created"] == 2
    summary = m.summary()
    assert summary["events"]["workspace_created"] == 1
    assert m.enabled is True
    m.reset()
    assert summary["per_scope"]["org_1"]["workspace_created"] == 1
    assert m.summary()["events"] == {}
    disabled = OrganizationMetricsTracker(make_config(track_metrics=False))
    disabled.record("x", "org_1")
    assert disabled.summary()["events"] == {}
    assert disabled.enabled is False


# ---------------------------------------------------------------- repositories

def test_base_repository_crud():
    repo = OrganizationRepository()
    org = Organization(id="org_1", tenant_id="t1", name="A", slug="a", owner_user_id="u1")
    assert repo.create(org) is org
    assert repo.get("org_1") is org
    assert repo.get("nope") is None
    org.name = "B"
    repo.update(org)
    assert repo.get("org_1").name == "B"
    assert repo.delete("org_1") is True
    assert repo.delete("org_1") is False


def test_organization_repository():
    repo = OrganizationRepository()
    repo.create(Organization(id="org_1", tenant_id="t1", name="A", slug="a", owner_user_id="u1"))
    repo.create(Organization(id="org_2", tenant_id="t2", name="B", slug="b", owner_user_id="u2"))
    repo.create(Organization(id="org_3", tenant_id="t1", name="C", slug="c", owner_user_id="u3"))
    assert repo.get_by_slug("a", "t1").id == "org_1"
    assert repo.get_by_slug("a", "t2") is None
    assert [o.id for o in repo.list_for_tenant("t1")] == ["org_1", "org_3"]
    assert repo.count_for_tenant("t1") == 2


def test_workspace_repository():
    repo = WorkspaceRepository()
    repo.create(Workspace(id="ws_1", organization_id="org_1", tenant_id="t1", name="A", slug="a", owner_user_id="u1"))
    repo.create(Workspace(id="ws_2", organization_id="org_1", tenant_id="t1", name="B", slug="b", owner_user_id="u1"))
    repo.create(Workspace(id="ws_3", organization_id="org_2", tenant_id="t2", name="C", slug="c", owner_user_id="u2"))
    assert repo.get_by_slug("a", "org_1").id == "ws_1"
    assert repo.get_by_slug("a", "org_2") is None
    assert len(repo.list_for_organization("org_1")) == 2
    assert len(repo.list_for_tenant("t1")) == 2
    assert repo.count_for_organization("org_1") == 2


def test_team_repository():
    repo = TeamRepository()
    repo.create(Team(id="t1", organization_id="org_1", tenant_id="t1", name="A"))
    repo.create(Team(id="t2", organization_id="org_1", tenant_id="t1", name="B"))
    repo.create(Team(id="t3", organization_id="org_2", tenant_id="t2", name="C"))
    assert len(repo.list_for_organization("org_1")) == 2
    assert repo.count_for_organization("org_1") == 2


def test_member_repository():
    repo = MemberRepository()
    repo.create(Member(id="m1", organization_id="org_1", tenant_id="t1", user_id="u1"))
    repo.create(Member(id="m2", organization_id="org_1", tenant_id="t1", user_id="u2"))
    repo.create(Member(id="m3", organization_id="org_2", tenant_id="t2", user_id="u3"))
    assert repo.get_by_user("org_1", "u1").id == "m1"
    assert repo.get_by_user("org_1", "zzz") is None
    assert len(repo.list_for_organization("org_1")) == 2
    assert repo.count_for_organization("org_1") == 2
    assert repo.delete_for_organization("org_1") == 2
    assert repo.count_for_organization("org_1") == 0


def test_project_repository():
    repo = ProjectRepository()
    repo.create(Project(id="p1", workspace_id="ws_1", organization_id="org_1", tenant_id="t1", name="A"))
    repo.create(Project(id="p2", workspace_id="ws_1", organization_id="org_1", tenant_id="t1", name="B"))
    repo.create(Project(id="p3", workspace_id="ws_2", organization_id="org_1", tenant_id="t1", name="C"))
    assert repo.get_by_name("ws_1", "A").id == "p1"
    assert repo.get_by_name("ws_1", "Z") is None
    assert len(repo.list_for_workspace("ws_1")) == 2
    assert repo.count_for_workspace("ws_1") == 2


def test_invitation_repository():
    repo = InvitationRepository()
    now = time.time()
    repo.create(Invitation(id="i1", organization_id="org_1", tenant_id="t1", email="a@b.io", role=MemberRole.MEMBER, invited_by="u1", token="tok1"))
    repo.create(Invitation(id="i2", organization_id="org_1", tenant_id="t1", email="c@d.io", role=MemberRole.MEMBER, invited_by="u1", token="tok2", status=InvitationStatus.ACCEPTED))
    repo.create(Invitation(id="i3", organization_id="org_2", tenant_id="t2", email="e@f.io", role=MemberRole.MEMBER, invited_by="u1", token="tok3"))
    assert repo.get_by_token("tok1").id == "i1"
    assert repo.get_by_token("nope") is None
    assert len(repo.list_for_organization("org_1")) == 2
    assert len(repo.list_for_organization("org_1", status="pending")) == 1
    assert repo.count_pending_for_organization("org_1") == 1


# ---------------------------------------------------------------- access / rbac

def test_access_guard_role_permissions():
    guard = AccessGuard()
    owner = Member(id="m1", organization_id="org_1", tenant_id="t1", user_id="u1", role=MemberRole.OWNER)
    admin = Member(id="m2", organization_id="org_1", tenant_id="t1", user_id="u2", role=MemberRole.ADMIN)
    viewer = Member(id="m3", organization_id="org_1", tenant_id="t1", user_id="u3", role=MemberRole.VIEWER)
    assert guard.member_allowed(owner, "anything:at:all") is True
    assert guard.member_allowed(admin, "org:manage_members") is True
    assert guard.member_allowed(admin, "org:delete") is False
    assert guard.member_allowed(viewer, "org:view") is True
    assert guard.member_allowed(viewer, "project:update") is False
    suspended = Member(id="m4", organization_id="org_1", tenant_id="t1", user_id="u4", role=MemberRole.ADMIN, status=MemberStatus.SUSPENDED)
    assert guard.member_allowed(suspended, "org:view") is False
    assert "*" in guard.permissions_for_role("owner")
    assert guard.permissions_for_role("unknown_role") == set()
    guard.register_role_permissions("auditor", {"org:view", "audit:read"})
    assert "audit:read" in guard.permissions_for_role("auditor")


def test_access_guard_require_and_principal():
    guard = AccessGuard()
    member = Member(id="m1", organization_id="org_1", tenant_id="t1", user_id="u1", role=MemberRole.MEMBER)
    principal = Principal(user_id="u1", tenant_id="t1", roles=[])
    guard.require(principal, member, "org:view")
    with pytest.raises(PermissionDeniedError):
        guard.require(principal, member, "org:update")
    wrong_user = Principal(user_id="u2", tenant_id="t1", roles=[])
    with pytest.raises(PermissionDeniedError):
        guard.verify_principal(wrong_user, member)
    wrong_tenant = Principal(user_id="u1", tenant_id="t2", roles=[])
    with pytest.raises(IsolationError):
        guard.verify_principal(wrong_tenant, member)
    assert guard.policy is not None
    with pytest.raises(PermissionDeniedError):
        guard.require_member(member, "org:update")


def test_access_guard_assert_tenant_and_owner():
    guard = AccessGuard()
    guard.assert_tenant("t1", "t1")
    with pytest.raises(IsolationError):
        guard.assert_tenant("t1", "t2")
    guard.assert_tenant("", "t1")
    guard.assert_tenant("t1", "")
    org = Organization(id="org_1", tenant_id="t1", name="A", slug="a", owner_user_id="u1")
    guard.require_org_owner(org, "u1")
    with pytest.raises(PermissionDeniedError):
        guard.require_org_owner(org, "someone_else")


def test_validate_member_role():
    assert validate_member_role("admin") == "admin"
    assert validate_member_role("owner") == "owner"
    with pytest.raises(MemberRoleError):
        validate_member_role("superuser")
    assert sorted(ORG_ROLE_PERMISSIONS) == ["admin", "member", "owner", "viewer"]
    assert "workspace:create_project" in ORG_ROLE_PERMISSIONS["member"]


def test_access_guard_policy_integration():
    policy = PermissionPolicy(deny_permissions={"workspace:delete"})
    guard = AccessGuard(policy=policy)
    assert guard.policy is policy
    owner = Member(id="m1", organization_id="org_1", tenant_id="t1", user_id="u1", role=MemberRole.OWNER)
    assert guard.member_allowed(owner, "workspace:delete") is True
    principal = Principal(user_id="u1", tenant_id="t1", roles=["admin"])
    assert policy.check(principal, "read:chat") is True
    assert policy.check(principal, "workspace:delete") is False


def test_create_access_guard():
    from app.organization import create_access_guard
    assert isinstance(create_access_guard(), AccessGuard)


# ---------------------------------------------------------------- organization manager

def test_org_create_and_get():
    service, org = make_org()
    assert org.id.startswith("org_")
    assert org.slug == "acme"
    assert service.organizations.get("t1", org.id).id == org.id
    assert service.organizations.get_by_slug("t1", "acme").id == org.id
    owner = service.members.get_member(org.id, "u_owner")
    assert owner.role == MemberRole.OWNER
    assert service.members.count(org.id) == 1


def test_org_create_slug_conflict_and_limit():
    service, org = make_org(name="Acme")
    with pytest.raises(OrganizationAlreadyExistsError):
        service.organizations.create("t1", "acme again", "u2", slug="acme")
    other_tenant = make_service()
    org2 = other_tenant.organizations.create("t2", "Acme", "u3")
    assert org2.slug == "acme"
    limited = make_service(config=make_config(max_organizations_per_tenant=1))
    limited.organizations.create("t1", "One", "u1")
    with pytest.raises(OrganizationLimitError):
        limited.organizations.create("t1", "Two", "u1")


def test_org_create_name_too_long():
    service = make_service()
    with pytest.raises(ValueError):
        service.organizations.create("t1", "x" * 100, "u1")


def test_org_update():
    service, org = make_org()
    updated = service.organizations.update("t1", org.id, name="Acme Ltd", description="d", plan="pro", metadata={"k": "v"})
    assert updated.name == "Acme Ltd"
    assert updated.plan == "pro"
    with pytest.raises(ValueError):
        service.organizations.update("t1", org.id, bogus_field=1)
    org2 = service.organizations.create("t1", "Other", "u1", slug="other")
    with pytest.raises(OrganizationAlreadyExistsError):
        service.organizations.update("t1", org.id, slug="other")
    service.organizations.update("t1", org.id, slug="acme-renamed")
    assert service.organizations.get("t1", org.id).slug == "acme-renamed"
    assert service.organizations.get("t1", org2.id).slug == "other"


def test_org_archive_restore():
    service, org = make_org()
    archived = service.organizations.archive("t1", org.id)
    assert archived.is_archived
    assert service.organizations.get("t1", org.id).is_archived
    restored = service.organizations.restore("t1", org.id)
    assert restored.is_active
    assert service.organizations.archive("t1", org.id).is_archived
    assert service.organizations.restore("t1", org.id).is_active
    assert service.organizations.archive("t1", org.id).is_archived
    # archiving twice is idempotent
    assert service.organizations.archive("t1", org.id).is_archived


def test_org_delete_cascades():
    service, org = make_org()
    ws = service.create_workspace(org.id, "W1", "u_owner", tenant_id="t1")
    service.create_project(org.id, ws.id, "P1", tenant_id="t1")
    service.create_team(org.id, "Core", tenant_id="t1")
    service.invite_member(org.id, "x@y.io", tenant_id="t1")
    assert service.organizations.delete("t1", org.id) is True
    assert service.organizations.list("t1") == []
    assert service.workspaces.list(tenant_id="t1") == []
    assert service.teams.repository.list_for_organization(org.id) == []
    assert service.members.repository.list_for_organization(org.id) == []
    assert service.invitations.repository.list_for_organization(org.id) == []
    assert service.projects.repository.list_for_workspace(ws.id) == []
    with pytest.raises(OrganizationNotFoundError):
        service.organizations.delete("t1", org.id)


def test_org_get_isolation_and_missing():
    service, org = make_org()
    with pytest.raises(OrganizationNotFoundError):
        service.organizations.get("t2", org.id)
    with pytest.raises(OrganizationNotFoundError):
        service.organizations.get("t1", "org_missing")
    with pytest.raises(OrganizationNotFoundError):
        service.organizations.get_by_slug("t2", "acme")
    with pytest.raises(OrganizationNotFoundError):
        service.organizations.get_by_slug("t1", "nope")


def test_org_list_filter():
    service, org = make_org(name="Alpha")
    service.organizations.create("t1", "Beta", "u2")
    service.organizations.archive("t1", org.id)
    assert len(service.organizations.list("t1")) == 2
    assert [o.slug for o in service.organizations.list("t1", status="archived")] == ["alpha"]
    assert [o.slug for o in service.organizations.list("t1", status="active")] == ["beta"]
    assert service.organizations.list("t2") == []


def test_org_transfer_ownership():
    service, org = make_org()
    service.members.add_member(org.id, "u_new_owner", tenant_id="t1", role="admin")
    principal = make_principal()
    transferred = service.organizations.transfer_ownership(principal, org.id, "u_new_owner", "t1")
    assert transferred.owner_user_id == "u_new_owner"
    assert service.members.get_member(org.id, "u_owner").role == MemberRole.ADMIN
    assert service.members.get_member(org.id, "u_new_owner").role == MemberRole.OWNER
    # transfer to self is a no-op
    assert service.organizations.transfer_ownership(principal, org.id, "u_new_owner", "t1").owner_user_id == "u_new_owner"


def test_org_transfer_ownership_errors():
    service, org = make_org()
    principal = make_principal()
    with pytest.raises(OwnershipTransferError):
        service.organizations.transfer_ownership(principal, org.id, "not_a_member", "t1")
    stranger = Principal(user_id="u_stranger", tenant_id="t1", roles=[])
    with pytest.raises(OwnershipTransferError):
        service.organizations.transfer_ownership(stranger, org.id, "u_someone", "t1")
    # transfer to the current owner is a no-op even for non-members
    assert service.organizations.transfer_ownership(stranger, org.id, "u_owner", "t1").owner_user_id == "u_owner"
    service.members.add_member(org.id, "u_member", tenant_id="t1", role="member")
    service.members.add_member(org.id, "u_target", tenant_id="t1", role="member")
    viewer = make_principal("u_member")
    with pytest.raises(PermissionDeniedError):
        service.organizations.transfer_ownership(viewer, org.id, "u_target", "t1")


def test_org_async_operations():
    service, org = make_org()
    org2 = run(service.organizations.create_async("t1", "Async Inc", "u_async"))
    assert org2.id != org.id
    updated = run(service.organizations.update_async("t1", org2.id, name="Async GmbH"))
    assert updated.name == "Async GmbH"
    archived = run(service.organizations.archive_async("t1", org2.id))
    assert archived.is_archived
    restored = run(service.organizations.restore_async("t1", org2.id))
    assert restored.is_active
    assert len(run(service.organizations.list_async("t1"))) == 2
    service.members.add_member(org2.id, "u_owner", tenant_id="t1", role="admin")
    owner = make_principal("u_async")
    assert run(service.organizations.transfer_ownership_async(owner, org2.id, "u_owner", "t1")).owner_user_id == "u_owner"
    assert run(service.organizations.delete_async("t1", org2.id)) is True


# ---------------------------------------------------------------- members

def test_member_add_list_remove():
    service, org = make_org()
    member = service.members.add_member(org.id, "u2", tenant_id="t1", role="member")
    assert member.id.startswith("mem_")
    assert service.members.is_member(org.id, "u2") is True
    assert service.members.is_member(org.id, "zzz") is False
    assert [m.user_id for m in service.members.list_members(org.id)] == ["u_owner", "u2"]
    assert service.members.get_member(org.id, "u2").role == MemberRole.MEMBER
    assert service.members.remove_member(org.id, "u2", tenant_id="t1") is True
    assert service.members.is_member(org.id, "u2") is False


def test_member_errors():
    service, org = make_org()
    with pytest.raises(OrganizationNotFoundError):
        service.members.add_member("org_missing", "u2", tenant_id="t1")
    with pytest.raises(IsolationError):
        service.members.add_member(org.id, "u2", tenant_id="t2")
    service.members.add_member(org.id, "u2", tenant_id="t1")
    with pytest.raises(MemberAlreadyExistsError):
        service.members.add_member(org.id, "u2", tenant_id="t1")
    with pytest.raises(MemberNotFoundError):
        service.members.remove_member(org.id, "u_nope", tenant_id="t1")
    with pytest.raises(MemberNotFoundError):
        service.members.get_member(org.id, "u_nope")
    with pytest.raises(MemberNotFoundError):
        service.members.get_member(org.id, "u_nope", tenant_id="t1")
    with pytest.raises(OrganizationNotFoundError):
        service.members.list_members("org_missing", "t1")


def test_member_owner_protections():
    service, org = make_org()
    actor = make_principal()
    with pytest.raises(MemberRoleError):
        service.members.add_member(org.id, "u2", tenant_id="t1", role="owner", actor=actor)
    service.members.add_member(org.id, "u2", tenant_id="t1", role="member", actor=actor)
    with pytest.raises(MemberRoleError):
        service.members.remove_member(org.id, "u_owner", tenant_id="t1", actor=actor)
    with pytest.raises(MemberRoleError):
        service.members.set_role(org.id, "u_owner", "member", tenant_id="t1", actor=actor)
    with pytest.raises(MemberRoleError):
        service.members.set_role(org.id, "u2", "owner", tenant_id="t1", actor=actor)
    with pytest.raises(MemberRoleError):
        service.members.set_role(org.id, "u2", "superadmin", tenant_id="t1", actor=actor)
    with pytest.raises(MemberNotFoundError):
        service.members.set_role(org.id, "u_nope", "member", tenant_id="t1", actor=actor)


def test_member_rbac_enforcement():
    service, org = make_org()
    service.members.add_member(org.id, "u_viewer", tenant_id="t1", role="viewer")
    viewer = make_principal("u_viewer")
    with pytest.raises(PermissionDeniedError):
        service.members.add_member(org.id, "u3", tenant_id="t1", role="member", actor=viewer)
    with pytest.raises(MemberNotFoundError):
        service.members.add_member(org.id, "u3", tenant_id="t1", role="member", actor=make_principal("u_stranger"))
    admin = service.members.add_member(org.id, "u_admin", tenant_id="t1", role="admin")
    admin_principal = make_principal("u_admin")
    service.members.add_member(org.id, "u3", tenant_id="t1", role="member", actor=admin_principal)
    assert service.members.has_permission(admin_principal, org.id, "org:manage_members") is True
    assert service.members.has_permission(viewer, org.id, "org:manage_members") is False
    assert service.members.has_permission(viewer, "org_missing", "org:view") is False
    with pytest.raises(MemberNotFoundError):
        service.members.require_permission(make_principal("u_stranger"), org.id, "org:view")


def test_member_limit():
    service = make_service(config=make_config(max_members_per_org=2))
    org = service.organizations.create("t1", "Tiny", "u_owner")
    service.members.add_member(org.id, "u2", tenant_id="t1")
    with pytest.raises(MemberLimitError):
        service.members.add_member(org.id, "u3", tenant_id="t1")


def test_member_archived_org_blocked():
    service, org = make_org()
    service.organizations.archive("t1", org.id)
    with pytest.raises(OrganizationArchivedError):
        service.members.add_member(org.id, "u2", tenant_id="t1")


def test_member_async():
    service, org = make_org()
    member = run(service.members.add_member_async(org.id, "u2", tenant_id="t1", role="admin"))
    assert member.role == MemberRole.ADMIN
    assert run(service.members.set_role_async(org.id, "u2", "member", tenant_id="t1")).role == MemberRole.MEMBER
    assert len(run(service.members.list_members_async(org.id))) == 2
    assert run(service.members.remove_member_async(org.id, "u2", tenant_id="t1")) is True


# ---------------------------------------------------------------- teams

def test_team_crud():
    service, org = make_org()
    team = service.teams.create(org.id, "Core Platform", tenant_id="t1", description="d")
    assert team.id.startswith("team_")
    assert service.teams.get(org.id, team.id, "t1").name == "Core Platform"
    updated = service.teams.update(org.id, team.id, tenant_id="t1", name="Edge", description="e")
    assert updated.name == "Edge"
    with pytest.raises(ValueError):
        service.teams.update(org.id, team.id, tenant_id="t1", bogus=1)
    assert len(service.teams.list(org.id, "t1")) == 1
    assert service.teams.delete(org.id, team.id, "t1") is True
    assert service.teams.list(org.id, "t1") == []


def test_team_errors():
    service, org = make_org()
    with pytest.raises(OrganizationNotFoundError):
        service.teams.create("org_missing", "T", tenant_id="t1")
    with pytest.raises(OrganizationNotFoundError):
        service.teams.create(org.id, "T", tenant_id="t2")
    with pytest.raises(ValueError):
        service.teams.create(org.id, "x" * 100, tenant_id="t1")
    with pytest.raises(TeamNotFoundError):
        service.teams.get(org.id, "team_missing", "t1")
    with pytest.raises(TeamNotFoundError):
        service.teams.update(org.id, "team_missing", tenant_id="t1")
    with pytest.raises(TeamNotFoundError):
        service.teams.delete(org.id, "team_missing", tenant_id="t1")
    with pytest.raises(OrganizationNotFoundError):
        service.teams.get(org.id, "team_missing")
    limited = make_service(config=make_config(max_teams_per_org=1))
    org2 = limited.organizations.create("t1", "L", "u1")
    limited.teams.create(org2.id, "One", tenant_id="t1")
    with pytest.raises(TeamLimitError):
        limited.teams.create(org2.id, "Two", tenant_id="t1")


def test_team_cross_org_isolation():
    service, org = make_org()
    other_service, other_org = make_org(name="Other")
    team = other_service.teams.create(other_org.id, "T", tenant_id="t1")
    with pytest.raises(TeamNotFoundError):
        service.teams.get(org.id, team.id, "t1")


def test_team_async():
    service, org = make_org()
    team = run(service.teams.create_async(org.id, "A", tenant_id="t1"))
    run(service.teams.update_async(org.id, team.id, tenant_id="t1", name="B"))
    assert len(run(service.teams.list_async(org.id, "t1"))) == 1
    assert run(service.teams.delete_async(org.id, team.id, "t1")) is True


# ---------------------------------------------------------------- workspaces

def test_workspace_crud():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "Production", "u_owner", tenant_id="t1")
    assert ws.id.startswith("ws_")
    assert ws.slug == "production"
    assert service.workspaces.get(org.id, ws.id, "t1").id == ws.id
    updated = service.workspaces.update(org.id, ws.id, tenant_id="t1", name="Prod", description="x")
    assert updated.name == "Prod"
    assert len(service.workspaces.list(org.id, "t1")) == 1
    assert service.workspaces.list(tenant_id="t1")[0].id == ws.id
    assert service.workspaces.delete(org.id, ws.id, "t1") is True
    assert service.workspaces.list(tenant_id="t1") == []


def test_workspace_errors():
    service, org = make_org()
    with pytest.raises(OrganizationNotFoundError):
        service.workspaces.create("org_missing", "W", "u1", tenant_id="t1")
    with pytest.raises(OrganizationNotFoundError):
        service.workspaces.create(org.id, "W", "u1", tenant_id="t2")
    with pytest.raises(ValueError):
        service.workspaces.create(org.id, "x" * 100, "u1", tenant_id="t1")
    ws = service.workspaces.create(org.id, "Prod", "u1", tenant_id="t1")
    with pytest.raises(WorkspaceAlreadyExistsError):
        service.workspaces.create(org.id, "other name", "u1", tenant_id="t1", slug="prod")
    with pytest.raises(WorkspaceAlreadyExistsError):
        service.workspaces.update(org.id, ws.id, tenant_id="t1", slug="prod")
    with pytest.raises(ValueError):
        service.workspaces.update(org.id, ws.id, tenant_id="t1", bogus=1)
    with pytest.raises(WorkspaceNotFoundError):
        service.workspaces.get(org.id, "ws_missing", "t1")
    with pytest.raises(WorkspaceNotFoundError):
        service.workspaces.update(org.id, "ws_missing", tenant_id="t1")
    with pytest.raises(WorkspaceNotFoundError):
        service.workspaces.delete(org.id, "ws_missing", tenant_id="t1")
    other_service, other_org = make_org(name="Other")
    other_ws = other_service.workspaces.create(other_org.id, "W", "u1", tenant_id="t1")
    with pytest.raises(WorkspaceNotFoundError):
        service.workspaces.get(org.id, other_ws.id, "t1")
    with pytest.raises(OrganizationNotFoundError):
        service.workspaces.list("org_missing", "t1")


def test_workspace_archived_org_and_limit():
    service = make_service(config=make_config(max_workspaces_per_org=1))
    org = service.organizations.create("t1", "A", "u1")
    service.workspaces.create(org.id, "One", "u1", tenant_id="t1")
    with pytest.raises(WorkspaceLimitError):
        service.workspaces.create(org.id, "Two", "u1", tenant_id="t1")
    service.organizations.archive("t1", org.id)
    with pytest.raises(OrganizationArchivedError):
        service.workspaces.create(org.id, "Three", "u1", tenant_id="t1")


def test_workspace_archive_restore():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u1", tenant_id="t1")
    archived = service.workspaces.archive(org.id, ws.id, "t1")
    assert archived.is_archived
    restored = service.workspaces.restore(org.id, ws.id, "t1")
    assert restored.is_active
    with pytest.raises(WorkspaceNotFoundError):
        service.workspaces.archive(org.id, "ws_missing", "t1")
    with pytest.raises(WorkspaceNotFoundError):
        service.workspaces.restore(org.id, "ws_missing", "t1")


def test_workspace_delete_cascades_projects():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u1", tenant_id="t1")
    service.projects.create(org.id, ws.id, "P1", tenant_id="t1")
    service.projects.create(org.id, ws.id, "P2", tenant_id="t1")
    assert service.workspaces.delete(org.id, ws.id, "t1") is True
    assert service.projects.repository.list_for_workspace(ws.id) == []


def test_workspace_clone():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "Main", "u_owner", tenant_id="t1", description="desc", metadata={"env": "prod"})
    service.projects.create(org.id, ws.id, "API", tenant_id="t1", description="d1", metadata={"k": 1})
    clone = service.workspaces.clone(org.id, ws.id, tenant_id="t1")
    assert clone.id != ws.id
    assert clone.name == "Main (copy)"
    assert clone.owner_user_id == "u_owner"
    assert clone.description == "desc"
    assert clone.metadata == {"env": "prod"}
    clone_projects = service.projects.list_for_workspace(org.id, clone.id, "t1")
    assert [p.name for p in clone_projects] == ["API"]
    assert clone_projects[0].metadata == {"k": 1}
    assert clone_projects[0].workspace_id == clone.id
    named = service.workspaces.clone(org.id, ws.id, tenant_id="t1", name="Custom Copy", include_projects=False)
    assert named.name == "Custom Copy"
    assert service.projects.list_for_workspace(org.id, named.id, "t1") == []
    with pytest.raises(WorkspaceNotFoundError):
        service.workspaces.clone(org.id, "ws_missing", tenant_id="t1")


def test_workspace_clone_archived_org():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u1", tenant_id="t1")
    service.organizations.archive("t1", org.id)
    with pytest.raises(OrganizationArchivedError):
        service.workspaces.clone(org.id, ws.id, tenant_id="t1")


def test_workspace_transfer():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u_owner", tenant_id="t1")
    service.members.add_member(org.id, "u_new", tenant_id="t1", role="member")
    transferred = service.workspaces.transfer(org.id, ws.id, "u_new", tenant_id="t1")
    assert transferred.owner_user_id == "u_new"
    actor = make_principal()
    service.members.add_member(org.id, "u_admin", tenant_id="t1", role="admin")
    service.workspaces.transfer(org.id, ws.id, "u_admin", tenant_id="t1", actor=make_principal("u_admin"))
    assert service.workspaces.get(org.id, ws.id, "t1").owner_user_id == "u_admin"
    with pytest.raises(MemberNotFoundError):
        service.workspaces.transfer(org.id, ws.id, "not_a_member", tenant_id="t1")
    with pytest.raises(WorkspaceNotFoundError):
        service.workspaces.transfer(org.id, "ws_missing", "u_admin", tenant_id="t1")
    viewer = make_principal("u_admin")
    viewer.user_id = "u_viewer"
    service.members.add_member(org.id, "u_viewer", tenant_id="t1", role="viewer")
    with pytest.raises(PermissionDeniedError):
        service.workspaces.transfer(org.id, ws.id, "u_owner", tenant_id="t1", actor=viewer)


def test_workspace_async():
    service, org = make_org()
    ws = run(service.workspaces.create_async(org.id, "W", "u1", tenant_id="t1"))
    run(service.workspaces.update_async(org.id, ws.id, tenant_id="t1", name="W2"))
    archived = run(service.workspaces.archive_async(org.id, ws.id, "t1"))
    assert archived.is_archived
    assert len(run(service.workspaces.list_async(org.id, "t1"))) == 1
    clone = run(service.workspaces.clone_async(org.id, ws.id, tenant_id="t1"))
    assert clone.id != ws.id
    assert run(service.workspaces.transfer_async(org.id, ws.id, "u_owner", tenant_id="t1")).owner_user_id == "u_owner"
    assert run(service.workspaces.delete_async(org.id, clone.id, "t1")) is True


# ---------------------------------------------------------------- projects

def test_project_crud():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u1", tenant_id="t1")
    project = service.projects.create(org.id, ws.id, "Billing", tenant_id="t1", description="d", metadata={"team": "fin"})
    assert project.id.startswith("proj_")
    assert service.projects.get(org.id, ws.id, project.id, "t1").name == "Billing"
    updated = service.projects.update(org.id, ws.id, project.id, tenant_id="t1", name="Billing 2", metadata={"team": "eng"})
    assert updated.name == "Billing 2"
    assert updated.metadata == {"team": "eng"}
    with pytest.raises(ValueError):
        service.projects.update(org.id, ws.id, project.id, tenant_id="t1", bogus=1)
    assert [p.id for p in service.projects.list_for_workspace(org.id, ws.id, "t1")] == [project.id]
    assert service.projects.delete(org.id, ws.id, project.id, "t1") is True
    assert service.projects.list_for_workspace(org.id, ws.id, "t1") == []


def test_project_errors():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u1", tenant_id="t1")
    with pytest.raises(OrganizationNotFoundError):
        service.projects.create("org_missing", ws.id, "P", tenant_id="t1")
    with pytest.raises(WorkspaceNotFoundError):
        service.projects.create(org.id, "ws_missing", "P", tenant_id="t1")
    other_service, other_org = make_org(name="Other")
    other_ws = other_service.workspaces.create(other_org.id, "W2", "u1", tenant_id="t1")
    with pytest.raises(WorkspaceNotFoundError):
        service.projects.create(org.id, other_ws.id, "P", tenant_id="t1")
    project = service.projects.create(org.id, ws.id, "P", tenant_id="t1")
    with pytest.raises(ProjectAlreadyExistsError):
        service.projects.create(org.id, ws.id, "P", tenant_id="t1")
    with pytest.raises(ValueError):
        service.projects.create(org.id, ws.id, "x" * 100, tenant_id="t1")
    with pytest.raises(ProjectNotFoundError):
        service.projects.get(org.id, ws.id, "proj_missing", "t1")
    with pytest.raises(ProjectNotFoundError):
        service.projects.update(org.id, ws.id, "proj_missing", tenant_id="t1")
    with pytest.raises(OrganizationNotFoundError):
        service.projects.delete(org.id, ws.id, project.id, tenant_id="t2")
    assert service.projects.delete(org.id, ws.id, project.id, "t1") is True


def test_project_archived_org_and_workspace():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u1", tenant_id="t1")
    service.organizations.archive("t1", org.id)
    with pytest.raises(OrganizationArchivedError):
        service.projects.create(org.id, ws.id, "P", tenant_id="t1")
    service.organizations.restore("t1", org.id)
    service.workspaces.archive(org.id, ws.id, "t1")
    with pytest.raises(WorkspaceArchivedError):
        service.projects.create(org.id, ws.id, "P", tenant_id="t1")


def test_project_list_for_organization():
    service, org = make_org()
    ws1 = service.workspaces.create(org.id, "W1", "u1", tenant_id="t1")
    ws2 = service.workspaces.create(org.id, "W2", "u1", tenant_id="t1")
    service.projects.create(org.id, ws1.id, "P1", tenant_id="t1")
    service.projects.create(org.id, ws2.id, "P2", tenant_id="t1")
    service.projects.create(org.id, ws2.id, "P3", tenant_id="t1")
    assert [p.name for p in service.projects.list_for_organization(org.id, "t1")] == ["P1", "P2", "P3"]
    other_org = service.organizations.create("t1", "Other", "u2")
    assert service.projects.list_for_organization(other_org.id, "t1") == []


def test_project_async():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u1", tenant_id="t1")
    p = run(service.projects.create_async(org.id, ws.id, "P", tenant_id="t1"))
    run(service.projects.update_async(org.id, ws.id, p.id, tenant_id="t1", name="P2"))
    assert [x.name for x in run(service.projects.list_async(org.id, ws.id, "t1"))] == ["P2"]
    assert len(run(service.projects.list_async(org.id, tenant_id="t1"))) == 1
    assert run(service.projects.delete_async(org.id, ws.id, p.id, "t1")) is True


# ---------------------------------------------------------------- invitations

def test_invitation_flow():
    service, org = make_org()
    invitation = service.invitations.create(org.id, "bob@example.com", role="member", tenant_id="t1", invited_by="u_owner")
    assert invitation.id.startswith("inv_")
    assert invitation.status == InvitationStatus.PENDING
    accepted = service.invitations.accept(invitation.token, "u_bob")
    assert accepted.status == InvitationStatus.ACCEPTED
    assert accepted.accepted_by == "u_bob"
    assert service.members.is_member(org.id, "u_bob") is True
    assert service.members.get_member(org.id, "u_bob").role == MemberRole.MEMBER
    assert len(service.invitations.list(org.id, "t1")) == 1
    assert len(service.invitations.list(org.id, "t1", status="accepted")) == 1


def test_invitation_accept_existing_member():
    service, org = make_org()
    service.members.add_member(org.id, "u_bob", tenant_id="t1", role="admin")
    invitation = service.invitations.create(org.id, "bob@example.com", tenant_id="t1")
    service.invitations.accept(invitation.token, "u_bob")
    assert service.members.get_member(org.id, "u_bob").role == MemberRole.ADMIN
    assert len(service.members.list_members(org.id, "t1")) == 2


def test_invitation_errors():
    service, org = make_org()
    invitation = service.invitations.create(org.id, "a@b.io", tenant_id="t1")
    with pytest.raises(InvitationNotFoundError):
        service.invitations.accept("no_such_token", "u1")
    with pytest.raises(InvitationAlreadyAcceptedError):
        service.invitations.accept(invitation.token, "u1")
        service.invitations.accept(invitation.token, "u2")
    revoked = service.invitations.create(org.id, "c@d.io", tenant_id="t1")
    service.invitations.revoke(revoked.token, "t1")
    assert revoked.status == InvitationStatus.REVOKED
    with pytest.raises(InvitationNotFoundError):
        service.invitations.accept(revoked.token, "u1")
    with pytest.raises(InvitationNotFoundError):
        service.invitations.revoke("no_such_token", "t1")
    with pytest.raises(InvitationNotFoundError):
        service.invitations.revoke(revoked.token, "t1")
    with pytest.raises(OrganizationNotFoundError):
        service.invitations.create("org_missing", "a@b.io", tenant_id="t1")
    with pytest.raises(OrganizationNotFoundError):
        service.invitations.revoke(invitation.token, "t2")
    with pytest.raises(OrganizationNotFoundError):
        service.invitations.list("org_missing", "t1")
    with pytest.raises(ValueError):
        service.invitations.create(org.id, "not-an-email", tenant_id="t1")
    with pytest.raises(ValueError):
        service.invitations.create(org.id, "", tenant_id="t1")
    with pytest.raises(ValueError):
        service.invitations.create(org.id, "a@b.io", role="owner", tenant_id="t1")
    with pytest.raises(MemberRoleError):
        service.invitations.create(org.id, "a@b.io", role="nope", tenant_id="t1")
    with pytest.raises(OrganizationArchivedError):
        archived_org = service.organizations.create("t1", "Arch", "u1")
        service.organizations.archive("t1", archived_org.id)
        service.invitations.create(archived_org.id, "a@b.io", tenant_id="t1")
    with pytest.raises(InvitationNotFoundError):
        service.invitations.get_by_token("nope")


def test_invitation_expiry():
    service = make_service(config=make_config(invitation_ttl_seconds=1))
    org = service.organizations.create("t1", "A", "u1")
    invitation = service.invitations.create(org.id, "a@b.io", tenant_id="t1")
    time.sleep(1.1)
    with pytest.raises(InvitationExpiredError):
        service.invitations.accept(invitation.token, "u1")
    assert service.invitations.get_by_token(invitation.token).status == InvitationStatus.EXPIRED
    with pytest.raises(InvitationExpiredError):
        service.invitations.accept(invitation.token, "u1")


def test_invitation_limit():
    service = make_service(config=make_config(max_pending_invitations_per_org=1))
    org = service.organizations.create("t1", "A", "u1")
    first = service.invitations.create(org.id, "a@b.io", tenant_id="t1")
    with pytest.raises(InvitationLimitError):
        service.invitations.create(org.id, "c@d.io", tenant_id="t1")
    # revoking frees up the pending quota
    service.invitations.revoke(first.token, "t1")
    second = service.invitations.create(org.id, "e@f.io", tenant_id="t1")
    assert second.status == InvitationStatus.PENDING


def test_invitation_async():
    service, org = make_org()
    invitation = run(service.invitations.create_async(org.id, "a@b.io", tenant_id="t1"))
    accepted = run(service.invitations.accept_async(invitation.token, "u_a"))
    assert accepted.status == InvitationStatus.ACCEPTED
    inv2 = run(service.invitations.create_async(org.id, "c@d.io", tenant_id="t1"))
    assert run(service.invitations.revoke_async(inv2.token, "t1")) is True
    assert len(run(service.invitations.list_async(org.id, "t1"))) == 2


# ---------------------------------------------------------------- service facade

def test_service_facade():
    service, org = make_org()
    assert isinstance(service, OrganizationService)
    assert isinstance(service.guard, AccessGuard)
    ws = service.create_workspace(org.id, "W", "u_owner", tenant_id="t1")
    assert ws.id.startswith("ws_")
    member = service.add_member(org.id, "u2", tenant_id="t1", role="member")
    assert member.role == MemberRole.MEMBER
    inv = service.invite_member(org.id, "a@b.io", tenant_id="t1", invited_by="u_owner")
    assert inv.token
    team = service.create_team(org.id, "T", tenant_id="t1")
    assert team.id.startswith("team_")
    project = service.create_project(org.id, ws.id, "P", tenant_id="t1")
    assert project.id.startswith("proj_")
    metrics = service.get_metrics()
    assert metrics["events"]["organization_created"] == 1
    service.close()


def test_service_managers_wired():
    service = make_service()
    assert isinstance(service.organizations, OrganizationManager)
    assert isinstance(service.workspaces, WorkspaceManager)
    assert isinstance(service.teams, TeamManager)
    assert isinstance(service.members, MemberManager)
    assert isinstance(service.projects, ProjectManager)
    assert isinstance(service.invitations, InvitationManager)
    assert isinstance(service.config, OrganizationConfig)
    assert isinstance(service.logger, OrganizationLogger)
    assert isinstance(service.metrics, OrganizationMetricsTracker)
    assert service.audit is None


def test_service_audit_wiring():
    audit = AuditLogger(TenancyConfig(audit_enabled=True))
    service = make_service(audit=audit)
    org = service.organizations.create("t1", "Audited", "u1")
    assert audit.count() >= 1
    actions = [e.action for e in audit.list()]
    assert "org.created" in actions
    service.organizations.archive("t1", org.id)
    assert "org.archived" in [e.action for e in audit.list()]


def test_audit_event_swallows_errors():
    class BoomAudit:
        def record(self, **kwargs):
            raise RuntimeError("audit down")
    service = make_service(audit=BoomAudit())
    org = service.organizations.create("t1", "Resilient", "u1")
    assert org.id
    service.members.add_member(org.id, "u2", tenant_id="t1")
    assert service.members.is_member(org.id, "u2")


def test_standalone_manager_constructors():
    cfg = make_config()
    guard = AccessGuard()
    orgs = OrganizationRepository()
    mems = MemberRepository()
    org_manager = OrganizationManager(
        organizations=orgs, member_repository=mems, guard=guard, config=cfg
    )
    ws_manager = create_workspace_manager(
        organizations=org_manager, members=MemberManager(members=mems, organizations=orgs, guard=guard, config=cfg), config=cfg
    )
    team_manager = create_team_manager(organizations=orgs, config=cfg)
    project_manager = create_project_manager(organizations=orgs, config=cfg)
    assert isinstance(org_manager.repository, OrganizationRepository)
    assert isinstance(org_manager.members, MemberManager)
    assert isinstance(ws_manager.repository, WorkspaceRepository)
    assert isinstance(team_manager.repository, TeamRepository)
    assert isinstance(project_manager.repository, ProjectRepository)
    inv_manager = InvitationManager(organizations=orgs, members=org_manager.members, config=cfg)
    assert isinstance(inv_manager.repository, InvitationRepository)


def test_workspace_without_org_dependency():
    manager = WorkspaceManager(config=make_config())
    with pytest.raises(OrganizationNotFoundError):
        manager.create("org_1", "W", "u1", tenant_id="t1")


def test_workspace_transfer_without_member_manager():
    service, org = make_org()
    ws = service.workspaces.create(org.id, "W", "u1", tenant_id="t1")
    manager = WorkspaceManager(
        workspaces=service.workspaces.repository,
        organizations=service.organizations,
        config=make_config(),
    )
    transferred = manager.transfer(org.id, ws.id, "someone", tenant_id="t1")
    assert transferred.owner_user_id == "someone"


def test_member_manager_without_org_dependency():
    manager = MemberManager(config=make_config())
    with pytest.raises(OrganizationNotFoundError):
        manager.list_members("org_1", "t1")


def test_invitation_accept_without_member_manager():
    repo = InvitationRepository()
    orgs = OrganizationRepository()
    manager = InvitationManager(invitations=repo, organizations=orgs, config=make_config())
    org = orgs.create(Organization(id="org_1", tenant_id="t1", name="A", slug="a", owner_user_id="u1"))
    invitation = manager.create(org.id, "a@b.io", tenant_id="t1")
    accepted = manager.accept(invitation.token, "u_x")
    assert accepted.status == InvitationStatus.ACCEPTED
    assert manager.get_by_token(invitation.token).accepted_by == "u_x"


def test_factories_and_edge_paths():
    cfg = make_config()
    guard = AccessGuard()
    orgs = OrganizationRepository()
    mems = MemberRepository()
    member_manager = create_member_manager(members=mems, organizations=orgs, guard=guard, config=cfg)
    assert isinstance(member_manager.repository, MemberRepository)
    inv_manager = create_invitation_manager(invitations=InvitationRepository(), organizations=orgs, config=cfg)
    assert isinstance(inv_manager.repository, InvitationRepository)
    org_manager = create_organization_manager(organizations=orgs, member_repository=mems, config=cfg)
    assert isinstance(org_manager.repository, OrganizationRepository)
    assert isinstance(org_manager.members, MemberManager)

    service, org = make_org()
    ws = service.create_workspace(org.id, "W", "u_owner", tenant_id="t1")
    service.create_project(org.id, ws.id, "P", tenant_id="t1")

    facade_org = service.create_organization("t2", "Facade", "u_f")
    assert facade_org.tenant_id == "t2"
    assert service.organizations.get("t2", facade_org.id).name == "Facade"

    for repo in (
        service.organizations.repository,
        service.workspaces.repository,
        service.teams.repository,
        service.members.repository,
        service.projects.repository,
        service.invitations.repository,
    ):
        assert isinstance(repo.list_all(), list)

    assert service.organizations.restore("t1", org.id) is org
    assert service.organizations.transfer_ownership(make_principal("u_owner"), org.id, "u_owner", "t1").owner_user_id == "u_owner"

    with pytest.raises(MemberNotFoundError):
        service.members.add_member(org.id, "u2", tenant_id="t1", role="member", actor=make_principal("u_who"))
    service.members.add_member(org.id, "u2", tenant_id="t1", role="member")
    with pytest.raises(MemberNotFoundError):
        service.members.remove_member(org.id, "u2", tenant_id="t1", actor=make_principal("u_who"))
    with pytest.raises(MemberNotFoundError):
        service.members.set_role(org.id, "u2", "admin", tenant_id="t1", actor=make_principal("u_who"))
    service.members.set_role(org.id, "u2", "admin", tenant_id="t1", actor=make_principal("u_owner"))
    service.members.remove_member(org.id, "u2", tenant_id="t1", actor=make_principal("u_owner"))

    with pytest.raises(ProjectNotFoundError):
        service.projects.delete(org.id, ws.id, "proj_missing", "t1")

    bare = orgs.create(Organization(id="org_bare", tenant_id="t1", name="Bare", slug="bare", owner_user_id="u_owner"))
    org_manager.members.add_member(bare.id, "u_actor", tenant_id="t1", role="owner")
    org_manager.members.add_member(bare.id, "u_newbie", tenant_id="t1", role="member")
    assert org_manager.transfer_ownership(make_principal("u_actor"), bare.id, "u_actor", "t1").owner_user_id == "u_owner"
    assert org_manager.transfer_ownership(make_principal("u_actor"), bare.id, "u_newbie", "t1").owner_user_id == "u_newbie"

    limited = make_service(config=make_config(max_projects_per_workspace=1))
    org2 = limited.organizations.create("t1", "B", "u1")
    ws2 = limited.workspaces.create(org2.id, "W2", "u1", tenant_id="t1")
    limited.projects.create(org2.id, ws2.id, "P1", tenant_id="t1")
    with pytest.raises(ValueError):
        limited.projects.create(org2.id, ws2.id, "P2", tenant_id="t1")


def test_failing_audit_is_silently_swallowed():
    def failing_audit(**kwargs):
        raise RuntimeError("audit backend down")

    service, org = make_org(service=make_service(audit=failing_audit))
    service.organizations.create("t1", "B", "u1")
    service.workspaces.create(org.id, "W", "u_owner", tenant_id="t1")
    service.members.add_member(org.id, "u2", tenant_id="t1", role="member")
    service.teams.create(org.id, "T", tenant_id="t1")
    service.invitations.create(org.id, "a@b.io", tenant_id="t1")
    ws = service.workspaces.create(org.id, "W2", "u_owner", tenant_id="t1")
    service.projects.create(org.id, ws.id, "P", tenant_id="t1")
