from __future__ import annotations

import json
import logging
from typing import Any


class MCPLogger:
    def __init__(self, name: str = "mcp"):
        self._logger = logging.getLogger(name)

    def log_event(self, event: str, **extra: Any) -> None:
        if not self._logger.isEnabledFor(logging.INFO):
            return
        self._logger.info(json.dumps({"event": f"mcp_{event}", **extra}))

    def log_error(self, error: Exception, context: str = "") -> None:
        self._logger.error(
            json.dumps(
                {
                    "event": "mcp_error",
                    "error": str(error),
                    "error_type": error.__class__.__name__,
                    "context": context,
                }
            )
        )
