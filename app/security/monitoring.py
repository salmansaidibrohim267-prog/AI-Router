"""Security monitoring: SIEM integrations and alert routing.

``SiemSink`` is the strategy interface; stdout, Splunk (HTTP Event Collector),
Elastic (bulk API) and Datadog (logs API) sinks are provided with injectable
transports for tests.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from .config import SecurityConfig
from .exceptions import MonitoringError
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import SecurityAlert, ThreatSeverity, generate_id


class SiemSink(ABC):
    """SIEM / observability sink strategy."""

    name = "stdout"

    def __init__(self, config: SecurityConfig) -> None:
        self.config = config

    async def start(self) -> None:  # noqa: B027
        pass

    async def close(self) -> None:  # noqa: B027
        pass

    @abstractmethod
    async def emit(self, payload: dict[str, Any]) -> bool:
        """Deliver an event payload; return True when accepted."""


class StdoutSink(SiemSink):
    """Writes JSON payloads to stdout (default)."""

    name = "stdout"

    async def emit(self, payload: dict[str, Any]) -> bool:
        print(json.dumps(payload, default=str, sort_keys=True))
        return True


class SplunkSink(SiemSink):
    """Splunk HTTP Event Collector.

    ``siem_config``: ``url`` (HEC endpoint), ``token``, ``index``, ``source``,
    ``source_type``. ``transport(backend, method, url, body=None)`` injectable.
    """

    name = "splunk"

    def __init__(self, config: SecurityConfig, transport: Any = None) -> None:
        super().__init__(config)
        self.transport = transport
        cfg = config.siem_config
        self.url = cfg.get("url", "https://hec.example.com:8088/services/collector/event").rstrip("/")
        self.token = cfg.get("token", "")
        self.index = cfg.get("index", "main")
        self.source = cfg.get("source", "ai-router-security")

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Splunk {self.token}", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Splunk {self.token}"
        return headers

    async def emit(self, payload: dict[str, Any]) -> bool:
        body = {
            "index": self.index,
            "source": self.source,
            "sourcetype": payload.get("source_type", "_json"),
            "event": payload,
        }
        try:
            response = await self.transport(self, "POST", self.url, body=body)
        except Exception as exc:
            raise MonitoringError(f"splunk emit failed: {exc}") from exc
        return bool(isinstance(response, dict) and response.get("code") in (0, "0", None))


class ElasticSink(SiemSink):
    """Elasticsearch bulk ingest.

    ``siem_config``: ``url`` (with index, e.g. ``/security-events/_doc``),
    ``api_key``. ``transport(backend, method, url, body=None)`` injectable.
    """

    name = "elastic"

    def __init__(self, config: SecurityConfig, transport: Any = None) -> None:
        super().__init__(config)
        self.transport = transport
        cfg = config.siem_config
        self.url = cfg.get("url", "http://127.0.0.1:9200/security-events/_doc")
        self.api_key = cfg.get("api_key", "")
        self._headers = {"Content-Type": "application/json"}
        if self.api_key:
            self._headers["Authorization"] = f"ApiKey {self.api_key}"

    async def emit(self, payload: dict[str, Any]) -> bool:
        try:
            response = await self.transport(self, "POST", self.url, body=payload)
        except Exception as exc:
            raise MonitoringError(f"elastic emit failed: {exc}") from exc
        return bool(isinstance(response, dict) and response.get("result") in ("created", "updated", "indexed", None))


class DatadogSink(SiemSink):
    """Datadog logs API.

    ``siem_config``: ``url`` (DD-US-1 default), ``api_key``. ``transport``
    injectable.
    """

    name = "datadog"

    def __init__(self, config: SecurityConfig, transport: Any = None) -> None:
        super().__init__(config)
        self.transport = transport
        cfg = config.siem_config
        self.url = cfg.get("url", "https://http-intake.logs.datadoghq.com/api/v2/logs")
        self.api_key = cfg.get("api_key", "")

    async def emit(self, payload: dict[str, Any]) -> bool:
        body = {
            "ddsource": "ai-router-security",
            "ddtags": payload.get("tags", ""),
            "message": json.dumps(payload, default=str),
        }  # noqa: E501
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["DD-API-KEY"] = self.api_key
        try:
            response = await self.transport(self, "POST", self.url, body=body)
        except Exception as exc:
            raise MonitoringError(f"datadog emit failed: {exc}") from exc
        return response is None or bool(response)


class SiemRegistry:
    """Strategy registry for SIEM sinks."""

    def __init__(self) -> None:
        self._factories: dict[str, Any] = {
            "stdout": lambda config: StdoutSink(config),
            "splunk": lambda config: SplunkSink(config),
            "elastic": lambda config: ElasticSink(config),
            "datadog": lambda config: DatadogSink(config),
        }

    def register(self, name: str, factory: Any) -> None:
        self._factories[name] = factory

    def create(self, config: SecurityConfig) -> SiemSink:
        name = config.siem_backend
        factory = self._factories.get(name)
        if factory is None:
            raise MonitoringError(f"unknown siem backend {name!r}")
        return factory(config)


class MonitoringService:
    """Routes security alerts to the configured SIEM sink."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        sink: SiemSink | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self.sink = sink
        self._alerts: list[SecurityAlert] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        if self.sink is None:
            self.sink = SiemRegistry().create(self.config)
        await self.sink.start()
        self._running = True

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self.sink is not None:
            await self.sink.close()

    async def send_alert(
        self,
        message: str,
        severity: ThreatSeverity = ThreatSeverity.MEDIUM,
        source: str = "security",
        metadata: dict[str, Any] | None = None,
    ) -> SecurityAlert:
        alert = SecurityAlert(
            id=generate_id("alert"),
            severity=severity,
            message=message,
            source=source,
            metadata=dict(metadata or {}),
        )
        self._alerts.append(alert)
        payload = {
            "type": "security_alert",
            "id": alert.id,
            "severity": severity.value,
            "message": message,
            "source": source,
            "timestamp": alert.timestamp,
            "metadata": alert.metadata,
            "source_type": f"security:{severity.value}",
            "tags": f"env:{self.config.environment},region:{self.config.region}",
        }
        if self.config.monitoring_enabled:
            if self.sink is None:
                await self.start()
            try:
                await self.sink.emit(payload)
            except MonitoringError as exc:
                self.metrics.record("alert_emit_failures", component="monitoring")
                self.logger.log_event("alert_emit_failed", alert_id=alert.id, error=str(exc))
                raise
            self.metrics.record("alerts_sent", component="monitoring")
            self.logger.log_event("alert_sent", alert_id=alert.id, severity=severity.value)
        return alert

    def alert_count(self) -> int:
        return len(self._alerts)

    def recent_alerts(self, limit: int = 50) -> list[SecurityAlert]:
        return list(self._alerts[-limit:])

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.monitoring_enabled,
            "backend": self.sink.name if self.sink is not None else self.config.siem_backend,
            "running": self._running,
            "alerts": len(self._alerts),
        }


def create_monitoring_service(config: SecurityConfig | None = None, **overrides: Any) -> MonitoringService:
    config = config if config is not None else SecurityConfig()
    sink = overrides.pop("sink", None)
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    return MonitoringService(config, sink, logger, metrics)


def create_siem_sink(config: SecurityConfig, **overrides: Any) -> SiemSink:
    registry = overrides.pop("registry", None) or SiemRegistry()
    sink = registry.create(config)
    transport = overrides.pop("transport", None)
    if transport is not None and isinstance(sink, (SplunkSink, ElasticSink, DatadogSink)):
        sink.transport = transport
    return sink
