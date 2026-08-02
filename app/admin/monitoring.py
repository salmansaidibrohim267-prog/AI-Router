from __future__ import annotations

import json
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from .config import AdminConfig
from .exceptions import MonitorError
from .logging import AdminLogger
from .models import AlertRecord, AlertSeverity, AlertStatus, generate_id


class MonitoringBackend(ABC):
    """Strategy: one observability integration backend."""

    name: str = ""

    def __init__(self, config: AdminConfig | None = None, logger: AdminLogger | None = None) -> None:
        self._config = config or AdminConfig()
        self._logger = logger or AdminLogger(self._config)
        self._lock = threading.Lock()


class PrometheusBackend(MonitoringBackend):
    """In-memory metric store with Prometheus text exposition format output."""

    name = "prometheus"

    def __init__(self, config: AdminConfig | None = None, logger: AdminLogger | None = None) -> None:
        super().__init__(config, logger)
        self._counters: dict[str, dict[str, float]] = {}
        self._gauges: dict[str, dict[str, float]] = {}
        self._histograms: dict[str, dict[str, list[float]]] = {}
        self._prefix = (config or AdminConfig()).prometheus_namespace

    def inc(self, metric: str, labels: dict[str, str] | None = None, amount: float = 1.0) -> None:
        with self._lock:
            self._counters.setdefault(metric, {})[self._key(labels)] = (
                self._counters.get(metric, {}).get(self._key(labels), 0.0) + amount
            )

    def set_gauge(self, metric: str, value: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._gauges.setdefault(metric, {})[self._key(labels)] = value

    def observe(self, metric: str, value: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._histograms.setdefault(metric, {}).setdefault(self._key(labels), []).append(value)

    @staticmethod
    def _key(labels: dict[str, str] | None) -> str:
        if not labels:
            return "{}"
        pairs = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{{{pairs}}}"

    def exposition(self) -> str:
        lines: list[str] = []
        for metric, series in sorted(self._counters.items()):
            lines.append(f"# TYPE {self._prefix}_{metric} counter")
            for labels, value in sorted(series.items()):
                lines.append(f"{self._prefix}_{metric}{labels} {value}")
        for metric, series in sorted(self._gauges.items()):
            lines.append(f"# TYPE {self._prefix}_{metric} gauge")
            for labels, value in sorted(series.items()):
                lines.append(f"{self._prefix}_{metric}{labels} {value}")
        for metric, series in sorted(self._histograms.items()):
            lines.append(f"# TYPE {self._prefix}_{metric}_seconds histogram")
            for labels, values in sorted(series.items()):
                count = len(values)
                total = sum(values)
                lines.append(f"{self._prefix}_{metric}_seconds_bucket{labels} {count}")
                lines.append(f"{self._prefix}_{metric}_seconds_sum{labels} {total}")
                lines.append(f"{self._prefix}_{metric}_seconds_count{labels} {count}")
        return "\n".join(lines) + "\n"

    def counter_value(self, metric: str, labels: dict[str, str] | None = None) -> float:
        with self._lock:
            return self._counters.get(metric, {}).get(self._key(labels), 0.0)


class OpenTelemetryBackend(MonitoringBackend):
    """Records spans/traces in memory, exportable for collection."""

    name = "otel"

    def __init__(self, config: AdminConfig | None = None, logger: AdminLogger | None = None) -> None:
        super().__init__(config, logger)
        self._spans: list[dict[str, Any]] = []
        self._traces: dict[str, list[dict[str, Any]]] = {}

    def start_span(self, name: str, attributes: dict[str, Any] | None = None, parent_id: str = "") -> str:
        span_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._spans.append(
                {
                    "span_id": span_id,
                    "trace_id": self._trace_for(parent_id),
                    "parent_id": parent_id,
                    "name": name,
                    "attributes": attributes or {},
                    "started_at": time.time(),
                }
            )
        return span_id

    def end_span(self, span_id: str, status: str = "OK") -> None:
        for span in self._spans:
            if span["span_id"] == span_id and "ended_at" not in span:
                span["ended_at"] = time.time()
                span["status"] = status
                self._traces.setdefault(span["trace_id"], []).append(span)
                break

    def _trace_for(self, parent_id: str) -> str:
        if not parent_id:
            return uuid.uuid4().hex[:32]
        for span in self._spans:
            if span["span_id"] == parent_id:
                return span["trace_id"]
        return uuid.uuid4().hex[:32]

    def export(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(span) for span in self._spans if "ended_at" in span]

    def trace_count(self) -> int:
        with self._lock:
            return len(self._traces)


class LokiBackend(MonitoringBackend):
    """Structured log shipping target (Loki-compatible JSON stream)."""

    name = "loki"

    def __init__(self, config: AdminConfig | None = None, logger: AdminLogger | None = None) -> None:
        super().__init__(config, logger)
        self._streams: dict[str, list[dict[str, Any]]] = {}

    def ship(self, message: str, labels: dict[str, str] | None = None, level: str = "info") -> None:
        labels = labels or {}
        stream_key = self._stream_key(labels)
        with self._lock:
            self._streams.setdefault(stream_key, []).append(
                {"ts": time.time(), "message": message, "level": level, **labels}
            )

    @staticmethod
    def _stream_key(labels: dict[str, str]) -> str:
        return json.dumps(labels, sort_keys=True)

    def query(self, level: str = "", limit: int = 100) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        with self._lock:
            for stream in self._streams.values():
                entries.extend(stream)
        entries.sort(key=lambda entry: entry["ts"])
        entries.reverse()
        if level:
            entries = [entry for entry in entries if entry.get("level") == level]
        return entries[:limit]

    def push_payload(self) -> dict[str, Any]:
        streams = [
            {"stream": json.loads(key), "values": [[str(int(entry["ts"] * 1e9)), entry["message"]] for entry in entries]}
            for key, entries in self._streams.items()
        ]
        return {"streams": streams}


class AlertmanagerBackend(MonitoringBackend):
    """Fires, acknowledges and resolves alerts (Alertmanager-compatible)."""

    name = "alertmanager"

    def __init__(self, config: AdminConfig | None = None, logger: AdminLogger | None = None) -> None:
        super().__init__(config, logger)
        self._alerts: dict[str, AlertRecord] = {}

    def fire(self, name: str, severity: str | AlertSeverity = "warning", message: str = "", labels: dict[str, str] | None = None) -> AlertRecord:
        if isinstance(severity, str):
            severity = AlertSeverity(severity)
        alert = AlertRecord(
            id=generate_id("alr"),
            name=name,
            severity=severity,
            status=AlertStatus.FIRING,
            message=message,
            labels=labels or {},
        )
        with self._lock:
            self._alerts[alert.id] = alert
        self._logger.log_event("alert.fired", alert_id=alert.id, name=name, severity=severity.value)
        return alert

    def acknowledge(self, alert_id: str, actor: str = "admin") -> AlertRecord:
        alert = self._alerts.get(alert_id)
        if alert is None:
            from .exceptions import AlertNotFoundError

            raise AlertNotFoundError(alert_id)
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = actor
        alert.updated_at = time.time()
        self._logger.log_event("alert.acknowledged", alert_id=alert_id, actor=actor)
        return alert

    def resolve(self, alert_id: str) -> AlertRecord:
        alert = self._alerts.get(alert_id)
        if alert is None:
            from .exceptions import AlertNotFoundError

            raise AlertNotFoundError(alert_id)
        alert.status = AlertStatus.RESOLVED
        alert.updated_at = time.time()
        self._logger.log_event("alert.resolved", alert_id=alert_id)
        return alert

    def list(self, status: str = "") -> list[AlertRecord]:
        if not status:
            return list(self._alerts.values())
        return [alert for alert in self._alerts.values() if alert.status.value == status]

    def active_count(self) -> int:
        return sum(1 for alert in self._alerts.values() if alert.status == AlertStatus.FIRING)

    def payloads(self) -> list[dict[str, Any]]:
        return [alert.to_dict() for alert in self._alerts.values()]


class MonitoringService:
    """Facade over observability backends (Prometheus, OTel, Loki, Alertmanager)."""

    def __init__(
        self,
        config: AdminConfig | None = None,
        logger: AdminLogger | None = None,
        backends: dict[str, MonitoringBackend] | None = None,
    ) -> None:
        self._config = config or AdminConfig()
        self._logger = logger or AdminLogger(self._config)
        self._backends = backends if backends is not None else self._default_backends()

    def _default_backends(self) -> dict[str, MonitoringBackend]:
        backends: dict[str, MonitoringBackend] = {}
        if self._config.prometheus_enabled:
            backends[PrometheusBackend.name] = PrometheusBackend(self._config, self._logger)
        if self._config.otel_enabled:
            backends[OpenTelemetryBackend.name] = OpenTelemetryBackend(self._config, self._logger)
        if self._config.loki_enabled:
            backends[LokiBackend.name] = LokiBackend(self._config, self._logger)
        if self._config.alertmanager_enabled:
            backends[AlertmanagerBackend.name] = AlertmanagerBackend(self._config, self._logger)
        return backends

    @property
    def backends(self) -> dict[str, MonitoringBackend]:
        return dict(self._backends)

    def backend(self, name: str) -> MonitoringBackend:
        backend = self._backends.get(name)
        if backend is None:
            raise MonitorError(f"Monitoring backend {name!r} is not enabled", name=name)
        return backend

    def record_metric(self, metric: str, value: float = 1.0, labels: dict[str, str] | None = None, kind: str = "counter") -> None:
        prometheus = self._backends.get(PrometheusBackend.name)
        if prometheus is None:
            return
        if kind == "counter":
            prometheus.inc(metric, labels=labels, amount=value)
        elif kind == "gauge":
            prometheus.set_gauge(metric, value, labels=labels)
        else:
            prometheus.observe(metric, value, labels=labels)

    def record_span(self, name: str, duration_ms: float, attributes: dict[str, Any] | None = None) -> None:
        otel = self._backends.get(OpenTelemetryBackend.name)
        if otel is None:
            return
        span_id = otel.start_span(name, attributes=attributes)
        otel.end_span(span_id)

    def ship_log(self, message: str, labels: dict[str, str] | None = None, level: str = "info") -> None:
        loki = self._backends.get(LokiBackend.name)
        if loki is not None:
            loki.ship(message, labels=labels, level=level)

    def fire_alert(self, name: str, severity: str = "warning", message: str = "", labels: dict[str, str] | None = None) -> AlertRecord:
        alertmanager = self._backends.get(AlertmanagerBackend.name)
        if alertmanager is None:
            raise MonitorError("Alertmanager backend is not enabled")
        alert = alertmanager.fire(name, severity=severity, message=message, labels=labels)
        self._logger.log_event("alert.fired", alert_id=alert.id, name=name)
        return alert

    def acknowledge_alert(self, alert_id: str, actor: str = "admin") -> AlertRecord:
        alertmanager = self._backends.get(AlertmanagerBackend.name)
        if alertmanager is None:
            raise MonitorError("Alertmanager backend is not enabled")
        return alertmanager.acknowledge(alert_id, actor=actor)

    def resolve_alert(self, alert_id: str) -> AlertRecord:
        alertmanager = self._backends.get(AlertmanagerBackend.name)
        if alertmanager is None:
            raise MonitorError("Alertmanager backend is not enabled")
        return alertmanager.resolve(alert_id)

    def alerts(self, status: str = "") -> list[AlertRecord]:
        alertmanager = self._backends.get(AlertmanagerBackend.name)
        if alertmanager is None:
            return []
        return alertmanager.list(status)

    def status(self) -> dict[str, Any]:
        return {
            "prometheus": self._config.prometheus_enabled,
            "otel": self._config.otel_enabled,
            "loki": self._config.loki_enabled,
            "alertmanager": self._config.alertmanager_enabled,
            "enabled_backends": list(self._backends.keys()),
        }
