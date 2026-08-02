from __future__ import annotations

import json
import logging
from typing import Any


class OrganizationLogger:
    def __init__(self, name: str = "organization"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)

    def log_event(
        self,
        event: str,
        tenant_id: str = "",
        organization_id: str = "",
        workspace_id: str = "",
        user_id: str = "",
        **extra: Any,
    ) -> None:
        payload: dict[str, Any] = {
            "event": f"organization_{event}",
            "tenant_id": tenant_id,
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "user_id": user_id,
            "data": extra,
        }
        try:
            self._logger.info(json.dumps(payload, default=str))
        except Exception:
            self._logger.info(f"organization_{event}")
