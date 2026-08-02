"""SecurityManager facade: wires together all security subsystems via DI.

Composes the secret manager, key manager, encryption service, zero-trust
enforcer, audit service, privacy service, compliance manager, threat detection
and monitoring into a single ``initialize()`` / ``shutdown()`` lifecycle.
"""

from __future__ import annotations

import time
from typing import Any

from .audit import AuditRepository, AuditService, create_audit_service
from .compliance import ComplianceManager, create_compliance_manager
from .config import SecurityConfig
from .crypto import EncryptionService, FieldCipher, StorageEncryption, create_encryption_service
from .exceptions import SecurityError
from .keys import KeyManager, SimulatedHSMAdapter, create_key_manager
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .monitoring import MonitoringService, create_monitoring_service
from .privacy import PIIDetector, PrivacyService, create_privacy_service
from .secrets import SecretManager, create_secret_manager
from .threat import IncidentManager, ThreatDetector, create_incident_manager, create_threat_detector
from .zero_trust import ZeroTrustEnforcer, create_zero_trust_enforcer
from .models import (
    AuditEventType,
    AuditSeverity,
    AuthContext,
    AuthMethod,
    DataSubjectRequestType,
    EncryptionAlgorithm,
    Incident,
    IncidentStatus,
    KeyPurpose,
    Policy,
    PolicyEffect,
    PolicyResult,
    SecretKind,
    Subject,
    ThreatEvent,
    ThreatSeverity,
    ThreatType,
)


class SecurityManager:
    """Facade over the complete security subsystem."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        secrets: SecretManager | None = None,
        keys: KeyManager | None = None,
        encryption: EncryptionService | None = None,
        zero_trust: ZeroTrustEnforcer | None = None,
        audit: AuditService | None = None,
        privacy: PrivacyService | None = None,
        compliance: ComplianceManager | None = None,
        threat: ThreatDetector | None = None,
        incidents: IncidentManager | None = None,
        monitoring: MonitoringService | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)

        self.secrets = secrets if secrets is not None else create_secret_manager(self.config, logger=self.logger, metrics=self.metrics)
        self.keys = keys if keys is not None else create_key_manager(self.config, logger=self.logger, metrics=self.metrics)
        if encryption is None:
            self.encryption = create_encryption_service(
                self.config, key_provider=self.keys.key_provider, logger=self.logger, metrics=self.metrics
            )
        else:
            self.encryption = encryption
        self.zero_trust = zero_trust if zero_trust is not None else create_zero_trust_enforcer(self.config, logger=self.logger, metrics=self.metrics)
        self.audit_service = audit if audit is not None else create_audit_service(self.config, logger=self.logger, metrics=self.metrics)
        self.privacy = privacy if privacy is not None else create_privacy_service(self.config, logger=self.logger, metrics=self.metrics)
        self.compliance = compliance if compliance is not None else create_compliance_manager(self.config, logger=self.logger, metrics=self.metrics)
        self.threat = threat if threat is not None else create_threat_detector(self.config, logger=self.logger, metrics=self.metrics)
        self.incidents = incidents if incidents is not None else create_incident_manager(
            self.config, detector=self.threat, logger=self.logger, metrics=self.metrics
        )
        self.monitoring = monitoring if monitoring is not None else create_monitoring_service(self.config, logger=self.logger, metrics=self.metrics)

        self._started_at = 0.0
        self._initialized = False
        self._audit_hook: Any = None

    # -- lifecycle -------------------------------------------------------------

    async def initialize(self) -> None:
        """Start the subsystems; creates the initial key if absent."""
        if self._initialized:
            return
        await self.secrets.start()
        if not self.keys.current_key().usable():
            self.keys.rotate()
        await self.monitoring.start()
        self._initialized = True
        self._started_at = time.time()
        self.metrics.record("manager_initializations", component="manager")
        self.logger.log_event("security_manager_initialized", node_id=self.config.node_id)

    async def shutdown(self) -> None:
        """Stop the subsystems in reverse order."""
        if not self._initialized:
            return
        await self.monitoring.stop()
        await self.secrets.stop()
        self._initialized = False
        self.metrics.record("manager_shutdowns", component="manager")
        self.logger.log_event("security_manager_shutdown", node_id=self.config.node_id)

    # -- secrets ---------------------------------------------------------------

    async def get_secret(self, name: str) -> Any:
        return await self.secrets.get_secret(name)

    async def set_secret(self, name: str, value: str, kind: SecretKind = SecretKind.OPAQUE) -> Any:
        return await self.secrets.set_secret(name, value, kind=kind)

    async def rotate_secret(self, name: str, new_value: str) -> Any:
        return await self.secrets.rotate_secret(name, new_value)

    # -- crypto ------------------------------------------------------------------

    def encrypt(self, plaintext: bytes) -> Any:
        envelope = self.encryption.encrypt(plaintext)
        return envelope.to_dict()

    def decrypt(self, envelope: dict[str, Any] | Any) -> bytes:
        from .models import Envelope

        if isinstance(envelope, dict):
            envelope = Envelope.from_dict(envelope)
        return self.encryption.decrypt(envelope)

    def encrypt_field(self, value: Any) -> Any:
        return FieldCipher(self.encryption).encrypt_field(value)

    def decrypt_field(self, value: Any) -> Any:
        return FieldCipher(self.encryption).decrypt_field(value)

    def encrypt_storage(self, value: str, purpose: str = "") -> Any:
        return StorageEncryption(self.encryption).encrypt_value(value, purpose=purpose)

    def decrypt_storage(self, wrapped: dict[str, Any] | str) -> str:
        return StorageEncryption(self.encryption).decrypt_value(wrapped)

    # -- zero trust ---------------------------------------------------------------

    def authenticate(self, subject: Subject, method: AuthMethod, credential: Any = None, **kwargs: Any) -> AuthContext:
        return self.zero_trust.authenticate(subject, method, credential, **kwargs)

    def authorize(self, context: AuthContext, action: str, resource: str, tenant: str | None = None) -> PolicyResult:
        return self.zero_trust.authorize(context, action, resource, tenant)

    def check(self, subject: Subject, action: str, resource: str, session: Any = None, tenant: str | None = None) -> PolicyResult:
        return self.zero_trust.check(subject, action, resource, session, tenant)

    def add_policy(self, policy: Policy) -> None:
        self.zero_trust.add_policy(policy)

    # -- audit --------------------------------------------------------------------

    def audit(
        self,
        event: str,
        actor: str,
        action: str,
        resource: str = "",
        outcome: str = "success",
        severity: AuditSeverity = AuditSeverity.INFO,
        event_type: AuditEventType = AuditEventType.ADMIN,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        record = self.audit_service.log(event, actor, action, resource, outcome, severity, event_type, metadata)
        if self._audit_hook is not None:
            self._audit_hook(record)
        return record

    def verify_audit(self) -> list[dict[str, Any]]:
        return self.audit_service.verify()

    # -- privacy ---------------------------------------------------------------------

    def detect_pii(self, text: str) -> list[Any]:
        return self.privacy.detect(text)

    def mask_pii(self, text: str, mode: str | None = None) -> Any:
        return self.privacy.mask(text, mode)

    def submit_dsar(self, subject: str, request_type: DataSubjectRequestType) -> Any:
        return self.privacy.submit_request(subject, request_type)

    def fulfill_dsar(self, request_id: str) -> Any:
        return self.privacy.fulfill_request(request_id)

    # -- compliance ----------------------------------------------------------------------

    def compliance_report(self, framework: str) -> Any:
        return self.compliance.generate_report(framework)

    def compliance_readiness(self) -> float:
        return self.compliance.readiness()

    # -- threat + incidents ------------------------------------------------------------------

    def report_threat(self, threat_type: ThreatType, source: str = "", target: str = "", details: dict[str, Any] | None = None) -> ThreatEvent:
        return self.threat.report(threat_type, source, target, details)

    def escalate_incident(self, signal: str) -> Incident:
        return self.incidents.escalate(signal)

    def resolve_incident(self, incident_id: str) -> Incident:
        return self.incidents.update_status(incident_id, IncidentStatus.RESOLVED)

    # -- monitoring -------------------------------------------------------------------------

    async def send_alert(self, message: str, severity: ThreatSeverity = ThreatSeverity.MEDIUM, source: str = "security") -> Any:
        return await self.monitoring.send_alert(message, severity, source)

    # -- status -------------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "node_id": self.config.node_id,
            "initialized": self._initialized,
            "uptime_seconds": round(time.time() - self._started_at, 1) if self._started_at else 0,
            "secrets": self.secrets.status(),
            "keys": self.keys.status(),
            "zero_trust": self.zero_trust.status(),
            "audit": self.audit_service.status(),
            "privacy": self.privacy.status(),
            "compliance": self.compliance.summary(),
            "threat": {
                "enabled": self.threat.enabled(),
                "events": len(self.threat.recent_events()),
                "incidents": self.incidents.count(),
            },
            "monitoring": self.monitoring.status(),
        }


def create_security_manager(config: SecurityConfig | None = None, **overrides: Any) -> SecurityManager:
    """DI factory for the SecurityManager (10.5-10.9 convention)."""
    config = config if config is not None else SecurityConfig()
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    keys = overrides.pop("keys", None)
    secrets = overrides.pop("secrets", None)
    zero_trust = overrides.pop("zero_trust", None)
    audit = overrides.pop("audit", None)
    privacy = overrides.pop("privacy", None)
    compliance = overrides.pop("compliance", None)
    threat = overrides.pop("threat", None)
    incidents = overrides.pop("incidents", None)
    monitoring = overrides.pop("monitoring", None)
    encryption = overrides.pop("encryption", None)
    return SecurityManager(
        config=config,
        secrets=secrets,
        keys=keys,
        encryption=encryption,
        zero_trust=zero_trust,
        audit=audit,
        privacy=privacy,
        compliance=compliance,
        threat=threat,
        incidents=incidents,
        monitoring=monitoring,
        logger=logger,
        metrics=metrics,
    )
