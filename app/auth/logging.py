from __future__ import annotations

import json
import logging
from typing import Any


class AuthLogger:
    def __init__(self, name: str = "auth"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)

    def log_event(self, event: str, tenant_id: str = "", user_id: str = "", **extra: Any) -> None:
        payload: dict[str, Any] = {
            "event": f"auth_{event}",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "data": extra,
        }
        try:
            self._logger.info(json.dumps(payload, default=str))
        except Exception:
            self._logger.info(f"auth_{event}")
