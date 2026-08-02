"""Structured logging for the API Gateway (Stage 10.4)."""

from __future__ import annotations

import json
import time
from typing import Any


class GatewayLogger:
    """Structured JSON gateway logger with optional event buffering."""

    def __init__(self, enabled: bool = True, sink: Any = None):
        self._enabled = enabled
        self._sink = sink
        self._events: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def log_event(self, event: str, **fields: Any) -> None:
        record = {"ts": time.time(), "event": event, **fields}
        if not self._enabled:
            return
        self._events.append(record)
        if self._sink is not None:
            try:
                self._sink(json.dumps(record))
            except Exception:
                pass

    def request(self, method: str, path: str, status: int, duration: float, **fields: Any) -> None:
        self.log_event(
            "gateway.request",
            method=method,
            path=path,
            status=status,
            duration_seconds=duration,
            **fields,
        )

    def route(self, pattern: str, action: str, **fields: Any) -> None:
        self.log_event("gateway.route", pattern=pattern, action=action, **fields)

    def error(self, message: str, error_code: str = "", **fields: Any) -> None:
        self.log_event("gateway.error", message=message, error_code=error_code, **fields)

    def clear(self) -> None:
        self._events.clear()
