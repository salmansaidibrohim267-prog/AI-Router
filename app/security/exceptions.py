"""Security & Compliance exception hierarchy."""

from __future__ import annotations


class SecurityError(Exception):
    """Base error for the security framework."""


class SecretError(SecurityError):
    """Base error for secret management."""


class SecretNotFoundError(SecretError):
    """Requested secret does not exist."""


class SecretBackendError(SecretError):
    """A secret backend failed to fulfil an operation."""


class EncryptionError(SecurityError):
    """Encryption operation failed."""


class DecryptionError(SecurityError):
    """Decryption failed (bad key, tag, or ciphertext)."""


class KeyManagementError(SecurityError):
    """Key lifecycle operation failed."""


class KeyRevokedError(KeyManagementError):
    """Operation attempted with a revoked key."""


class KeyExpiredError(KeyManagementError):
    """Operation attempted with an expired key."""


class KeyVersionError(KeyManagementError):
    """Unknown or inactive key version."""


class PolicyError(SecurityError):
    """Base error for policy evaluation."""


class AuthenticationError(PolicyError):
    """Authentication failed."""


class AuthorizationError(PolicyError):
    """Authorization denied."""


class TenantValidationError(PolicyError):
    """Tenant validation failed."""


class SessionValidationError(PolicyError):
    """Session validation failed."""


class PolicyEvaluationError(PolicyError):
    """Policy engine could not evaluate a request."""


class AuditError(SecurityError):
    """Audit log operation failed."""


class AuditIntegrityError(AuditError):
    """Audit chain integrity verification failed."""


class PrivacyError(SecurityError):
    """Privacy operation failed."""


class DataSubjectRequestError(PrivacyError):
    """A data subject request could not be fulfilled."""


class ComplianceError(SecurityError):
    """Compliance assessment failed."""


class ThreatError(SecurityError):
    """Threat detection or incident workflow failed."""


class IncidentError(ThreatError):
    """Incident workflow transition failed."""


class MonitoringError(SecurityError):
    """Security monitoring integration failed."""
