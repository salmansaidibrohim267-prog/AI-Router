from __future__ import annotations

import json
import logging
from typing import Any


class TenancyLogger:
    def __init__(self, name: str = "tenancy"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)

    def log_event(self, event: str, tenant_id: str = "", **extra: Any) -> None:
        payload: dict[str, Any] = {
            "event": f"tenancy_{event}",
            "tenant_id": tenant_id,
            "data": extra,
        }
        try:
            self._logger.info(json.dumps(payload, default=str))
        except Exception:
            self._logger.info(f"tenancy_{event}")
