from __future__ import annotations

from typing import Any


class AdminError(Exception):
    """Base class for all admin dashboard errors."""

    status_code = 400
    error_code = "admin_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DashboardError(AdminError):
    status_code = 500
    error_code = "dashboard_error"


class ComponentUnavailableError(AdminError):
    status_code = 503
    error_code = "component_unavailable"

    def __init__(self, component: str, detail: str = "not responding") -> None:
        super().__init__(f"Component {component!r} is {detail}", component=component, detail=detail)


class HealthCheckFailedError(AdminError):
    status_code = 503
    error_code = "health_check_failed"

    def __init__(self, component: str, reason: str) -> None:
        super().__init__(f"Health check failed for {component!r}: {reason}", component=component, reason=reason)


class FeatureFlagNotFoundError(AdminError):
    status_code = 404
    error_code = "feature_flag_not_found"

    def __init__(self, name: str) -> None:
        super().__init__(f"Feature flag {name!r} does not exist", name=name)


class FeatureFlagInvalidError(AdminError):
    status_code = 422
    error_code = "feature_flag_invalid"

    def __init__(self, name: str, reason: str = "invalid value") -> None:
        super().__init__(f"Feature flag {name!r} is {reason}", name=name, reason=reason)


class SettingNotFoundError(AdminError):
    status_code = 404
    error_code = "setting_not_found"

    def __init__(self, key: str) -> None:
        super().__init__(f"Setting {key!r} does not exist", key=key)


class SettingValidationError(AdminError):
    status_code = 422
    error_code = "setting_validation_error"

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(f"Setting {key!r} is invalid: {reason}", key=key, reason=reason)


class MaintenanceActiveError(AdminError):
    status_code = 503
    error_code = "maintenance_active"

    def __init__(self, reason: str = "system is under maintenance") -> None:
        super().__init__(reason)


class AlertNotFoundError(AdminError):
    status_code = 404
    error_code = "alert_not_found"

    def __init__(self, alert_id: str) -> None:
        super().__init__(f"Alert {alert_id!r} does not exist", alert_id=alert_id)


class AnalyticsUnavailableError(AdminError):
    status_code = 503
    error_code = "analytics_unavailable"

    def __init__(self, detail: str = "analytics source is not configured") -> None:
        super().__init__(detail)


class AuditQueryError(AdminError):
    status_code = 422
    error_code = "audit_query_error"

    def __init__(self, reason: str = "invalid audit query") -> None:
        super().__init__(reason)


class ModuleNotFoundError(AdminError):
    status_code = 404
    error_code = "admin_module_not_found"

    def __init__(self, name: str) -> None:
        super().__init__(f"Admin module {name!r} does not exist", name=name)


class MonitorError(AdminError):
    status_code = 500
    error_code = "monitor_error"


class ConfigurationError(AdminError):
    status_code = 500
    error_code = "admin_configuration_error"

    def __init__(self, detail: str = "invalid configuration") -> None:
        super().__init__(detail)
