"""Observability subsystem (Stage 10.10): SLO/SLI, alerts, dashboards."""

from .alerts import (
    AlertEngine,
    AlertIncident,
    AlertRule,
    BurnRateAlertBuilder,
    DashboardGenerator,
    create_alert_engine,
    create_sli_collector,
)
from .config import ObservabilityConfig
from .exceptions import AlertingError, DashboardError, ObservabilityError, SloError
from .slo import SliCollector, SliSnapshot, SloDefinition

__all__ = [
    "ObservabilityConfig",
    "SloDefinition",
    "SliSnapshot",
    "SliCollector",
    "create_sli_collector",
    "AlertRule",
    "AlertIncident",
    "AlertEngine",
    "create_alert_engine",
    "BurnRateAlertBuilder",
    "DashboardGenerator",
    "ObservabilityError",
    "SloError",
    "AlertingError",
    "DashboardError",
]
