from __future__ import annotations

import json
import logging
from typing import Any

from .config import BillingConfig


class BillingLogger:
    def __init__(self, config: BillingConfig | None = None) -> None:
        self._config = config or BillingConfig()
        self._logger = logging.getLogger("billing")
        self._logger.setLevel(logging.INFO)
        self._events: list[dict[str, Any]] = []

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._events

    def log_event(self, event: str, **extra: Any) -> None:
        payload: dict[str, Any] = {"event": f"billing_{event}", "data": extra}
        if self._config.log_events:
            self._events.append(payload)
        try:
            self._logger.info(json.dumps(payload, default=str))
        except Exception:
            self._logger.info("billing_event")
