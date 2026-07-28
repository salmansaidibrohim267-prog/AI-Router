"""Structured JSON logging for AI Router."""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import LogEntry


SENSITIVE_FIELDS = {"api_key", "api-key", "apikey", "secret", "password", "token", "authorization",
                    "x-api-key", "cookie", "set-cookie"}


def _mask_sensitive(value: str) -> str:
    if not isinstance(value, str):
        return value
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def _sanitize_value(key: str, value):
    """Mask value if key name indicates sensitive content."""
    if key.lower() in SENSITIVE_FIELDS:
        return _mask_sensitive(value)
    if isinstance(value, dict):
        return {k: _sanitize_value(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(key, v) if isinstance(v, dict) else v for v in value]
    return value


class JSONFormatter(logging.Formatter):
    """JSON log formatter with sensitive data masking."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields (sanitized)
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "levelname", "levelno", "pathname",
                           "filename", "module", "lineno", "funcName", "created",
                           "msecs", "relativeCreated", "thread", "threadName",
                           "processName", "process", "exc_info", "exc_text", "stack_info"]:
                log_data[key] = _sanitize_value(key, value)

        return json.dumps(log_data, default=str)


class StructuredLogger:
    """Thread-safe structured logger with in-memory buffer."""

    def __init__(
        self,
        log_dir: str | Path = "logs",
        max_memory_logs: int = 1000,
        log_level: str = "INFO",
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.max_memory_logs = max_memory_logs
        self._memory_logs: deque[LogEntry] = deque(maxlen=max_memory_logs)
        self._lock = threading.RLock()

        # Setup file handler with JSON format
        self._setup_file_logging(log_level)

    def _setup_file_logging(self, log_level: str) -> None:
        """Setup file logging with JSON formatter."""
        log_file = self.log_dir / "router.jsonl"

        # Create logger
        self.logger = logging.getLogger("ai_router")
        self.logger.setLevel(getattr(logging, log_level.upper()))
        self.logger.handlers.clear()

        # File handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(JSONFormatter())
        self.logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(JSONFormatter())
        self.logger.addHandler(console_handler)

    def log_request(
        self,
        request_id: str,
        provider: str,
        model: str,
        task: str,
        latency_ms: float,
        success: bool,
        error: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        status_code: int = 200,
        response_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a request with structured data."""
        entry = LogEntry(
            request_id=request_id,
            response_id=response_id,
            provider=provider,
            model=model,
            task=task,
            latency_ms=latency_ms,
            success=success,
            error=error,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            status_code=status_code,
            metadata=metadata or {},
        )

        # Add to memory buffer
        with self._lock:
            self._memory_logs.append(entry)

        # Log to file/console
        log_data = entry.model_dump()
        if success:
            self.logger.info("Request completed", extra=log_data)
        else:
            self.logger.error("Request failed", extra=log_data)

    def log_health_check(
        self,
        provider: str,
        status: str,
        latency_ms: float | None = None,
        error: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Log health check result."""
        self.logger.info(
            f"Health check: {provider} - {status}",
            extra={
                "event": "health_check",
                "provider": provider,
                "status": status,
                "latency_ms": latency_ms,
                "error": error,
                "details": details or {},
            },
        )

    def log_config_reload(self, success: bool, message: str, config_hash: str) -> None:
        """Log config reload event."""
        self.logger.info(
            f"Config reload: {'success' if success else 'failed'} - {message}",
            extra={
                "event": "config_reload",
                "success": success,
                "message": message,
                "config_hash": config_hash,
            },
        )

    def get_recent_logs(self, limit: int = 100) -> list[LogEntry]:
        """Get recent logs from memory buffer."""
        with self._lock:
            return list(self._memory_logs)[-limit:]

    def get_logs_by_provider(self, provider: str, limit: int = 100) -> list[LogEntry]:
        """Get logs filtered by provider."""
        with self._lock:
            return [
                log for log in reversed(self._memory_logs)
                if log.provider == provider
            ][:limit]

    def get_logs_by_task(self, task: str, limit: int = 100) -> list[LogEntry]:
        """Get logs filtered by task."""
        with self._lock:
            return [
                log for log in reversed(self._memory_logs)
                if log.task == task
            ][:limit]

    def get_error_logs(self, limit: int = 100) -> list[LogEntry]:
        """Get failed request logs."""
        with self._lock:
            return [
                log for log in reversed(self._memory_logs)
                if not log.success
            ][:limit]

    def clear_memory_logs(self) -> None:
        """Clear memory log buffer."""
        with self._lock:
            self._memory_logs.clear()

    def get_logs(
        self,
        limit: int = 100,
        provider: str | None = None,
        success: bool | None = None,
    ) -> list[LogEntry]:
        """Get logs with optional filtering."""
        with self._lock:
            logs = list(self._memory_logs)[-limit:]

            if provider:
                logs = [log for log in logs if log.provider == provider]
            if success is not None:
                logs = [log for log in logs if log.success == success]

            return list(reversed(logs))

    def get_log(self, request_id: str) -> LogEntry | None:
        """Get log by request ID."""
        with self._lock:
            for log in reversed(self._memory_logs):
                if log.request_id == request_id:
                    return log
            return None

    def clear(self) -> None:
        """Clear all logs."""
        self.clear_memory_logs()

    def now(self) -> datetime:
        """Get current time."""
        return datetime.now()

    def shutdown(self) -> None:
        """Shutdown logger."""
        # Flush handlers
        for handler in self.logger.handlers:
            handler.flush()
            handler.close()


# Global logger instance
logger = StructuredLogger()