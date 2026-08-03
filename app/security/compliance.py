"""Compliance reporting: SOC 2, ISO 27001, GDPR and CCPA control catalogs.

Each framework ships a default control catalog with statuses derived from the
platform's live configuration, plus an evidence provider hook and readiness
scoring.
"""

from __future__ import annotations

import time
from typing import Any

from .config import SecurityConfig
from .exceptions import ComplianceError
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import (
    ComplianceFramework,
    Control,
    ControlStatus,
    EvidenceProvider,
    Finding,
    ThreatSeverity,
    generate_id,
)

_CONTROLS: dict[str, list[tuple[str, str]]] = {
    "soc2": [
        ("CC6.1", "Logical and physical access controls"),
        ("CC6.6", "Logical and physical access security against malicious code"),
        ("CC7.2", "Security event monitoring"),
        ("CC7.3", "System operations monitoring and anomalous activity"),
        ("CC8.1", "Change management and integrity"),
        ("A1.2", "Data backup and recovery"),
    ],
    "iso27001": [
        ("A.5.15", "Access control policy"),
        ("A.5.24", "Information security incident management"),
        ("A.8.24", "Cryptographic controls"),
        ("A.8.25", "Secure development lifecycle"),
        ("A.8.28", "Logging and monitoring"),
        ("A.8.10", "Information deletion"),
    ],
    "gdpr": [
        ("Art.5", "Data minimisation and purpose limitation"),
        ("Art.15", "Right of access"),
        ("Art.17", "Right to erasure"),
        ("Art.20", "Right to data portability"),
        ("Art.30", "Records of processing activities"),
        ("Art.32", "Security of processing"),
    ],
    "ccpa": [
        ("1798.110", "Right to know"),
        ("1798.105", "Right to delete"),
        ("1798.115", "Opt-out of sale"),
        ("1798.100", "Notice at collection"),
        ("1798.130", "Disclosure requirements"),
    ],
}


def _derive_status(framework: ComplianceFramework, control_id: str, config: SecurityConfig) -> ControlStatus:
    if framework == ComplianceFramework.GDPR:
        if control_id == "Art.15":
            return ControlStatus.IMPLEMENTED if config.pii_detection_enabled else ControlStatus.NOT_IMPLEMENTED
        if control_id == "Art.17":
            return ControlStatus.IMPLEMENTED if config.pii_retention_days > 0 else ControlStatus.NOT_IMPLEMENTED
        if control_id == "Art.20":
            return ControlStatus.IMPLEMENTED if config.pii_detection_enabled else ControlStatus.PARTIAL
        if control_id == "Art.32":
            return (
                ControlStatus.IMPLEMENTED
                if config.encryption_algorithm.startswith("aes-256")
                else ControlStatus.PARTIAL
            )  # noqa: E501
        if control_id == "Art.30":
            return ControlStatus.PARTIAL
        return ControlStatus.IMPLEMENTED
    if framework == ComplianceFramework.CCPA:
        if control_id in ("1798.110", "1798.105"):
            return ControlStatus.IMPLEMENTED if config.pii_detection_enabled else ControlStatus.NOT_IMPLEMENTED
        if control_id == "1798.130":
            return ControlStatus.PARTIAL
        return ControlStatus.NOT_IMPLEMENTED
    if framework == ComplianceFramework.SOC2:
        if control_id in ("CC6.1",):
            return ControlStatus.IMPLEMENTED if config.zero_trust_enforce else ControlStatus.NOT_IMPLEMENTED
        if control_id in ("CC7.2", "CC7.3"):
            return ControlStatus.IMPLEMENTED if config.threat_detection_enabled else ControlStatus.NOT_IMPLEMENTED
        if control_id == "CC6.6":
            return ControlStatus.IMPLEMENTED if config.audit_enabled else ControlStatus.PARTIAL
        return ControlStatus.PARTIAL
    # ISO 27001
    if control_id in ("A.5.15",):
        return ControlStatus.IMPLEMENTED if config.zero_trust_enforce else ControlStatus.NOT_IMPLEMENTED
    if control_id == "A.5.24":
        return ControlStatus.IMPLEMENTED if config.threat_detection_enabled else ControlStatus.NOT_IMPLEMENTED
    if control_id == "A.8.24":
        return ControlStatus.IMPLEMENTED if config.encryption_algorithm.startswith("aes-256") else ControlStatus.PARTIAL
    if control_id == "A.8.28":
        return ControlStatus.IMPLEMENTED if config.audit_enabled else ControlStatus.NOT_IMPLEMENTED
    if control_id == "A.8.10":
        return ControlStatus.IMPLEMENTED if config.pii_retention_days > 0 else ControlStatus.NOT_IMPLEMENTED
    return ControlStatus.PARTIAL


class ComplianceManager:
    """Generates per-framework control reports with evidence hooks."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
        evidence_provider: EvidenceProvider | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self.evidence_provider = evidence_provider
        self._custom_statuses: dict[tuple[str, str], ControlStatus] = {}

    def frameworks(self) -> list[ComplianceFramework]:
        return [ComplianceFramework(fw) for fw in self.config.compliance_frameworks]

    def set_control_status(self, framework: str, control_id: str, status: ControlStatus) -> None:
        self._custom_statuses[(framework, control_id)] = status

    def _status_for(self, framework: ComplianceFramework, control_id: str) -> ControlStatus:
        override = self._custom_statuses.get((framework.value, control_id))
        if override is not None:
            return override
        return _derive_status(framework, control_id, self.config)

    def build_controls(self, framework: ComplianceFramework) -> list[Control]:
        controls: list[Control] = []
        for control_id, name in _CONTROLS.get(framework.value, []):
            control = Control(
                id=control_id,
                name=name,
                status=self._status_for(framework, control_id),
            )
            if self.evidence_provider is not None:
                try:
                    evidence = self.evidence_provider(control_id, framework.value)
                except Exception:
                    evidence = None
                if evidence is not None:
                    control.evidence = dict(evidence) if isinstance(evidence, dict) else {"value": evidence}
            controls.append(control)
        return controls

    def generate_report(self, framework: ComplianceFramework | str) -> Any:
        if isinstance(framework, str):
            framework = ComplianceFramework(framework)
        if framework not in self.frameworks():
            raise ComplianceError(f"framework {framework.value} not enabled in configuration")
        report = self._build_report(framework)
        self.metrics.record("compliance_reports", component="compliance")
        self.logger.log_event("compliance_report", framework=framework.value, readiness=report.readiness())
        return report

    def _build_report(self, framework: ComplianceFramework) -> Any:
        from .models import ComplianceReport

        controls = self.build_controls(framework)
        findings = self._findings_for(controls)
        return ComplianceReport(framework=framework, controls=controls, findings=findings)

    def _findings_for(self, controls: list[Control]) -> list[Finding]:
        findings: list[Finding] = []
        for control in controls:
            if control.status == ControlStatus.NOT_IMPLEMENTED:
                findings.append(
                    Finding(
                        id=generate_id("finding"),
                        severity=ThreatSeverity.HIGH,
                        description=f"Control {control.id} not implemented",
                        remediation=f"Implement {control.name}",
                        resource=control.id,
                    )
                )
            elif control.status == ControlStatus.PARTIAL:
                findings.append(
                    Finding(
                        id=generate_id("finding"),
                        severity=ThreatSeverity.MEDIUM,
                        description=f"Control {control.id} partially implemented",
                        remediation=f"Complete {control.name}",
                        resource=control.id,
                    )
                )
        return findings

    def readiness(self) -> float:
        """Weighted readiness across all enabled frameworks."""
        total_controls = 0
        implemented = 0
        for framework in self.frameworks():
            controls = self.build_controls(framework)
            total_controls += len(controls)
            implemented += sum(1 for c in controls if c.status == ControlStatus.IMPLEMENTED)
        if not total_controls:
            return 0.0
        return round(implemented / total_controls * 100.0, 1)

    def summary(self) -> dict[str, Any]:
        return {
            "frameworks": [fw.value for fw in self.frameworks()],
            "readiness": self.readiness(),
            "generated_at": time.time(),
        }


def create_compliance_manager(config: SecurityConfig | None = None, **overrides: Any) -> ComplianceManager:
    config = config if config is not None else SecurityConfig()
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    evidence_provider = overrides.pop("evidence_provider", None)
    return ComplianceManager(config, logger, metrics, evidence_provider)
