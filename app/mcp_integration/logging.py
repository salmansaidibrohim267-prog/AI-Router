from __future__ import annotations

import json
import logging
from typing import Any


class MCPIntegrationLogger:
    def __init__(self, name: str = "mcp_integration"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)

    def log_event(self, event: str, **extra: Any) -> None:
        payload: dict[str, Any] = {
            "event": f"mcp_integration_{event}",
            "data": extra,
        }
        try:
            self._logger.info(json.dumps(payload, default=str))
        except Exception:
            self._logger.info(f"mcp_integration_{event}")
