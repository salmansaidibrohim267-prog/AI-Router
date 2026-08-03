"""Zero Trust policy enforcement: authentication, authorization, tenant and
session validation, and policy evaluation.

The ``ZeroTrustEnforcer`` runs the deny-by-default pipeline:

1. authenticate the presented credential,
2. authorize the subject against the policy set (first-match by priority),
3. validate the tenant binding,
4. validate the session (age, idle time, status),
5. evaluate the final decision.

Account lockout counters are tracked per subject.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .config import SecurityConfig
from .exceptions import (
    AuthenticationError,
    PolicyEvaluationError,
    SessionValidationError,
    TenantValidationError,
)
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import (
    AuthContext,
    AuthMethod,
    Decision,
    Policy,
    PolicyEffect,
    PolicyResult,
    Session,
    SessionStatus,
    Subject,
    generate_id,
)

CredentialValidator = Callable[[AuthContext], bool]
"""validator(auth_context) -> authenticated?"""

MfaValidator = Callable[[AuthContext], bool]
"""mfa(auth_context) -> mfa verified?"""


class ZeroTrustEnforcer:
    """Deny-by-default policy pipeline."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self._policies: list[Policy] = []
        self._credential_validators: dict[AuthMethod, CredentialValidator] = {}
        self._mfa_validators: dict[AuthMethod, MfaValidator] = {}
        self._sessions: dict[str, Session] = {}
        self._failed_attempts: dict[str, list[float]] = {}
        self._lockout_until: dict[str, float] = {}

    # -- registration ----------------------------------------------------------

    def add_policy(self, policy: Policy) -> None:
        self._policies.append(policy)

    def add_policies(self, policies: list[Policy]) -> None:
        self._policies.extend(policies)

    def register_credential_validator(self, method: AuthMethod, validator: CredentialValidator) -> None:
        self._credential_validators[method] = validator

    def register_mfa_validator(self, method: AuthMethod, validator: MfaValidator) -> None:
        self._mfa_validators[method] = validator

    def policies(self) -> list[Policy]:
        return list(self._policies)

    # -- sessions --------------------------------------------------------------

    def create_session(self, subject: Subject, ttl: int | None = None) -> Session:
        ttl = ttl if ttl is not None else self.config.max_session_age_seconds
        session = Session(
            id=generate_id("session"),
            subject_id=subject.id,
            tenant=subject.tenant,
            expires_at=time.time() + ttl,
        )
        self._sessions[session.id] = session
        self.metrics.record("sessions_created", component="zero_trust")
        return session

    def get_session(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.status == SessionStatus.ACTIVE and session.expires_at and time.time() >= session.expires_at:
            session.status = SessionStatus.EXPIRED
        return session

    def revoke_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.status = SessionStatus.REVOKED
        self.metrics.record("sessions_revoked", component="zero_trust")
        return True

    def revoke_all_for_subject(self, subject_id: str) -> int:
        count = 0
        for session in self._sessions.values():
            if session.subject_id == subject_id and session.status == SessionStatus.ACTIVE:
                session.status = SessionStatus.REVOKED
                count += 1
        return count

    # -- lockout ---------------------------------------------------------------

    def is_locked_out(self, subject_id: str) -> bool:
        until = self._lockout_until.get(subject_id, 0.0)
        if until > time.time():
            return True
        if until:
            self._lockout_until.pop(subject_id, None)
        return False

    def record_failure(self, subject_id: str) -> int:
        now = time.time()
        attempts = [ts for ts in self._failed_attempts.get(subject_id, []) if now - ts <= 60]
        attempts.append(now)
        self._failed_attempts[subject_id] = attempts
        if len(attempts) >= self.config.max_failed_attempts:
            self._lockout_until[subject_id] = now + self.config.lockout_seconds
            self._failed_attempts[subject_id] = []
            self.metrics.record("account_lockouts", component="zero_trust")
            self.logger.log_event("account_locked", subject=subject_id, seconds=self.config.lockout_seconds)
        return len(attempts)

    def reset_failures(self, subject_id: str) -> None:
        self._failed_attempts.pop(subject_id, None)
        self._lockout_until.pop(subject_id, None)

    # -- pipeline --------------------------------------------------------------

    def authenticate(
        self,
        subject: Subject,
        method: AuthMethod = AuthMethod.PASSWORD,
        credential: Any = None,
        **kwargs: Any,
    ) -> AuthContext:
        """Step 1: verify the credential. Raises AuthenticationError on failure."""
        if self.is_locked_out(subject.id):
            raise AuthenticationError(f"subject {subject.id} is locked out")
        validator = self._credential_validators.get(method)
        if validator is None:
            raise AuthenticationError(f"no credential validator for {method.value}")
        context = AuthContext(
            subject=subject,
            method=method,
            device=kwargs.get("device", ""),
            ip_address=kwargs.get("ip_address", ""),
        )
        if not validator(context):
            attempts = self.record_failure(subject.id)
            self.metrics.record("authentication_failures", component="zero_trust")
            self.logger.log_event("authentication_failed", subject=subject.id, method=method.value, attempts=attempts)
            raise AuthenticationError(f"invalid credential for {subject.id}")
        self.reset_failures(subject.id)
        if self.config.require_mfa:
            self._require_mfa(context)
        context.session = self.create_session(subject)
        self.metrics.record("authentications", component="zero_trust")
        self.logger.log_event("authenticated", subject=subject.id, method=method.value)
        return context

    def _require_mfa(self, context: AuthContext) -> None:
        validator = self._mfa_validators.get(context.method)
        if validator is None:
            raise AuthenticationError(f"mfa required but no validator for {context.method.value}")
        if not validator(context):
            self.metrics.record("mfa_failures", component="zero_trust")
            raise AuthenticationError(f"mfa failed for {context.subject.id}")
        context.mfa_verified = True

    def authorize(
        self,
        context: AuthContext,
        action: str,
        resource: str,
        tenant: str | None = None,
    ) -> PolicyResult:
        """Steps 2-5: policy, tenant, session and final decision."""
        if tenant is not None and tenant != context.subject.tenant:
            raise TenantValidationError(f"tenant mismatch: context {context.subject.tenant} != requested {tenant}")
        if context.session is not None:
            self._validate_session(context.session)
        result = self._evaluate_policies(context.subject, action, resource)
        if self.config.zero_trust_enforce and not result.allowed:
            self.metrics.record("authorization_denials", component="zero_trust")
            self.logger.log_event(
                "authorization_denied",
                subject=context.subject.id,
                action=action,
                resource=resource,
                reasons=result.reasons,
            )
        else:
            self.metrics.record("authorizations", component="zero_trust")
        return result

    def check(
        self,
        subject: Subject,
        action: str,
        resource: str,
        session: Session | None = None,
        tenant: str | None = None,
    ) -> PolicyResult:
        """Stateless convenience evaluation (no authentication)."""
        if tenant is not None and tenant != subject.tenant:
            raise TenantValidationError(f"tenant mismatch: subject {subject.tenant} != requested {tenant}")
        if session is not None:
            self._validate_session(session)
        return self._evaluate_policies(subject, action, resource)

    def _validate_session(self, session: Session) -> None:
        now = time.time()
        if session.status == SessionStatus.REVOKED:
            raise SessionValidationError(f"session {session.id} revoked")
        if session.expires_at and now >= session.expires_at:
            session.status = SessionStatus.EXPIRED
            raise SessionValidationError(f"session {session.id} expired")
        if now - session.last_seen > self.config.session_idle_timeout_seconds:
            session.status = SessionStatus.EXPIRED
            raise SessionValidationError(f"session {session.id} idle timeout")
        session.last_seen = now

    def _evaluate_policies(self, subject: Subject, action: str, resource: str) -> PolicyResult:
        matched: Policy | None = None
        for policy in sorted(self._policies, key=lambda p: p.priority, reverse=True):
            if policy.matches(subject, action, resource):
                matched = policy
                break
        if matched is None:
            return PolicyResult(allowed=False, reasons=["no policy matched"], decision=Decision.DENY)
        if matched.effect == PolicyEffect.DENY:
            return PolicyResult(
                allowed=False,
                reasons=["matched deny policy"],
                decision=Decision.DENY,
                matched_policy=matched.id,
            )
        if matched.conditions:
            try:
                if not self._evaluate_conditions(matched.conditions, subject, action, resource):
                    return PolicyResult(
                        allowed=False,
                        reasons=["conditions not met"],
                        decision=Decision.DENY,
                        matched_policy=matched.id,
                    )
            except Exception as exc:
                raise PolicyEvaluationError(f"condition evaluation failed: {exc}") from exc
        return PolicyResult(
            allowed=True,
            decision=Decision.ALLOW,
            reasons=["matched allow policy"],
            matched_policy=matched.id,
        )

    def _evaluate_conditions(self, conditions: dict[str, Any], subject: Subject, action: str, resource: str) -> bool:
        for key, expected in conditions.items():
            if key == "role" and subject.roles:
                if expected not in subject.roles:
                    return False
            elif key == "group" and subject.groups:
                if expected not in subject.groups:
                    return False
            elif key == "tenant" and subject.tenant:
                if expected != subject.tenant:
                    return False
            elif key == "attribute" and subject.attributes:
                attr_key, attr_value = expected
                if subject.attributes.get(attr_key) != attr_value:
                    return False
            elif key == "action":
                if expected != action:
                    return False
            elif key == "resource":
                if expected != resource:
                    return False
            else:
                return False
        return True

    def status(self) -> dict[str, Any]:
        return {
            "policies": len(self._policies),
            "sessions": len(self._sessions),
            "enforce": self.config.zero_trust_enforce,
            "require_mfa": self.config.require_mfa,
            "lockouts": len(self._lockout_until),
        }


def create_zero_trust_enforcer(config: SecurityConfig | None = None, **overrides: Any) -> ZeroTrustEnforcer:
    config = config if config is not None else SecurityConfig()
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    return ZeroTrustEnforcer(config, logger, metrics)
