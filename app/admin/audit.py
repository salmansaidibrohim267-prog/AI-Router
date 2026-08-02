from __future__ import annotations

import time
from typing import Any

from .config import AdminConfig
from .exceptions import AuditQueryError
from .logging import AdminLogger
from .models import AuditRecord, generate_id
from .repositories import AuditRepository


class AuditService:
    """Records and queries administrative audit trails."""

    def __init__(
        self,
        config: AdminConfig | None = None,
        repository: AuditRepository | None = None,
        logger: AdminLogger | None = None,
    ) -> None:
        from .repositories import InMemoryAuditRepository

        self._config = config or AdminConfig()
        self._repository = repository or InMemoryAuditRepository()
        self._logger = logger or AdminLogger(self._config)

    @property
    def repository(self) -> AuditRepository:
        return self._repository

    def record(self, actor: str, action: str, resource: str = "", details: dict[str, Any] | None = None) -> AuditRecord:
        record = AuditRecord(
            id=generate_id("aud"),
            actor=actor,
            action=action,
            resource=resource,
            details=details or {},
            created_at=time.time(),
        )
        self._repository.record(record)
        self._logger.log_event("audit.recorded", actor=actor, action=action, resource=resource)
        return record

    def query(self, actor: str = "", action: str = "", limit: int = 50) -> list[AuditRecord]:
        if limit < 1 or limit > 1000:
            raise AuditQueryError(f"limit must be between 1 and 1000, got {limit}")
        return self._repository.query(actor=actor, action=action, limit=limit)

    def count(self) -> int:
        return len(self._repository.query(limit=1000))

    def by_actor(self, actor: str, limit: int = 50) -> list[AuditRecord]:
        return self._repository.query(actor=actor, limit=limit)

    def by_action(self, action: str, limit: int = 50) -> list[AuditRecord]:
        return self._repository.query(action=action, limit=limit)
