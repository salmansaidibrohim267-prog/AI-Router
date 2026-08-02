from __future__ import annotations

from typing import Any

from .config import AdminConfig
from .exceptions import FeatureFlagNotFoundError, MaintenanceActiveError
from .feature_flags import FeatureFlagManager
from .logging import AdminLogger
from .maintenance import MaintenanceManager
from .monitoring import AlertRecord, AlertSeverity, MonitoringService
from .settings import SystemSettingsManager


class OperationsService:
    """Command side of CQRS: administrative mutations.

    All write operations funnel through this service so they can be audited,
    guarded by maintenance mode and broadcast to observers.
    """

    def __init__(
        self,
        config: AdminConfig | None = None,
        flags: FeatureFlagManager | None = None,
        settings: SystemSettingsManager | None = None,
        maintenance: MaintenanceManager | None = None,
        monitoring: MonitoringService | None = None,
        logger: AdminLogger | None = None,
    ) -> None:
        self._config = config or AdminConfig()
        self._flags = flags or FeatureFlagManager(self._config)
        self._settings = settings or SystemSettingsManager()
        self._maintenance = maintenance or MaintenanceManager()
        self._monitoring = monitoring or MonitoringService(self._config)
        self._logger = logger or AdminLogger(self._config)

    @property
    def flags(self) -> FeatureFlagManager:
        return self._flags

    @property
    def settings(self) -> SystemSettingsManager:
        return self._settings

    @property
    def maintenance(self) -> MaintenanceManager:
        return self._maintenance

    @property
    def monitoring(self) -> MonitoringService:
        return self._monitoring

    # ------------------------------------------------------------- feature flags

    def toggle_feature(self, name: str, enabled: bool, actor: str = "admin") -> dict[str, Any]:
        flag = self._flags.set(name, enabled)
        self._logger.log_event("operation.feature_flag", name=name, enabled=enabled, actor=actor)
        return flag.to_dict()

    def register_feature(self, name: str, enabled: bool = False, owner: str = "platform", description: str = "") -> dict[str, Any]:
        flag = self._flags.register(name, enabled=enabled, owner=owner, description=description)
        return flag.to_dict()

    def delete_feature(self, name: str) -> bool:
        if not self._flags.delete(name):
            raise FeatureFlagNotFoundError(name)
        return True

    # ------------------------------------------------------------- settings

    def update_setting(self, key: str, value: Any, actor: str = "admin") -> dict[str, Any]:
        updated = self._settings.set(key, value, actor=actor)
        self._logger.log_event("operation.setting", key=key, actor=actor)
        return {"key": key, "value": updated}

    def reset_setting(self, key: str) -> dict[str, Any]:
        value = self._settings.reset(key)
        return {"key": key, "value": value}

    # ------------------------------------------------------------ maintenance

    def start_maintenance(self, reason: str = "scheduled maintenance", actor: str = "admin") -> dict[str, Any]:
        self._maintenance.start(reason, actor=actor)
        return self._maintenance.status()

    def end_maintenance(self, actor: str = "admin") -> dict[str, Any]:
        self._maintenance.end(actor=actor)
        return self._maintenance.status()

    def schedule_maintenance(self, start: float, end: float, reason: str = "") -> dict[str, Any]:
        self._maintenance.schedule(start, end, reason=reason)
        return self._maintenance.status()

    def require_available(self) -> None:
        self._maintenance.require_available()

    # ---------------------------------------------------------------- alerts

    def fire_alert(
        self,
        name: str,
        severity: str | AlertSeverity = "warning",
        message: str = "",
        labels: dict[str, str] | None = None,
        actor: str = "admin",
    ) -> dict[str, Any]:
        if isinstance(severity, str):
            severity = AlertSeverity(severity)
        alert = self._monitoring.fire_alert(name, severity=severity, message=message, labels=labels)
        self._logger.log_event("operation.alert_fired", alert_id=alert.id, name=name, severity=severity.value, actor=actor)
        return alert.to_dict()

    def acknowledge_alert(self, alert_id: str, actor: str = "admin") -> dict[str, Any]:
        alert = self._monitoring.acknowledge_alert(alert_id, actor=actor)
        return alert.to_dict()

    def resolve_alert(self, alert_id: str) -> dict[str, Any]:
        alert = self._monitoring.resolve_alert(alert_id)
        return alert.to_dict()
