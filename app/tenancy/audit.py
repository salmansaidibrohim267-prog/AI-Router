from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuditEvent:
    timestamp: float
    action: str
    tenant_id: str = ""
    actor: str = ""
    resource: str = ""
    outcome: str = "success"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "resource": self.resource,
            "outcome": self.outcome,
            "details": self.details,
        }


class AuditLogger:
    def __init__(
        self,
        config: Any | None = None,
        logger: Any | None = None,
        max_events: int = 1000,
    ):
        from .config import TenancyConfig
        from .logging import TenancyLogger

        self._config = config or TenancyConfig()
        self._logger = logger or TenancyLogger()
        self._events: list[AuditEvent] = []
        self._max_events = max_events

    def record(
        self,
        action: str,
        tenant_id: str = "",
        actor: str = "",
        resource: str = "",
        outcome: str = "success",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            timestamp=time.time(),
            action=action,
            tenant_id=tenant_id,
            actor=actor,
            resource=resource,
            outcome=outcome,
            details=details or {},
        )
        if self._config.audit_enabled:
            self._events.append(event)
            if len(self._events) > self._max_events:
                self._events = self._events[-self._max_events :]
            self._logger.log_event(
                "audit",
                tenant_id=tenant_id,
                action=action,
                actor=actor,
                outcome=outcome,
            )
        return event

    def list(self, tenant_id: str | None = None, limit: int = 100) -> list[AuditEvent]:
        events = self._events
        if tenant_id is not None:
            events = [e for e in events if e.tenant_id == tenant_id]
        return events[-limit:] if limit else events

    def count(self, tenant_id: str | None = None) -> int:
        return len(self.list(tenant_id=tenant_id, limit=0))

    def clear(self) -> None:
        self._events = []
