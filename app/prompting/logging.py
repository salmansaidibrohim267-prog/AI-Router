from __future__ import annotations

import json
import logging

from app.prompting.models import PromptBuildRequest, PromptBuildResult


class PromptLogger:
    def __init__(self, name: str = "prompting"):
        self._logger = logging.getLogger(name)

    def log_build(self, request: PromptBuildRequest, result: PromptBuildResult) -> None:
        if not self._logger.isEnabledFor(logging.INFO):
            return
        self._logger.info(
            json.dumps(
                {
                    "event": "prompt_build",
                    "sections": list(result.sections.keys()),
                    "total_tokens": result.total_tokens,
                    "budget_tokens": result.budget_tokens,
                    "truncated": result.truncated,
                    "format": result.format.value,
                    "context_items_used": result.context_items_used,
                    "latency_ms": round(result.build_latency_ms, 4),
                }
            )
        )

    def log_error(self, error: Exception, query: str = "") -> None:
        self._logger.error(
            json.dumps(
                {
                    "event": "prompt_error",
                    "error": str(error),
                    "error_type": error.__class__.__name__,
                    "query": query[:500],
                }
            )
        )
