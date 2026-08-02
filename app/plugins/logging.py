from __future__ import annotations

import json
import logging
from typing import Any

from .config import PluginConfig


class PluginLogger:
    """Structured event logger for the plugin platform."""

    def __init__(self, config: PluginConfig | None = None) -> None:
        self._config = config or PluginConfig()
        self._logger = logging.getLogger("plugins")
        self._logger.setLevel(logging.INFO)
        self._events: list[dict[str, Any]] = []

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._events

    def log_event(self, event: str, **extra: Any) -> None:
        payload: dict[str, Any] = {"event": f"plugin_{event}", "data": extra}
        if self._config.log_events:
            self._events.append(payload)
        try:
            self._logger.info(json.dumps(payload, default=str))
        except Exception:  # pragma: no cover - defensive, default=str makes this unreachable
            self._logger.info("plugin_event")
