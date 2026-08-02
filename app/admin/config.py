from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AdminConfig:
    environment: str = "production"
    version: str = "1.0.0"
    admin_token: str = ""
    prometheus_enabled: bool = True
    otel_enabled: bool = True
    loki_enabled: bool = True
    alertmanager_enabled: bool = True
    health_timeout_seconds: float = 5.0
    track_metrics: bool = True
    log_events: bool = True
    audit_enabled: bool = True
    feature_defaults: dict[str, bool] = field(default_factory=dict)
    loki_endpoint: str = "http://loki:3100/loki/api/v1/push"
    otel_endpoint: str = "http://otel-collector:4318/v1/traces"
    prometheus_namespace: str = "airouter"
    alertmanager_endpoint: str = "http://alertmanager:9093/api/v2/alerts"

    @classmethod
    def from_env(cls) -> AdminConfig:
        return cls(
            environment=os.getenv("ADM_ENVIRONMENT", "production"),
            version=os.getenv("ADM_VERSION", "1.0.0"),
            admin_token=os.getenv("ADM_TOKEN", ""),
            prometheus_enabled=os.getenv("ADM_PROMETHEUS", "1") == "1",
            otel_enabled=os.getenv("ADM_OTEL", "1") == "1",
            loki_enabled=os.getenv("ADM_LOKI", "1") == "1",
            alertmanager_enabled=os.getenv("ADM_ALERTMANAGER", "1") == "1",
            health_timeout_seconds=float(os.getenv("ADM_HEALTH_TIMEOUT", "5")),
            track_metrics=os.getenv("ADM_TRACK_METRICS", "1") == "1",
            log_events=os.getenv("ADM_LOG_EVENTS", "1") == "1",
            audit_enabled=os.getenv("ADM_AUDIT", "1") == "1",
        )

    def integration_enabled(self, name: str) -> bool:
        flags = {
            "prometheus": self.prometheus_enabled,
            "otel": self.otel_enabled,
            "loki": self.loki_enabled,
            "alertmanager": self.alertmanager_enabled,
        }
        return flags.get(name, False)
