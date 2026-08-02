from __future__ import annotations

import threading
import time
from typing import Any

from .exceptions import MaintenanceActiveError
from .logging import AdminLogger
from .models import MaintenanceStatus


class MaintenanceManager:
    """Manages maintenance mode: immediate toggles and scheduled windows."""

    def __init__(self, logger: AdminLogger | None = None) -> None:
        self._logger = logger or AdminLogger()
        self._active: bool = False
        self._reason: str = ""
        self._scheduled_start: float = 0.0
        self._scheduled_end: float = 0.0
        self._scheduled_reason: str = ""
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        now = time.time()
        if not self._active and self._scheduled_start and self._scheduled_start <= now <= self._scheduled_end:
            self._active = True
            self._reason = self._scheduled_reason or "scheduled maintenance"
        if self._active and self._scheduled_end and now > self._scheduled_end:
            self._active = False
            self._reason = ""
        return self._active

    def start(self, reason: str = "scheduled maintenance", actor: str = "admin") -> None:
        self._active = True
        self._reason = reason
        self._logger.log_event("maintenance.started", reason=reason, actor=actor)

    def end(self, actor: str = "admin") -> None:
        self._active = False
        self._reason = ""
        self._scheduled_start = 0.0
        self._scheduled_end = 0.0
        self._scheduled_reason = ""
        self._logger.log_event("maintenance.ended", actor=actor)

    def schedule(self, start: float, end: float, reason: str = "") -> None:
        if end <= start:
            raise MaintenanceActiveError("maintenance window end must be after start")
        self._scheduled_start = start
        self._scheduled_end = end
        self._scheduled_reason = reason

    def in_maintenance(self) -> bool:
        return self.active

    def require_available(self) -> None:
        if self.in_maintenance():
            raise MaintenanceActiveError(self._reason or "system is under maintenance")

    def status(self) -> dict[str, Any]:
        active = self.in_maintenance()
        return {
            "status": MaintenanceStatus.ACTIVE.value if active else MaintenanceStatus.NONE.value,
            "reason": self._reason,
            "scheduled_start": self._scheduled_start or None,
            "scheduled_end": self._scheduled_end or None,
            "scheduled_reason": self._scheduled_reason,
        }
