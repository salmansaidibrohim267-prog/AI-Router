"""Configuration for the API Gateway (Stage 10.4)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GatewayConfig:
    """Gateway configuration with env-driven defaults."""

    default_version: str = "v1"
    supported_versions: list[str] = field(default_factory=lambda: ["v1", "v2"])
    deprecated_versions: list[str] = field(default_factory=lambda: ["v1"])
    deprecation_warning_header: str = "X-API-Deprecated"
    version_header: str = "X-API-Version"
    version_ttl_seconds: float = 3600.0
    allow_header_versioning: bool = True
    allow_url_versioning: bool = True
    version_header_priority: bool = True

    default_rate_limit_strategy: str = "token_bucket"
    default_requests_per_minute: int = 120
    default_burst: int = 30
    sliding_window_precision: float = 1.0

    max_requests_per_key: int = 100000
    max_quota_requests: int = 100000
    max_quota_tokens: int = 1000000
    max_quota_storage: int = 1024 * 1024 * 1024
    max_quota_embeddings: int = 100000
    max_quota_mcp_calls: int = 10000

    cache_enabled: bool = True
    cache_ttl_seconds: float = 60.0
    cache_max_entries: int = 1000

    webhooks_enabled: bool = True
    webhook_max_retries: int = 3
    webhook_retry_backoff_seconds: float = 1.0
    webhook_secret: str = ""

    request_timeout_seconds: float = 30.0
    max_body_bytes: int = 10 * 1024 * 1024
    openapi_title: str = "AI Router Gateway API"
    openapi_version: str = "3.0.0"
    openapi_servers: list[str] = field(default_factory=list)

    log_events: bool = True
    track_metrics: bool = True
    audit_enabled: bool = True
    correlation_header: str = "X-Correlation-ID"

    @classmethod
    def from_env(cls, prefix: str = "GW_") -> GatewayConfig:
        """Build config from environment variables."""

        def _split(value: str | None) -> list[str]:
            return [item.strip() for item in (value or "").split(",") if item.strip()]

        def _int(name: str, default: int) -> int:
            raw = os.environ.get(f"{prefix}{name}")
            return int(raw) if raw is not None else default

        def _float(name: str, default: float) -> float:
            raw = os.environ.get(f"{prefix}{name}")
            return float(raw) if raw is not None else default

        def _bool(name: str, default: bool) -> bool:
            raw = os.environ.get(f"{prefix}{name}")
            if raw is None:
                return default
            return raw.strip().lower() in ("1", "true", "yes", "on")

        return GatewayConfig(
            default_version=os.environ.get(f"{prefix}DEFAULT_VERSION", "v1"),
            supported_versions=_split(os.environ.get(f"{prefix}SUPPORTED_VERSIONS")) or ["v1", "v2"],
            deprecated_versions=_split(os.environ.get(f"{prefix}DEPRECATED_VERSIONS")) or ["v1"],
            deprecation_warning_header=os.environ.get(f"{prefix}DEPRECATION_WARNING_HEADER", "X-API-Deprecated"),
            version_header=os.environ.get(f"{prefix}VERSION_HEADER", "X-API-Version"),
            version_ttl_seconds=_float("VERSION_TTL_SECONDS", 3600.0),
            allow_header_versioning=_bool("ALLOW_HEADER_VERSIONING", True),
            allow_url_versioning=_bool("ALLOW_URL_VERSIONING", True),
            version_header_priority=_bool("VERSION_HEADER_PRIORITY", True),
            default_rate_limit_strategy=os.environ.get(f"{prefix}DEFAULT_RATE_LIMIT_STRATEGY", "token_bucket"),
            default_requests_per_minute=_int("DEFAULT_REQUESTS_PER_MINUTE", 120),
            default_burst=_int("DEFAULT_BURST", 30),
            sliding_window_precision=_float("SLIDING_WINDOW_PRECISION", 1.0),
            max_requests_per_key=_int("MAX_REQUESTS_PER_KEY", 100000),
            max_quota_requests=_int("MAX_QUOTA_REQUESTS", 100000),
            max_quota_tokens=_int("MAX_QUOTA_TOKENS", 1000000),
            max_quota_storage=_int("MAX_QUOTA_STORAGE", 1024 * 1024 * 1024),
            max_quota_embeddings=_int("MAX_QUOTA_EMBEDDINGS", 100000),
            max_quota_mcp_calls=_int("MAX_QUOTA_MCP_CALLS", 10000),
            cache_enabled=_bool("CACHE_ENABLED", True),
            cache_ttl_seconds=_float("CACHE_TTL_SECONDS", 60.0),
            cache_max_entries=_int("CACHE_MAX_ENTRIES", 1000),
            webhooks_enabled=_bool("WEBHOOKS_ENABLED", True),
            webhook_max_retries=_int("WEBHOOK_MAX_RETRIES", 3),
            webhook_retry_backoff_seconds=_float("WEBHOOK_RETRY_BACKOFF_SECONDS", 1.0),
            webhook_secret=os.environ.get(f"{prefix}WEBHOOK_SECRET", ""),
            request_timeout_seconds=_float("REQUEST_TIMEOUT_SECONDS", 30.0),
            max_body_bytes=_int("MAX_BODY_BYTES", 10 * 1024 * 1024),
            openapi_title=os.environ.get(f"{prefix}OPENAPI_TITLE", "AI Router Gateway API"),
            openapi_version=os.environ.get(f"{prefix}OPENAPI_VERSION", "3.0.0"),
            openapi_servers=_split(os.environ.get(f"{prefix}OPENAPI_SERVERS")),
            log_events=_bool("LOG_EVENTS", True),
            track_metrics=_bool("TRACK_METRICS", True),
            audit_enabled=_bool("AUDIT_ENABLED", True),
            correlation_header=os.environ.get(f"{prefix}CORRELATION_HEADER", "X-Correlation-ID"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializable representation."""
        return {
            "default_version": self.default_version,
            "supported_versions": list(self.supported_versions),
            "deprecated_versions": list(self.deprecated_versions),
            "default_rate_limit_strategy": self.default_rate_limit_strategy,
            "cache_enabled": self.cache_enabled,
            "webhooks_enabled": self.webhooks_enabled,
            "audit_enabled": self.audit_enabled,
        }
