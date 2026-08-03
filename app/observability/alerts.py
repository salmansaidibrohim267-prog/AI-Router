"""Alert rules, evaluation and Grafana dashboard generation.

``AlertRule`` couples an expression (or burn-rate threshold) with a severity
and notification targets. ``AlertEngine`` evaluates rules against SLI
snapshots and produces ``AlertIncident`` events. ``DashboardGenerator`` emits
Grafana JSON dashboards for the platform services.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import ObservabilityConfig
from .exceptions import AlertingError, DashboardError
from .slo import SliCollector, SloDefinition

Evaluator = Callable[[dict[str, Any]], bool]
"""evaluator(context) -> alert fired?"""

SEVERITIES = ("info", "warning", "critical")


@dataclass
class AlertRule:
    """A declarative alert rule."""

    name: str
    condition: str = ""
    severity: str = "warning"
    description: str = ""
    evaluator: Evaluator | None = None
    for_seconds: int = 0
    notify: list[str] = field(default_factory=lambda: ["slack", "pagerduty"])

    def __post_init__(self) -> None:
        if not self.name:
            raise AlertingError("alert rule name must not be empty")
        if self.severity not in SEVERITIES:
            raise AlertingError(f"unknown severity {self.severity!r}")
        if not self.condition and self.evaluator is None:
            raise AlertingError("alert rule needs a condition or evaluator")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "condition": self.condition,
            "severity": self.severity,
            "description": self.description,
            "for_seconds": self.for_seconds,
            "notify": list(self.notify),
        }


@dataclass
class AlertIncident:
    """A fired alert occurrence."""

    rule: str
    severity: str
    message: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


class AlertEngine:
    """Evaluates alert rules against SLI data and tracks occurrences."""

    def __init__(self, config: ObservabilityConfig | None = None) -> None:
        self.config = config if config is not None else ObservabilityConfig()
        self._rules: list[AlertRule] = []
        self._incidents: list[AlertIncident] = []
        self._firing_since: dict[str, float] = {}
        self._handlers: list[Callable[[AlertIncident], Any]] = []

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def add_rules(self, rules: list[AlertRule]) -> None:
        self._rules.extend(rules)

    def rules(self) -> list[AlertRule]:
        return list(self._rules)

    def add_handler(self, handler: Callable[[AlertIncident], Any]) -> None:
        self._handlers.append(handler)

    def evaluate(self, context: dict[str, Any]) -> list[AlertIncident]:
        """Evaluate all rules; returns incidents fired in this pass."""
        if not self.config.alerts_enabled:
            return []
        fired: list[AlertIncident] = []
        now = time.time()
        for rule in self._rules:
            triggered = (
                rule.evaluator(context)
                if rule.evaluator is not None
                else self._evaluate_condition(rule.condition, context)
            )  # noqa: E501
            if triggered:
                since = self._firing_since.get(rule.name, now)
                if rule.name not in self._firing_since:
                    self._firing_since[rule.name] = since
                if now - since >= rule.for_seconds:
                    incident = AlertIncident(
                        rule=rule.name,
                        severity=rule.severity,
                        message=rule.description or rule.name,
                        metadata=dict(context),
                    )  # noqa: E501
                    self._incidents.append(incident)
                    fired.append(incident)
                    for handler in self._handlers:
                        try:
                            handler(incident)
                        except Exception:
                            pass
            else:
                self._firing_since.pop(rule.name, None)
        return fired

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Supports ``burn_rate:slo_name>0.5`` and ``error_budget:slo_name<20``."""
        try:
            metric, rest = condition.split(":", 1)
            if ">" in rest:
                name, threshold = rest.rsplit(">", 1)
                comparison = float(context.get(f"{metric}_{name}", 0.0)) > float(threshold)
                return comparison
            if "<" in rest:
                name, threshold = rest.rsplit("<", 1)
                return float(context.get(f"{metric}_{name}", 0.0)) < float(threshold)
        except (ValueError, IndexError) as exc:
            raise AlertingError(f"malformed condition {condition!r}: {exc}") from exc
        raise AlertingError(f"malformed condition {condition!r}")

    def incidents(self) -> list[AlertIncident]:
        return list(self._incidents)

    def status(self) -> dict[str, Any]:
        return {
            "rules": len(self._rules),
            "incidents": len(self._incidents),
            "enabled": self.config.alerts_enabled,
        }


class BurnRateAlertBuilder:
    """Builds burn-rate alert rules from SLO definitions."""

    def build(self, slo: SloDefinition, warn_burn: float = 0.5, page_burn: float = 2.0) -> list[AlertRule]:
        return [
            AlertRule(
                name=f"{slo.name}-burn-rate-warning",
                condition=f"burn_rate:{slo.name}>{warn_burn}",
                severity="warning",
                description=f"{slo.name} burn rate above {warn_burn}",
            ),
            AlertRule(
                name=f"{slo.name}-burn-rate-critical",
                condition=f"burn_rate:{slo.name}>{page_burn}",
                severity="critical",
                description=f"{slo.name} burn rate above {page_burn}",
            ),
        ]


class DashboardGenerator:
    """Generates Grafana JSON dashboards for platform services."""

    def __init__(self, config: ObservabilityConfig | None = None) -> None:
        self.config = config if config is not None else ObservabilityConfig()

    def _panel(self, uid: str, title: str, expr: str, row: int, span: int = 8, kind: str = "graph") -> dict[str, Any]:
        return {
            "id": uid,
            "title": title,
            "type": kind,
            "span": span,
            "gridPos": {"h": 8, "w": span * 2, "x": 0, "y": row},
            "targets": [{"expr": expr, "refId": "A"}],
        }

    def generate(self, service: str, panels: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not service:
            raise DashboardError("service name must not be empty")
        custom = panels or self._default_panels(service)
        return {
            "dashboard": {
                "title": f"{service} overview",
                "uid": f"{service.replace('-', '_')}_overview",
                "tags": ["ai-router", service],
                "schemaVersion": 39,
                "panels": custom,
                "time": {"from": "now-6h", "to": "now"},
            },
            "overwrite": True,
        }

    def _default_panels(self, service: str) -> list[dict[str, Any]]:
        prefix = service.replace("-", "_")
        return [
            self._panel(1, "Request rate", f"sum(rate({prefix}_request_total[5m]))", 0),
            self._panel(2, "Error rate", f"sum(rate({prefix}_request_failed[5m]))", 0, kind="graph"),
            self._panel(
                3,
                "p95 latency",
                f"histogram_quantile(0.95, sum(rate({prefix}_provider_latency_seconds_bucket[5m])) by (le))",
                0,
            ),  # noqa: E501
            self._panel(4, "Success ratio", f"sum({prefix}_request_success) / sum({prefix}_request_total)", 1),
            self._panel(5, "Memory usage", f'process_resident_memory_bytes{{job="{service}"}}', 1, kind="graph"),
            self._panel(6, "CPU usage", f'rate(process_cpu_seconds_total{{job="{service}"}}[5m])', 1, kind="graph"),
        ]

    def to_json(self, dashboard: dict[str, Any]) -> str:
        return json.dumps(dashboard, indent=2)


def create_alert_engine(config: ObservabilityConfig | None = None, **overrides: Any) -> AlertEngine:
    config = config if config is not None else ObservabilityConfig()
    return AlertEngine(config)


def create_sli_collector(config: ObservabilityConfig | None = None, **overrides: Any) -> SliCollector:
    config = config if config is not None else ObservabilityConfig()
    return SliCollector(config)
