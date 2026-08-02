from __future__ import annotations

import json
import logging
from typing import Any

from app.rag.models import RAGRequest, RAGResponse


class RAGLogger:
    def __init__(self, name: str = "rag"):
        self._logger = logging.getLogger(name)

    def log_request(self, request: RAGRequest) -> None:
        if not self._logger.isEnabledFor(logging.INFO):
            return
        self._logger.info(
            json.dumps({
                "event": "rag_request",
                "query": request.query[:500],
                "has_history": bool(request.conversation_history),
                "stream": request.stream,
                "provider_override": request.provider_override,
            })
        )

    def log_response(self, response: RAGResponse, latency_ms: float) -> None:
        if not self._logger.isEnabledFor(logging.INFO):
            return
        self._logger.info(
            json.dumps({
                "event": "rag_response",
                "cache_hit": response.cache_hit,
                "fallback_used": response.fallback_used,
                "total_latency_ms": round(latency_ms, 4),
                "confidence": response.confidence,
                "answer_length": len(response.answer),
                "sources_count": len(response.sources),
                "token_usage": response.token_usage,
            })
        )

    def log_error(self, error: Exception, query: str = "") -> None:
        self._logger.error(
            json.dumps({
                "event": "rag_error",
                "error": str(error),
                "error_type": error.__class__.__name__,
                "query": query[:500],
            })
        )
