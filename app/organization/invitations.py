from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

from .access import validate_member_role
from .config import OrganizationConfig
from .exceptions import (
    InvitationAlreadyAcceptedError,
    InvitationExpiredError,
    InvitationLimitError,
    InvitationNotFoundError,
    MemberNotFoundError,
    OrganizationArchivedError,
    OrganizationNotFoundError,
)
from .logging import OrganizationLogger
from .members import MemberManager
from .models import Invitation, InvitationStatus, MemberRole, Organization
from .repository import InvitationRepository, OrganizationRepository
from .statistics import OrganizationMetricsTracker


class InvitationManager:
    def __init__(
        self,
        invitations: InvitationRepository | None = None,
        organizations: OrganizationRepository | None = None,
        members: MemberManager | None = None,
        config: OrganizationConfig | None = None,
        logger: OrganizationLogger | None = None,
        metrics: OrganizationMetricsTracker | None = None,
        audit: Any | None = None,
    ):
        self._invitations = invitations or InvitationRepository()
        self._organizations = organizations or OrganizationRepository()
        self._members = members
        self._config = config or OrganizationConfig()
        self._logger = logger or OrganizationLogger()
        self._metrics = metrics or OrganizationMetricsTracker(self._config)
        self._audit = audit

    @property
    def repository(self) -> InvitationRepository:
        return self._invitations

    def _audit_event(self, action: str, tenant_id: str, actor: str, **details: Any) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(action=action, tenant_id=tenant_id, actor=actor, resource="invitations", details=details)
        except Exception:
            pass

    def _get_org(self, organization_id: str, tenant_id: str) -> Organization:
        org = self._organizations.get(organization_id)
        if org is None or org.tenant_id != tenant_id:
            raise OrganizationNotFoundError(organization_id)
        return org

    def create(
        self,
        organization_id: str,
        email: str,
        role: str = "member",
        tenant_id: str = "",
        invited_by: str = "",
        ttl: int | None = None,
    ) -> Invitation:
        org = self._get_org(organization_id, tenant_id)
        if not org.is_active:
            raise OrganizationArchivedError(organization_id)
        role = validate_member_role(role)
        if role == "owner":
            raise ValueError("Owner invitations are not allowed; transfer ownership instead")
        if not email or "@" not in email:
            raise ValueError(f"Invalid email {email!r}")
        pending = self._invitations.count_pending_for_organization(organization_id)
        if pending >= self._config.max_pending_invitations_per_org:
            raise InvitationLimitError(organization_id, self._config.max_pending_invitations_per_org)
        invitation = Invitation(
            id=f"inv_{uuid.uuid4().hex[:16]}",
            organization_id=organization_id,
            tenant_id=org.tenant_id,
            email=email,
            role=MemberRole(role),
            invited_by=invited_by,
            token=secrets.token_urlsafe(24),
            expires_at=time.time() + (ttl if ttl is not None else self._config.invitation_ttl_seconds),
        )
        self._invitations.create(invitation)
        self._metrics.record("invitation_created", organization_id)
        self._logger.log_event(
            "invitation_created",
            tenant_id=org.tenant_id,
            organization_id=organization_id,
            user_id=invited_by,
            email=email,
        )
        self._audit_event("org.invitation_created", org.tenant_id, invited_by, email=email, role=role)
        return invitation

    def accept(self, token: str, user_id: str) -> Invitation:
        invitation = self._invitations.get_by_token(token)
        if invitation is None:
            raise InvitationNotFoundError(token)
        if invitation.status == InvitationStatus.ACCEPTED:
            raise InvitationAlreadyAcceptedError(token)
        if invitation.status == InvitationStatus.REVOKED:
            raise InvitationNotFoundError(token)
        if invitation.status == InvitationStatus.EXPIRED or invitation.is_expired:
            if invitation.status == InvitationStatus.PENDING:
                invitation.status = InvitationStatus.EXPIRED
                self._invitations.update(invitation)
            raise InvitationExpiredError(token)
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = time.time()
        invitation.accepted_by = user_id
        self._invitations.update(invitation)
        if self._members is not None and not self._members.is_member(invitation.organization_id, user_id):
            self._members.add_member(
                organization_id=invitation.organization_id,
                user_id=user_id,
                tenant_id=invitation.tenant_id,
                role=invitation.role.value,
            )
        self._metrics.record("invitation_accepted", invitation.organization_id)
        self._audit_event("org.invitation_accepted", invitation.tenant_id, user_id, organization_id=invitation.organization_id)
        return invitation

    def revoke(self, token: str, tenant_id: str = "") -> bool:
        invitation = self._invitations.get_by_token(token)
        if invitation is None:
            raise InvitationNotFoundError(token)
        org = self._get_org(invitation.organization_id, tenant_id)
        if invitation.status != InvitationStatus.PENDING:
            raise InvitationNotFoundError(token)
        invitation.status = InvitationStatus.REVOKED
        self._invitations.update(invitation)
        self._metrics.record("invitation_revoked", invitation.organization_id)
        self._audit_event("org.invitation_revoked", org.tenant_id, "", token=token)
        return True

    def get_by_token(self, token: str) -> Invitation:
        invitation = self._invitations.get_by_token(token)
        if invitation is None:
            raise InvitationNotFoundError(token)
        return invitation

    def list(self, organization_id: str, tenant_id: str = "", status: str = "") -> list[Invitation]:
        self._get_org(organization_id, tenant_id)
        return self._invitations.list_for_organization(organization_id, status)

    async def create_async(self, organization_id: str, email: str, role: str = "member", tenant_id: str = "", invited_by: str = "", ttl: int | None = None) -> Invitation:
        return self.create(organization_id, email, role, tenant_id, invited_by, ttl)

    async def accept_async(self, token: str, user_id: str) -> Invitation:
        return self.accept(token, user_id)

    async def revoke_async(self, token: str, tenant_id: str = "") -> bool:
        return self.revoke(token, tenant_id)

    async def list_async(self, organization_id: str, tenant_id: str = "", status: str = "") -> list[Invitation]:
        return self.list(organization_id, tenant_id, status)


def create_invitation_manager(
    invitations: InvitationRepository | None = None,
    organizations: OrganizationRepository | None = None,
    members: MemberManager | None = None,
    config: OrganizationConfig | None = None,
    logger: OrganizationLogger | None = None,
    metrics: OrganizationMetricsTracker | None = None,
    audit: Any | None = None,
) -> InvitationManager:
    return InvitationManager(
        invitations=invitations,
        organizations=organizations,
        members=members,
        config=config,
        logger=logger,
        metrics=metrics,
        audit=audit,
    )
