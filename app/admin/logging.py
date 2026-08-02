from __future__ import annotations

import json
import logging
from typing import Any

from .config import AdminConfig


class AdminLogger:
    def __init__(self, config: AdminConfig | None = None) -> None:
        self._config = config or AdminConfig()
        self._logger = logging.getLogger("admin")
        self._logger.setLevel(logging.INFO)
        self._events: list[dict[str, Any]] = []

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._events

    def log_event(self, event: str, **extra: Any) -> None:
        payload: dict[str, Any] = {"event": f"admin_{event}", "data": extra}
        if self._config.log_events:
            self._events.append(payload)
        try:
            self._logger.info(json.dumps(payload, default=str))
        except Exception:
            self._logger.info("admin_event")
