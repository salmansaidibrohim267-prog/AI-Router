"""Deployment configuration (Stage 10.10)."""

from __future__ import annotations

import os
from typing import Any


class DeployConfig:
    """Runtime configuration for the deployment pipeline."""

    def __init__(self, **kwargs: Any) -> None:
        self.target_version: str = kwargs.pop("target_version", "1.0.0-rc.1")
        self.environment: str = kwargs.pop("environment", "staging")
        self.min_coverage: float = float(kwargs.pop("min_coverage", 95.0))
        self.max_latency_ms: float = float(kwargs.pop("max_latency_ms", 500.0))
        self.max_error_rate: float = float(kwargs.pop("max_error_rate", 1.0))
        self.smoke_timeout_seconds: int = int(kwargs.pop("smoke_timeout_seconds", 30))
        self.require_signatures: bool = bool(kwargs.pop("require_signatures", True))
        self.auto_rollback: bool = bool(kwargs.pop("auto_rollback", True))
        self.gitops_manifest: str = kwargs.pop("gitops_manifest", "deployment/gitops/apps/ai-router/application.yaml")
        self.release_artifacts_dir: str = kwargs.pop("release_artifacts_dir", "dist/release")
        self._reject_unknown(kwargs)

    def _reject_unknown(self, kwargs: dict[str, Any]) -> None:
        if kwargs:
            raise TypeError(f"unexpected deploy config: {sorted(kwargs)}")

    @classmethod
    def from_env(cls, **overrides: Any) -> "DeployConfig":
        kwargs: dict[str, Any] = {
            "target_version": os.environ.get("DEP_TARGET_VERSION", "1.0.0-rc.1"),
            "environment": os.environ.get("DEP_ENVIRONMENT", "staging"),
            "min_coverage": float(os.environ.get("DEP_MIN_COVERAGE", "95.0")),
            "max_latency_ms": float(os.environ.get("DEP_MAX_LATENCY_MS", "500.0")),
            "max_error_rate": float(os.environ.get("DEP_MAX_ERROR_RATE", "1.0")),
            "smoke_timeout_seconds": int(os.environ.get("DEP_SMOKE_TIMEOUT_SECONDS", "30")),
            "require_signatures": os.environ.get("DEP_REQUIRE_SIGNATURES", "true").lower() in ("1", "true", "yes"),
            "auto_rollback": os.environ.get("DEP_AUTO_ROLLBACK", "true").lower() in ("1", "true", "yes"),
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    def as_dict(self) -> dict[str, Any]:
        return {name: value for name, value in vars(self).items()}
