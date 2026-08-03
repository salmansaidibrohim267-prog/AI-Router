"""Threat detection and incident response.

Heuristics detect brute force, credential stuffing, token replay and anomaly
patterns over a sliding window; correlated events are escalated into incidents
with an investigation/containment/resolution lifecycle.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .config import SecurityConfig
from .exceptions import IncidentError, ThreatError  # noqa: F401
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import Incident, IncidentStatus, ThreatEvent, ThreatSeverity, ThreatType, generate_id

_IncidentHandler = Callable[[Incident], Any]


class ThreatDetector:
    """Sliding-window rule evaluation over reported events."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self._events: list[ThreatEvent] = []
        self._lock = threading.Lock()
        self._window = self.config.threat_window_seconds

    def enabled(self) -> bool:
        return self.config.threat_detection_enabled

    def report(
        self, threat_type: ThreatType, source: str = "", target: str = "", details: dict[str, Any] | None = None
    ) -> ThreatEvent:  # noqa: E501
        event = ThreatEvent(
            id=generate_id("threat"),
            threat_type=threat_type,
            severity=self._severity_for(threat_type),
            source=source,
            target=target,
            details=dict(details or {}),
        )
        with self._lock:
            self._events.append(event)
            cutoff = time.time() - self._window
            self._events = [e for e in self._events if e.timestamp >= cutoff]
        self.metrics.record("threat_events", component="threat", amount=1)
        return event

    def _severity_for(self, threat_type: ThreatType) -> ThreatSeverity:
        return {
            ThreatType.BRUTE_FORCE: ThreatSeverity.HIGH,
            ThreatType.CREDENTIAL_STUFFING: ThreatSeverity.HIGH,
            ThreatType.TOKEN_REPLAY: ThreatSeverity.MEDIUM,
            ThreatType.DATA_EXFILTRATION: ThreatSeverity.CRITICAL,
            ThreatType.MALWARE: ThreatSeverity.CRITICAL,
            ThreatType.ANOMALY: ThreatSeverity.LOW,
        }.get(threat_type, ThreatSeverity.LOW)

    def analyze(self) -> list[str]:
        """Return a list of detected threat signals within the window."""
        if not self.config.threat_detection_enabled:
            return []
        signals: list[str] = []
        now = time.time()
        with self._lock:
            events = [e for e in self._events if now - e.timestamp <= self._window]
        sources: dict[str, dict[str, list[ThreatEvent]]] = {}
        for event in events:
            bucket = sources.setdefault(event.source, {}).setdefault(event.threat_type.value, [])
            bucket.append(event)
        for source, types in sources.items():
            brute = types.get(ThreatType.BRUTE_FORCE.value, [])
            stuffing = types.get(ThreatType.CREDENTIAL_STUFFING.value, [])
            replay = types.get(ThreatType.TOKEN_REPLAY.value, [])
            if len(brute) >= self.config.brute_force_threshold:
                signals.append(f"brute_force:{source}")
                self.metrics.record("brute_force_detected", component="threat", amount=1)
            if len(stuffing) >= self.config.brute_force_threshold:
                signals.append(f"credential_stuffing:{source}")
            if len(replay) >= self.config.token_replay_threshold:
                signals.append(f"token_replay:{source}")
            if len(types) >= 3 and len(events) >= self.config.brute_force_threshold * 2:
                signals.append(f"anomaly:{source}")
        return signals

    def recent_events(self, limit: int = 100) -> list[ThreatEvent]:
        with self._lock:
            return list(self._events[-limit:])

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class IncidentManager:
    """Correlates threat signals into incidents and drives resolution."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        detector: ThreatDetector | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.detector = detector if detector is not None else ThreatDetector(config, logger, metrics)
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self._incidents: dict[str, Incident] = {}
        self._handlers: list[_IncidentHandler] = []
        self._lock = threading.Lock()

    def add_handler(self, handler: _IncidentHandler) -> None:
        self._handlers.append(handler)

    def register_event(self, event: ThreatEvent) -> list[Incident]:
        """Register an event and escalate correlated events into incidents."""
        stored = self.detector.report(event.threat_type, event.source, event.target, event.details)
        signals = self.detector.analyze()
        created: list[Incident] = []
        for signal in signals:
            incident = self._escalate(signal, stored)
            if incident is not None:
                created.append(incident)
        return created

    def _escalate(self, signal: str, event: ThreatEvent) -> Incident | None:
        name, source = signal.split(":", 1)
        with self._lock:
            for incident in self._incidents.values():
                if (
                    incident.status in (IncidentStatus.OPEN, IncidentStatus.INVESTIGATING)
                    and incident.summary == signal
                ):  # noqa: E501
                    incident.threat_events.append(event)
                    incident.updated_at = time.time()
                    return None
            incident = Incident(
                id=generate_id("incident"),
                severity=self._severity_for_signal(name),
                summary=signal,
                threat_events=[event],
            )
            self._incidents[incident.id] = incident
        self.metrics.record("incidents_created", component="threat", amount=1)
        self.logger.log_event("incident_created", incident_id=incident.id, summary=signal)
        for handler in self._handlers:
            try:
                handler(incident)
            except Exception:
                pass
        return incident

    def _severity_for_signal(self, name: str) -> ThreatSeverity:
        return {
            "brute_force": ThreatSeverity.HIGH,
            "credential_stuffing": ThreatSeverity.HIGH,
            "token_replay": ThreatSeverity.MEDIUM,
            "anomaly": ThreatSeverity.LOW,
        }.get(name, ThreatSeverity.MEDIUM)

    def escalate(self, signal: str, details: dict[str, Any] | None = None) -> Incident:
        """Manually create an incident from a signal string."""
        with self._lock:
            incident = Incident(
                id=generate_id("incident"),
                severity=ThreatSeverity.MEDIUM,
                summary=signal,
                threat_events=[],
            )
            self._incidents[incident.id] = incident
        self.logger.log_event("incident_escalated", incident_id=incident.id, summary=signal)
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    def list_incidents(self, status: IncidentStatus | None = None) -> list[Incident]:
        incidents = list(self._incidents.values())
        if status is not None:
            incidents = [i for i in incidents if i.status == status]
        return incidents

    def update_status(self, incident_id: str, status: IncidentStatus, summary: str | None = None) -> Incident:
        with self._lock:
            incident = self._incidents.get(incident_id)
            if incident is None:
                raise IncidentError(f"incident {incident_id} not found")
            incident.status = status
            incident.updated_at = time.time()
            if summary is not None:
                incident.summary = summary
            if status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
                incident.resolved_at = time.time()
        self.metrics.record("incident_updates", component="threat")
        self.logger.log_event("incident_updated", incident_id=incident_id, status=status.value)
        return incident

    def count(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for incident in self._incidents.values():
            counts[incident.status.value] = counts.get(incident.status.value, 0) + 1
        return counts


def create_threat_detector(config: SecurityConfig | None = None, **overrides: Any) -> ThreatDetector:
    config = config if config is not None else SecurityConfig()
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    return ThreatDetector(config, logger, metrics)


def create_incident_manager(config: SecurityConfig | None = None, **overrides: Any) -> IncidentManager:
    config = config if config is not None else SecurityConfig()
    detector = overrides.pop("detector", None)
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    if detector is None:
        detector = ThreatDetector(config, logger, metrics)
    return IncidentManager(config, detector, logger, metrics)
