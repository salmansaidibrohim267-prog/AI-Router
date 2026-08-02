"""Shared models for the security framework."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


def generate_id(prefix: str = "sec") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class SecretKind(str, Enum):
    OPAQUE = "opaque"
    CREDENTIAL = "credential"
    CERTIFICATE = "certificate"
    API_KEY = "api_key"
    DATABASE = "database"
    TOKEN = "token"


class SecretStatus(str, Enum):
    ACTIVE = "active"
    ROTATING = "rotating"
    ROTATED = "rotated"
    REVOKED = "revoked"
    EXPIRED = "expired"


class EncryptionAlgorithm(str, Enum):
    AES_256_GCM = "aes-256-gcm"
    AES_256_CBC = "aes-256-cbc"


class KeyPurpose(str, Enum):
    ENCRYPTION = "encryption"
    SIGNING = "signing"
    TOKEN = "token"
    DATABASE = "database"


class KeyStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    RETIRED = "retired"
    REVOKED = "revoked"
    EXPIRED = "expired"
    DESTROYED = "destroyed"


class AuthMethod(str, Enum):
    PASSWORD = "password"
    TOTP = "totp"
    API_KEY = "api_key"
    OAUTH = "oauth"
    SAML = "saml"
    CLIENT_CERTIFICATE = "client_certificate"
    MFA = "mfa"


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AuditEventType(str, Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    SECRET = "secret"
    CRYPTO = "crypto"
    POLICY = "policy"
    PRIVACY = "privacy"
    INCIDENT = "incident"
    COMPLIANCE = "compliance"
    ADMIN = "admin"


class PIIKind(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    NAME = "name"
    DATE_OF_BIRTH = "date_of_birth"
    ADDRESS = "address"


class DataSubjectRequestType(str, Enum):
    ACCESS = "access"
    ERASURE = "erasure"
    RECTIFICATION = "rectification"
    PORTABILITY = "portability"


class DataSubjectRequestStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FULFILLED = "fulfilled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ComplianceFramework(str, Enum):
    SOC2 = "soc2"
    ISO27001 = "iso27001"
    GDPR = "gdpr"
    CCPA = "ccpa"


class ControlStatus(str, Enum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    NOT_IMPLEMENTED = "not_implemented"
    NOT_APPLICABLE = "not_applicable"


class ThreatSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatType(str, Enum):
    BRUTE_FORCE = "brute_force"
    CREDENTIAL_STUFFING = "credential_stuffing"
    TOKEN_REPLAY = "token_replay"
    ANOMALY = "anomaly"
    DATA_EXFILTRATION = "data_exfiltration"
    MALWARE = "malware"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


# -- secrets ------------------------------------------------------------------


@dataclass
class Secret:
    id: str
    name: str
    kind: SecretKind = SecretKind.OPAQUE
    value: str = ""
    version: int = 1
    status: SecretStatus = SecretStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    rotated_at: float = 0.0
    expires_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "version": self.version,
            "status": self.status.value,
            "created_at": self.created_at,
            "rotated_at": self.rotated_at,
            "expires_at": self.expires_at,
            "metadata": dict(self.metadata),
        }


# -- encryption keys -------------------------------------------------------------


@dataclass
class EncryptionKey:
    id: str
    purpose: KeyPurpose = KeyPurpose.ENCRYPTION
    algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM
    status: KeyStatus = KeyStatus.ACTIVE
    material: bytes = b""
    version: int = 1
    created_at: float = field(default_factory=time.time)
    rotated_at: float = 0.0
    expires_at: float = 0.0
    revoked_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "purpose": self.purpose.value,
            "algorithm": self.algorithm.value,
            "status": self.status.value,
            "version": self.version,
            "created_at": self.created_at,
            "rotated_at": self.rotated_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "metadata": dict(self.metadata),
        }

    def is_revoked(self) -> bool:
        return self.status == KeyStatus.REVOKED

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return bool(self.expires_at and now >= self.expires_at)

    def usable(self, now: float | None = None) -> bool:
        return not self.is_revoked() and not self.is_expired(now) and bool(self.material)


# -- envelope encryption ---------------------------------------------------------


@dataclass
class Envelope:
    key_id: str
    key_version: int
    algorithm: str
    iv: str
    tag: str
    ciphertext: str
    wrapped_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "key_version": self.key_version,
            "algorithm": self.algorithm,
            "iv": self.iv,
            "tag": self.tag,
            "ciphertext": self.ciphertext,
            "wrapped_key": self.wrapped_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Envelope":
        return cls(
            key_id=data.get("key_id", ""),
            key_version=int(data.get("key_version", 1)),
            algorithm=data.get("algorithm", "aes-256-gcm"),
            iv=data.get("iv", ""),
            tag=data.get("tag", ""),
            ciphertext=data.get("ciphertext", ""),
            wrapped_key=data.get("wrapped_key", ""),
        )


# -- zero trust -------------------------------------------------------------------


@dataclass
class Subject:
    id: str
    tenant: str = "default"
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    id: str
    subject_id: str
    tenant: str = "default"
    issued_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: SessionStatus = SessionStatus.ACTIVE
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject_id": self.subject_id,
            "tenant": self.tenant,
            "issued_at": self.issued_at,
            "last_seen": self.last_seen,
            "expires_at": self.expires_at,
            "status": self.status.value,
            "metadata": dict(self.metadata),
        }


@dataclass
class AuthContext:
    subject: Subject
    method: AuthMethod = AuthMethod.PASSWORD
    token_id: str = ""
    session: Session | None = None
    device: str = ""
    ip_address: str = ""
    mfa_verified: bool = False


@dataclass
class Policy:
    id: str
    name: str
    effect: PolicyEffect = PolicyEffect.ALLOW
    subjects: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    conditions: dict[str, Any] = field(default_factory=dict)
    priority: int = 0

    def matches(self, subject: Subject, action: str, resource: str) -> bool:
        if self.subjects and subject.id not in self.subjects:
            return False
        if self.resources and not any(resource == r or resource.startswith(r.rstrip("*")) for r in self.resources):
            return False
        if self.actions and action not in self.actions:
            return False
        return True


@dataclass
class PolicyResult:
    allowed: bool
    decision: Decision = Decision.DENY
    reasons: list[str] = field(default_factory=list)
    matched_policy: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "matched_policy": self.matched_policy,
        }


# -- audit -----------------------------------------------------------------------


@dataclass
class AuditRecord:
    seq: int
    event: str
    actor: str
    action: str
    resource: str
    outcome: str
    severity: AuditSeverity = AuditSeverity.INFO
    event_type: AuditEventType = AuditEventType.ADMIN
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    previous_hash: str = ""
    signature: str = ""
    hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "event": self.event,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "outcome": self.outcome,
            "severity": self.severity.value,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
            "previous_hash": self.previous_hash,
            "signature": self.signature,
            "hash": self.hash,
        }


# -- privacy ----------------------------------------------------------------------


@dataclass
class PIIField:
    kind: PIIKind
    location: tuple[int, int]
    confidence: float = 1.0
    value: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "location": list(self.location),
            "confidence": self.confidence,
            "value": self.value,
        }


@dataclass
class DataSubjectRequest:
    id: str
    subject: str
    request_type: DataSubjectRequestType = DataSubjectRequestType.ACCESS
    status: DataSubjectRequestStatus = DataSubjectRequestStatus.PENDING
    created_at: float = field(default_factory=time.time)
    fulfilled_at: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "request_type": self.request_type.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "fulfilled_at": self.fulfilled_at,
            "result": dict(self.result),
        }


# -- compliance -------------------------------------------------------------------


@dataclass
class Control:
    id: str
    name: str
    description: str = ""
    status: ControlStatus = ControlStatus.NOT_IMPLEMENTED
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "evidence": dict(self.evidence),
        }


@dataclass
class Finding:
    id: str
    severity: ThreatSeverity = ThreatSeverity.MEDIUM
    description: str = ""
    remediation: str = ""
    resource: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "description": self.description,
            "remediation": self.remediation,
            "resource": self.resource,
        }


@dataclass
class ComplianceReport:
    framework: ComplianceFramework
    controls: list[Control] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    def status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for control in self.controls:
            counts[control.status.value] = counts.get(control.status.value, 0) + 1
        return counts

    def readiness(self) -> float:
        total = len(self.controls)
        if not total:
            return 0.0
        implemented = sum(1 for c in self.controls if c.status == ControlStatus.IMPLEMENTED)
        return round(implemented / total * 100.0, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework": self.framework.value,
            "controls": [c.to_dict() for c in self.controls],
            "findings": [f.to_dict() for f in self.findings],
            "generated_at": self.generated_at,
            "status": self.status(),
            "readiness": self.readiness(),
        }


# -- threat -----------------------------------------------------------------------


@dataclass
class ThreatEvent:
    id: str
    threat_type: ThreatType = ThreatType.ANOMALY
    severity: ThreatSeverity = ThreatSeverity.LOW
    source: str = ""
    target: str = ""
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "threat_type": self.threat_type.value,
            "severity": self.severity.value,
            "source": self.source,
            "target": self.target,
            "timestamp": self.timestamp,
            "details": dict(self.details),
        }


@dataclass
class Incident:
    id: str
    severity: ThreatSeverity = ThreatSeverity.MEDIUM
    status: IncidentStatus = IncidentStatus.OPEN
    threat_events: list[ThreatEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    resolved_at: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "status": self.status.value,
            "threat_events": [e.to_dict() for e in self.threat_events],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "summary": self.summary,
        }


# -- monitoring --------------------------------------------------------------------


@dataclass
class SecurityAlert:
    id: str
    severity: ThreatSeverity = ThreatSeverity.MEDIUM
    message: str = ""
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "message": self.message,
            "source": self.source,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


# -- repository helper -----------------------------------------------------------

EvidenceProvider = Callable[[str, str], Any]
"""evidence_provider(control_id, framework) -> evidence payload or None"""
