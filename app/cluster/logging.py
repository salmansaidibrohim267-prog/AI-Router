"""Structured event logger for the cluster framework."""

from __future__ import annotations

import json
import logging
from typing import Any

from .config import ClusterConfig


class ClusterLogger:
    """Emits ``cluster_*`` structured events and keeps an in-memory ring."""

    def __init__(self, config: ClusterConfig | None = None) -> None:
        self._config = config or ClusterConfig()
        self._logger = logging.getLogger("cluster")
        self._logger.setLevel(logging.INFO)
        self._events: list[dict[str, Any]] = []
        self._max_events = 1000

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def log_event(self, event: str, **extra: Any) -> None:
        payload: dict[str, Any] = {"event": f"cluster_{event}", "data": extra}
        if self._config.log_events:
            self._events.append(payload)
            if len(self._events) > self._max_events:
                del self._events[: len(self._events) - self._max_events]
        try:
            self._logger.info(json.dumps(payload, default=str))
        except Exception:  # pragma: no cover - defensive, default=str makes this unreachable
            self._logger.info(f"cluster_{event}")
