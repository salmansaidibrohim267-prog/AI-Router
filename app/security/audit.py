"""Immutable audit logging with an append-only hash chain.

Every record is linked to the previous one via ``sha256(previous_hash | payload
| secret)``; when ``audit_immutable`` is enabled an HMAC signature over the
chain value is also stored. ``AuditRepository.verify_integrity`` replays the
chain and reports tampered or missing links.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from typing import Any, Iterable

from .config import SecurityConfig
from .exceptions import AuditIntegrityError, AuditError
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import AuditEventType, AuditRecord, AuditSeverity


class AuditRepository:
    """In-memory store of immutable audit records with a hash chain."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self._records: list[AuditRecord] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._last_hash = "genesis"

    def _chain_hash(self, record: AuditRecord) -> str:
        payload_dict = record.to_dict()
        payload_dict.pop("signature", None)
        payload_dict.pop("hash", None)
        payload = json.dumps(payload_dict, sort_keys=True, default=str)
        secret = self.config.audit_hash_secret.encode()
        digest = hmac.new(secret, f"{record.previous_hash}|{payload}".encode(), hashlib.sha256).digest()
        if self.config.audit_immutable:
            return hmac.new(secret, f"{digest.hex()}|{self.config.node_id}".encode(), hashlib.sha256).hexdigest()
        return digest.hex()

    def append(
        self,
        event: str,
        actor: str,
        action: str,
        resource: str,
        outcome: str = "success",
        severity: AuditSeverity = AuditSeverity.INFO,
        event_type: AuditEventType = AuditEventType.ADMIN,
        metadata: dict[str, Any] | None = None,
    ) -> AuditRecord:
        with self._lock:
            self._seq += 1
            record = AuditRecord(
                seq=self._seq,
                event=event,
                actor=actor,
                action=action,
                resource=resource,
                outcome=outcome,
                severity=severity,
                event_type=event_type,
                timestamp=time.time(),
                metadata=dict(metadata or {}),
                previous_hash=self._last_hash,
            )
            record.signature = self._chain_hash(record)
            record.hash = record.signature if self.config.audit_immutable else record.previous_hash
            self._records.append(record)
            self._last_hash = record.signature
            self.metrics.record("audit_records", component="audit")
            self.logger.log_event("audit_appended", seq=record.seq, name=event, actor=actor, action=action)
            return record

    def find(self, **filters: Any) -> list[AuditRecord]:
        records = list(self._records)
        for key, value in filters.items():
            if key == "event_type":
                records = [r for r in records if r.event_type == value]
            elif key == "severity":
                records = [r for r in records if r.severity == value]
            elif key == "actor":
                records = [r for r in records if r.actor == value]
            elif key == "action":
                records = [r for r in records if r.action == value]
            elif key == "outcome":
                records = [r for r in records if r.outcome == value]
            elif key == "resource":
                records = [r for r in records if r.resource == value]
            elif key == "event":
                records = [r for r in records if r.event == value]
            elif key == "seq":
                records = [r for r in records if r.seq == value]
            elif key == "after":
                records = [r for r in records if r.timestamp > value]
            elif key == "before":
                records = [r for r in records if r.timestamp < value]
        return records

    def get(self, seq: int) -> AuditRecord | None:
        if not 1 <= seq <= len(self._records):
            return None
        return self._records[seq - 1]

    def count(self) -> int:
        return len(self._records)

    def verify_integrity(self) -> list[dict[str, Any]]:
        """Replay the chain; return a list of tampered/missing record findings."""
        violations: list[dict[str, Any]] = []
        previous_hash = "genesis"
        for index, record in enumerate(self._records):
            if record.previous_hash != previous_hash:
                violations.append(
                    {"seq": record.seq, "reason": "broken link", "expected": previous_hash, "actual": record.previous_hash}
                )
            expected = self._chain_hash(record)
            if record.signature != expected:
                violations.append({"seq": record.seq, "reason": "signature mismatch", "expected": expected})
            previous_hash = record.signature
        if violations and self.config.audit_immutable:
            self.metrics.record("audit_violations", component="audit")
        return violations

    def prune(self, retention_days: int | None = None) -> int:
        """Drop records older than the retention window. Returns removed count.

        With an immutable chain, dropping the tail is forbidden — instead the
        chain is truncated by detaching from the last remaining record.
        """
        retention_days = retention_days if retention_days is not None else self.config.audit_retention_days
        cutoff = time.time() - retention_days * 86400
        old = [r for r in self._records if r.timestamp < cutoff]
        keep = [r for r in self._records if r.timestamp >= cutoff]
        removed = len(old)
        if self.config.audit_immutable:
            if not keep and self._records:
                keep = [self._records[-1]]
                removed = max(0, removed - 1)
            while len(keep) > 1 and keep[0].timestamp < cutoff:
                keep.pop(0)
                removed += 1
            previous = "genesis"
            for record in keep:
                record.previous_hash = previous
                record.signature = self._chain_hash(record)
                record.hash = record.signature
                previous = record.signature
            self._records = keep
            self._last_hash = keep[-1].signature if keep else "genesis"
            return removed
        self._records = keep
        return removed

    def export(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._records]

    def status(self) -> dict[str, Any]:
        return {
            "records": len(self._records),
            "immutable": self.config.audit_immutable,
            "last_seq": self._seq,
            "last_hash": self._last_hash,
        }


def _now() -> float:
    return time.time()


class AuditService:
    """Facade over the repository exposing typed audit events."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        repository: AuditRepository | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.repository = repository if repository is not None else AuditRepository(self.config)
        self._enabled = self.config.audit_enabled

    def log(
        self,
        event: str,
        actor: str,
        action: str,
        resource: str = "",
        outcome: str = "success",
        severity: AuditSeverity = AuditSeverity.INFO,
        event_type: AuditEventType = AuditEventType.ADMIN,
        metadata: dict[str, Any] | None = None,
    ) -> AuditRecord | None:
        if not self._enabled:
            return None
        return self.repository.append(event, actor, action, resource, outcome, severity, event_type, metadata)

    def log_authentication(self, actor: str, outcome: str, metadata: dict[str, Any] | None = None) -> AuditRecord | None:
        severity = AuditSeverity.INFO if outcome == "success" else AuditSeverity.WARNING
        return self.log("authentication", actor, "authenticate", "auth", outcome, severity, AuditEventType.AUTHENTICATION, metadata)

    def log_authorization(self, actor: str, outcome: str, metadata: dict[str, Any] | None = None) -> AuditRecord | None:
        severity = AuditSeverity.INFO if outcome == "success" else AuditSeverity.CRITICAL
        return self.log("authorization", actor, "authorize", "authz", outcome, severity, AuditEventType.AUTHORIZATION, metadata)

    def log_secret(self, actor: str, action: str, secret_name: str, outcome: str = "success") -> AuditRecord | None:
        severity = AuditSeverity.CRITICAL if action in ("delete", "rotate") else AuditSeverity.INFO
        return self.log("secret", actor, action, f"secret:{secret_name}", outcome, severity, AuditEventType.SECRET)

    def log_admin(self, actor: str, action: str, resource: str = "system", outcome: str = "success") -> AuditRecord | None:
        return self.log("admin", actor, action, resource, outcome, AuditSeverity.WARNING, AuditEventType.ADMIN)

    def verify(self) -> list[dict[str, Any]]:
        return self.repository.verify_integrity()

    def status(self) -> dict[str, Any]:
        return {"enabled": self._enabled, **self.repository.status()}


def create_audit_service(config: SecurityConfig | None = None, **overrides: Any) -> AuditService:
    config = config if config is not None else SecurityConfig()
    repository = overrides.pop("repository", None)
    if repository is None:
        logger = overrides.pop("logger", None) or SecurityLogger(config)
        metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
        repository = AuditRepository(config, logger, metrics)
    return AuditService(config, repository)
