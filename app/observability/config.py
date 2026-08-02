"""Observability configuration (Stage 10.10)."""

from __future__ import annotations

import os
from typing import Any


class ObservabilityConfig:
    """Runtime configuration for SLO/SLI tracking and alerting."""

    def __init__(self, **kwargs: Any) -> None:
        self.window_seconds: int = int(kwargs.pop("window_seconds", 30 * 86400))
        self.default_slo: float = float(kwargs.pop("default_slo", 99.9))
        self.burn_alert_threshold: float = float(kwargs.pop("burn_alert_threshold", 0.5))
        self.page_threshold: float = float(kwargs.pop("page_threshold", 2.0))
        self.alerts_enabled: bool = bool(kwargs.pop("alerts_enabled", True))
        self.alerts_file: str = kwargs.pop("alerts_file", "config/alerts.yml")
        self.dashboard_dir: str = kwargs.pop("dashboard_dir", "grafana/dashboards")
        self.metrics_enabled: bool = bool(kwargs.pop("metrics_enabled", True))
        self.traces_enabled: bool = bool(kwargs.pop("traces_enabled", True))
        self._reject_unknown(kwargs)

    def _reject_unknown(self, kwargs: dict[str, Any]) -> None:
        if kwargs:
            raise TypeError(f"unexpected observability config: {sorted(kwargs)}")

    @classmethod
    def from_env(cls, **overrides: Any) -> "ObservabilityConfig":
        kwargs: dict[str, Any] = {
            "window_seconds": int(os.environ.get("OBS_WINDOW_SECONDS", str(30 * 86400))),
            "default_slo": float(os.environ.get("OBS_DEFAULT_SLO", "99.9")),
            "burn_alert_threshold": float(os.environ.get("OBS_BURN_ALERT_THRESHOLD", "0.5")),
            "page_threshold": float(os.environ.get("OBS_PAGE_THRESHOLD", "2.0")),
            "alerts_enabled": os.environ.get("OBS_ALERTS_ENABLED", "true").lower() in ("1", "true", "yes"),
            "metrics_enabled": os.environ.get("OBS_METRICS_ENABLED", "true").lower() in ("1", "true", "yes"),
            "traces_enabled": os.environ.get("OBS_TRACES_ENABLED", "true").lower() in ("1", "true", "yes"),
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    def as_dict(self) -> dict[str, Any]:
        return {name: value for name, value in vars(self).items()}
