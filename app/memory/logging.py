from __future__ import annotations

import json
import logging
from typing import Any

from app.memory.models import MemoryEventType, MemoryItem


class MemoryLogger:
    def __init__(self, name: str = "memory"):
        self._logger = logging.getLogger(name)

    def log_event(self, event: MemoryEventType, item: MemoryItem | None = None, **extra: Any) -> None:
        if not self._logger.isEnabledFor(logging.INFO):
            return
        payload: dict[str, Any] = {
            "event": f"memory_{event.value}",
            **extra,
        }
        if item is not None:
            payload.update(
                {
                    "item_id": item.id,
                    "memory_type": item.memory_type.value,
                    "category": item.category.value,
                    "tenant_id": item.tenant_id,
                    "user_id": item.user_id,
                    "session_id": item.session_id,
                }
            )
        self._logger.info(json.dumps(payload))

    def log_error(self, error: Exception, context: str = "") -> None:
        self._logger.error(
            json.dumps(
                {
                    "event": "memory_error",
                    "error": str(error),
                    "error_type": error.__class__.__name__,
                    "context": context,
                }
            )
        )
