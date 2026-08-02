"""Security & Compliance configuration.

Settings mirror the rest of the platform: constructor defaults plus
``from_env()`` reading ``SEC_*`` environment variables.
"""

from __future__ import annotations

import os
import socket
import uuid
from typing import Any


def _default_node_id() -> str:
    host = socket.gethostname()
    suffix = uuid.uuid4().hex[:8]
    return f"node-{host}-{suffix}"


class SecurityConfig:
    """Runtime configuration for the security framework."""

    def __init__(self, **kwargs: Any) -> None:
        # Identity
        self.node_id: str = kwargs.pop("node_id", None) or _default_node_id()
        self.environment: str = kwargs.pop("environment", "production")
        self.region: str = kwargs.pop("region", "default")

        # Secret management
        self.secret_backend: str = kwargs.pop("secret_backend", "environment")
        self.secret_config: dict[str, Any] = dict(kwargs.pop("secret_config", {}) or {})
        self.secret_cache_ttl: float = float(kwargs.pop("secret_cache_ttl", 60.0))

        # Encryption
        self.encryption_algorithm: str = kwargs.pop("encryption_algorithm", "aes-256-gcm")
        self.envelope_enabled: bool = bool(kwargs.pop("envelope_enabled", True))
        self.key_rotation_days: int = int(kwargs.pop("key_rotation_days", 90))
        self.master_key_ttl: int = int(kwargs.pop("master_key_ttl", 0))

        # Zero Trust
        self.zero_trust_enforce: bool = bool(kwargs.pop("zero_trust_enforce", True))
        self.max_session_age_seconds: int = int(kwargs.pop("max_session_age_seconds", 3600))
        self.session_idle_timeout_seconds: int = int(kwargs.pop("session_idle_timeout_seconds", 900))
        self.max_failed_attempts: int = int(kwargs.pop("max_failed_attempts", 5))
        self.lockout_seconds: int = int(kwargs.pop("lockout_seconds", 300))
        self.require_mfa: bool = bool(kwargs.pop("require_mfa", False))

        # Audit
        self.audit_enabled: bool = bool(kwargs.pop("audit_enabled", True))
        self.audit_immutable: bool = bool(kwargs.pop("audit_immutable", True))
        self.audit_retention_days: int = int(kwargs.pop("audit_retention_days", 365))
        self.audit_hash_secret: str = kwargs.pop("audit_hash_secret", "audit-chain-secret")

        # Privacy
        self.pii_detection_enabled: bool = bool(kwargs.pop("pii_detection_enabled", True))
        self.pii_retention_days: int = int(kwargs.pop("pii_retention_days", 90))
        self.pii_masking_mode: str = kwargs.pop("pii_masking_mode", "partial")

        # Threat detection
        self.threat_detection_enabled: bool = bool(kwargs.pop("threat_detection_enabled", True))
        self.threat_window_seconds: float = float(kwargs.pop("threat_window_seconds", 60.0))
        self.brute_force_threshold: int = int(kwargs.pop("brute_force_threshold", 5))
        self.token_replay_threshold: int = int(kwargs.pop("token_replay_threshold", 3))

        # Compliance
        self.compliance_frameworks: list[str] = list(
            kwargs.pop("compliance_frameworks", ["soc2", "iso27001", "gdpr", "ccpa"]) or []
        )

        # Monitoring / integrations
        self.monitoring_enabled: bool = bool(kwargs.pop("monitoring_enabled", True))
        self.siem_backend: str = kwargs.pop("siem_backend", "stdout")
        self.siem_config: dict[str, Any] = dict(kwargs.pop("siem_config", {}) or {})

        # Observability
        self.log_events: bool = bool(kwargs.pop("log_events", True))

        # Misc
        self.extra: dict[str, Any] = dict(kwargs.pop("extra", {}) or {})
        self._reject_unknown(kwargs)

    def _reject_unknown(self, kwargs: dict[str, Any]) -> None:
        if kwargs:
            raise TypeError(f"unexpected security config: {sorted(kwargs)}")

    @classmethod
    def from_env(cls, **overrides: Any) -> "SecurityConfig":
        """Build config from ``SEC_*`` environment variables + overrides."""
        def _get(name: str, default: str) -> str:
            return os.environ.get(f"SEC_{name}", default)

        kwargs: dict[str, Any] = {
            "node_id": _get("NODE_ID", ""),
            "environment": _get("ENVIRONMENT", "production"),
            "region": _get("REGION", "default"),
            "secret_backend": _get("SECRET_BACKEND", "environment"),
            "encryption_algorithm": _get("ENCRYPTION_ALGORITHM", "aes-256-gcm"),
            "key_rotation_days": int(os.environ.get("SEC_KEY_ROTATION_DAYS", "90")),
            "max_session_age_seconds": int(os.environ.get("SEC_MAX_SESSION_AGE_SECONDS", "3600")),
            "audit_retention_days": int(os.environ.get("SEC_AUDIT_RETENTION_DAYS", "365")),
            "pii_retention_days": int(os.environ.get("SEC_PII_RETENTION_DAYS", "90")),
            "pii_masking_mode": _get("PII_MASKING_MODE", "partial"),
            "zero_trust_enforce": os.environ.get("SEC_ZERO_TRUST_ENFORCE", "true").lower() in ("1", "true", "yes"),
            "audit_enabled": os.environ.get("SEC_AUDIT_ENABLED", "true").lower() in ("1", "true", "yes"),
            "threat_detection_enabled": os.environ.get("SEC_THREAT_DETECTION_ENABLED", "true").lower() in ("1", "true", "yes"),
            "monitoring_enabled": os.environ.get("SEC_MONITORING_ENABLED", "true").lower() in ("1", "true", "yes"),
            "log_events": os.environ.get("SEC_LOG_EVENTS", "true").lower() in ("1", "true", "yes"),
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    def as_dict(self) -> dict[str, Any]:
        """Plain serialisable representation."""
        result: dict[str, Any] = {}
        for name, value in vars(self).items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                result[name] = value
            else:
                result[name] = str(value)
        result["secret_config"] = dict(self.secret_config)
        result["siem_config"] = dict(self.siem_config)
        result["extra"] = dict(self.extra)
        result["compliance_frameworks"] = list(self.compliance_frameworks)
        return result
