from __future__ import annotations

import json
import logging
from typing import Any

from app.citations.models import CitationResult


class CitationLogger:
    def __init__(self, name: str = "citations"):
        self._logger = logging.getLogger(name)

    def log_event(
        self,
        event: str,
        result: CitationResult | None = None,
        **extra: Any,
    ) -> None:
        if not self._logger.isEnabledFor(logging.INFO):
            return
        payload: dict[str, Any] = {
            "event": f"citation_{event}",
            **extra,
        }
        if result is not None:
            payload.update({
                "citations": len(result.citations),
                "sources": len(result.sources),
                "format": result.format.value,
                "confidence": round(result.confidence, 4),
                "errors": len(result.errors),
                "warnings": len(result.warnings),
            })
        self._logger.info(json.dumps(payload))

    def log_error(self, error: Exception, context: str = "") -> None:
        self._logger.error(
            json.dumps({
                "event": "citation_error",
                "error": str(error),
                "error_type": error.__class__.__name__,
                "context": context,
            })
        )
