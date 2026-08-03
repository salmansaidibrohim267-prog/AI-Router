from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Any

from .exceptions import AlertNotFoundError, FeatureFlagNotFoundError
from .models import AlertRecord, AuditRecord, FeatureFlag, SettingDefinition, SettingType


class FlagRepository(ABC):
    @abstractmethod
    def create(self, flag: FeatureFlag) -> FeatureFlag:
        raise NotImplementedError

    @abstractmethod
    def get(self, name: str) -> FeatureFlag:
        raise NotImplementedError

    @abstractmethod
    def update(self, flag: FeatureFlag) -> FeatureFlag:
        raise NotImplementedError

    @abstractmethod
    def delete(self, name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list(self) -> list[FeatureFlag]:
        raise NotImplementedError


class SettingsRepository(ABC):
    @abstractmethod
    def get(self, key: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def all(self) -> dict[str, Any]:
        raise NotImplementedError


class AlertRepository(ABC):
    @abstractmethod
    def create(self, alert: AlertRecord) -> AlertRecord:
        raise NotImplementedError

    @abstractmethod
    def get(self, alert_id: str) -> AlertRecord:
        raise NotImplementedError

    @abstractmethod
    def update(self, alert: AlertRecord) -> AlertRecord:
        raise NotImplementedError

    @abstractmethod
    def list(self, status: str = "") -> list[AlertRecord]:
        raise NotImplementedError


class AuditRepository(ABC):
    @abstractmethod
    def record(self, record: AuditRecord) -> AuditRecord:
        raise NotImplementedError

    @abstractmethod
    def query(self, actor: str = "", action: str = "", limit: int = 50) -> list[AuditRecord]:
        raise NotImplementedError


class InMemoryFlagRepository(FlagRepository):
    def __init__(self) -> None:
        self._flags: dict[str, FeatureFlag] = {}
        self._lock = threading.Lock()

    def create(self, flag: FeatureFlag) -> FeatureFlag:
        with self._lock:
            self._flags[flag.name] = flag
        return flag

    def get(self, name: str) -> FeatureFlag:
        with self._lock:
            flag = self._flags.get(name)
        if flag is None:
            raise FeatureFlagNotFoundError(name)
        return flag

    def update(self, flag: FeatureFlag) -> FeatureFlag:
        with self._lock:
            if flag.name not in self._flags:
                raise FeatureFlagNotFoundError(flag.name)
            self._flags[flag.name] = flag
        return flag

    def delete(self, name: str) -> bool:
        with self._lock:
            if name not in self._flags:
                return False
            del self._flags[name]
        return True

    def list(self) -> list[FeatureFlag]:
        with self._lock:
            return list(self._flags.values())


class InMemorySettingsRepository(SettingsRepository):
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            return self._values.get(key)

    def set(self, key: str, value: Any) -> Any:
        with self._lock:
            self._values[key] = value
        return value

    def all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._values)


class InMemoryAlertRepository(AlertRepository):
    def __init__(self) -> None:
        self._alerts: dict[str, AlertRecord] = {}
        self._lock = threading.Lock()

    def create(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            self._alerts[alert.id] = alert
        return alert

    def get(self, alert_id: str) -> AlertRecord:
        with self._lock:
            alert = self._alerts.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(alert_id)
        return alert

    def update(self, alert: AlertRecord) -> AlertRecord:
        with self._lock:
            if alert.id not in self._alerts:
                raise AlertNotFoundError(alert.id)
            self._alerts[alert.id] = alert
        return alert

    def list(self, status: str = "") -> list[AlertRecord]:
        with self._lock:
            alerts = list(self._alerts.values())
        if not status:
            return alerts
        return [alert for alert in alerts if alert.status.value == status]


class InMemoryAuditRepository(AuditRepository):
    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._lock = threading.Lock()

    def record(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            self._records.append(record)
        return record

    def query(self, actor: str = "", action: str = "", limit: int = 50) -> list[AuditRecord]:
        with self._lock:
            records = list(self._records)
        records.reverse()
        if actor:
            records = [record for record in records if record.actor == actor]
        if action:
            records = [record for record in records if record.action == action]
        return records[:limit]


class AdminRepositories:
    def __init__(
        self,
        flags: FlagRepository | None = None,
        settings: SettingsRepository | None = None,
        alerts: AlertRepository | None = None,
        audit: AuditRepository | None = None,
    ) -> None:
        self.flags = flags or InMemoryFlagRepository()
        self.settings = settings or InMemorySettingsRepository()
        self.alerts = alerts or InMemoryAlertRepository()
        self.audit = audit or InMemoryAuditRepository()

    def as_dict(self) -> dict[str, Any]:
        return {"flags": self.flags, "settings": self.settings, "alerts": self.alerts, "audit": self.audit}


DEFAULT_SETTINGS: dict[str, SettingDefinition] = {
    "platform_name": SettingDefinition(
        "platform_name", SettingType.STRING, default="AI Router", description="Display name"
    ),  # noqa: E501
    "max_upload_mb": SettingDefinition(
        "max_upload_mb", SettingType.INTEGER, default=100, description="Max upload size"
    ),  # noqa: E501
    "session_timeout_minutes": SettingDefinition(
        "session_timeout_minutes", SettingType.INTEGER, default=60, description="Session timeout"
    ),  # noqa: E501
    "rate_limit_multiplier": SettingDefinition(
        "rate_limit_multiplier", SettingType.FLOAT, default=1.0, description="Global rate limit factor"
    ),  # noqa: E501
    "maintenance_notice": SettingDefinition(
        "maintenance_notice", SettingType.STRING, default="", description="Maintenance notice"
    ),  # noqa: E501
    "allow_public_signup": SettingDefinition(
        "allow_public_signup", SettingType.BOOLEAN, default=False, description="Public signup"
    ),  # noqa: E501
    "supported_languages": SettingDefinition(
        "supported_languages", SettingType.JSON, default=["en"], description="Languages"
    ),  # noqa: E501
    "secret_overrides": SettingDefinition(
        "secret_overrides", SettingType.STRING, default="", description="Secret overrides", sensitive=True
    ),  # noqa: E501
}
