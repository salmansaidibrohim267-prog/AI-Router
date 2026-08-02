from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class ComponentName(Enum):
    GATEWAY = "gateway"
    BILLING = "billing"
    TENANCY = "tenancy"
    ORGANIZATIONS = "organizations"
    AUTH = "auth"
    MODELS = "models"
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    MCP = "mcp"
    PLUGINS = "plugins"
    STORAGE = "storage"
    RATE_LIMITER = "rate_limiter"


class HealthStatus(Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(Enum):
    FIRING = "firing"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class MaintenanceStatus(Enum):
    NONE = "none"
    ACTIVE = "active"
    SCHEDULED = "scheduled"


class SettingType(Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"


class AdminEventType(Enum):
    FEATURE_FLAG_CHANGED = "feature_flag.changed"
    SETTING_UPDATED = "setting.updated"
    MAINTENANCE_STARTED = "maintenance.started"
    MAINTENANCE_ENDED = "maintenance.ended"
    ALERT_FIRED = "alert.fired"
    ALERT_ACKNOWLEDGED = "alert.acknowledged"
    ALERT_RESOLVED = "alert.resolved"
    MODULE_ACCESSED = "module.accessed"


@dataclass
class FeatureFlag:
    name: str
    enabled: bool = False
    environment: str = "*"
    owner: str = "platform"
    description: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "environment": self.environment,
            "owner": self.owner,
            "description": self.description,
            "updated_at": self.updated_at,
        }


@dataclass
class SettingDefinition:
    key: str
    type: SettingType
    default: Any = None
    description: str = ""
    sensitive: bool = False
    options: list[Any] = field(default_factory=list)

    def validate(self, value: Any) -> bool:
        if self.type == SettingType.STRING:
            return isinstance(value, str)
        if self.type == SettingType.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)
        if self.type == SettingType.FLOAT:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if self.type == SettingType.BOOLEAN:
            return isinstance(value, bool)
        if self.type == SettingType.JSON:
            return isinstance(value, (dict, list))
        return False


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus = HealthStatus.OK
    latency_ms: float = 0.0
    message: str = ""
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "message": self.message,
            "checked_at": self.checked_at,
        }


@dataclass
class SystemStatus:
    environment: str
    version: str
    components: list[ComponentHealth] = field(default_factory=list)
    maintenance: MaintenanceStatus = MaintenanceStatus.NONE
    maintenance_reason: str = ""
    active_alerts: int = 0
    feature_flags_enabled: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def overall(self) -> str:
        if not self.components:
            return HealthStatus.OK.value
        statuses = [component.status for component in self.components]
        if HealthStatus.DOWN in statuses:
            return HealthStatus.DOWN.value
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED.value
        return HealthStatus.OK.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "version": self.version,
            "overall": self.overall,
            "components": [component.to_dict() for component in self.components],
            "maintenance": self.maintenance.value,
            "maintenance_reason": self.maintenance_reason,
            "active_alerts": self.active_alerts,
            "feature_flags_enabled": self.feature_flags_enabled,
            "timestamp": self.timestamp,
        }


@dataclass
class AlertRecord:
    id: str
    name: str
    severity: AlertSeverity = AlertSeverity.WARNING
    status: AlertStatus = AlertStatus.FIRING
    message: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    acknowledged_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.severity.value,
            "status": self.status.value,
            "message": self.message,
            "labels": self.labels,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "acknowledged_by": self.acknowledged_by,
        }


@dataclass
class AnalyticsPoint:
    label: str
    value: float
    dimension: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": self.value, "dimension": self.dimension}


@dataclass
class DashboardReport:
    generated_at: float = field(default_factory=time.time)
    overview: dict[str, Any] = field(default_factory=dict)
    system: dict[str, Any] = field(default_factory=dict)
    analytics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "overview": self.overview,
            "system": self.system,
            "analytics": self.analytics,
        }


@dataclass
class DiagnosticsReport:
    generated_at: float = field(default_factory=time.time)
    environment: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    integrations: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "environment": self.environment,
            "runtime": self.runtime,
            "integrations": self.integrations,
            "checks": self.checks,
        }


@dataclass
class AuditRecord:
    id: str
    actor: str
    action: str
    resource: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "created_at": self.created_at,
        }
