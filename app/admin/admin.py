from __future__ import annotations

from typing import Any

from .analytics import AnalyticsService
from .audit import AuditService
from .config import AdminConfig
from .diagnostics import DiagnosticsService
from .exceptions import ComponentUnavailableError, ModuleNotFoundError
from .feature_flags import FeatureFlagManager
from .health import HealthCheckRegistry, create_default_registry
from .logging import AdminLogger
from .maintenance import MaintenanceManager
from .metrics import AdminMetricsTracker
from .models import DashboardReport, MaintenanceStatus, SystemStatus
from .monitoring import MonitoringService
from .operations import OperationsService
from .settings import SystemSettingsManager
from .statistics import StatisticsService


class AdminModule:
    """Base class for administration modules (tenants, billing, models, ...)."""

    name: str = ""

    def describe(self) -> dict[str, Any]:
        return {"name": self.name}

    def summary(self) -> dict[str, Any]:
        return {"name": self.name}


class TenantsModule(AdminModule):
    name = "tenants"

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._tenants: dict[str, dict[str, Any]] = {}

    def seed(self, tenant_id: str, name: str = "", plan: str = "free", status: str = "active") -> None:
        self._tenants[tenant_id] = {"id": tenant_id, "name": name or tenant_id, "plan": plan, "status": status}

    def list(self) -> list[dict[str, Any]]:
        if self._source is not None:
            return [self._from_source(tenant) for tenant in self._source.list()]
        return list(self._tenants.values())

    def get(self, tenant_id: str) -> dict[str, Any]:
        if self._source is not None:
            return self._from_source(self._source.get(tenant_id))
        tenant = self._tenants.get(tenant_id)
        if tenant is None:
            raise ComponentUnavailableError(self.name, f"tenant {tenant_id!r} unknown")
        return tenant

    def stats(self) -> dict[str, Any]:
        tenants = self.list()
        by_plan: dict[str, int] = {}
        active = 0
        for tenant in tenants:
            by_plan[tenant.get("plan", "unknown")] = by_plan.get(tenant.get("plan", "unknown"), 0) + 1
            if tenant.get("status", "") == "active":
                active += 1
        return {"total": len(tenants), "active": active, "by_plan": by_plan}

    @staticmethod
    def _from_source(tenant: Any) -> dict[str, Any]:
        if isinstance(tenant, dict):
            return tenant
        return {
            "id": getattr(tenant, "id", ""),
            "name": getattr(tenant, "name", ""),
            "plan": getattr(tenant, "plan", "free"),
            "status": getattr(tenant, "status", "active"),
        }  # noqa: E501

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "total": self.stats()["total"]}


class OrganizationsModule(AdminModule):
    name = "organizations"

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._organizations: dict[str, dict[str, Any]] = {}

    def seed(self, org_id: str, name: str = "", status: str = "active") -> None:
        self._organizations[org_id] = {"id": org_id, "name": name or org_id, "status": status}

    def list(self) -> list[dict[str, Any]]:
        if self._source is not None:
            return [self._from_source(org) for org in self._source.list()]
        return list(self._organizations.values())

    def get(self, org_id: str) -> dict[str, Any]:
        if self._source is not None:
            return self._from_source(self._source.get(org_id))
        org = self._organizations.get(org_id)
        if org is None:
            raise ComponentUnavailableError(self.name, f"organization {org_id!r} unknown")
        return org

    def stats(self) -> dict[str, Any]:
        organizations = self.list()
        active = sum(1 for org in organizations if org.get("status", "") == "active")
        return {"total": len(organizations), "active": active}

    @staticmethod
    def _from_source(org: Any) -> dict[str, Any]:
        if isinstance(org, dict):
            return org
        return {
            "id": getattr(org, "id", ""),
            "name": getattr(org, "name", ""),
            "status": getattr(org, "status", "active"),
        }  # noqa: E501

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "total": self.stats()["total"]}


class UsersModule(AdminModule):
    name = "users"

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._users: dict[str, dict[str, Any]] = {}

    def seed(self, user_id: str, username: str = "", role: str = "user", status: str = "active") -> None:
        self._users[user_id] = {"id": user_id, "username": username or user_id, "role": role, "status": status}

    def list(self) -> list[dict[str, Any]]:
        if self._source is not None:
            return [self._from_source(user) for user in self._source.list()]
        return list(self._users.values())

    def get(self, user_id: str) -> dict[str, Any]:
        if self._source is not None:
            return self._from_source(self._source.get(user_id))
        user = self._users.get(user_id)
        if user is None:
            raise ComponentUnavailableError(self.name, f"user {user_id!r} unknown")
        return user

    def stats(self) -> dict[str, Any]:
        users = self.list()
        by_role: dict[str, int] = {}
        active = 0
        for user in users:
            by_role[user.get("role", "user")] = by_role.get(user.get("role", "user"), 0) + 1
            if user.get("status", "") == "active":
                active += 1
        return {"total": len(users), "active": active, "by_role": by_role}

    @staticmethod
    def _from_source(user: Any) -> dict[str, Any]:
        if isinstance(user, dict):
            return user
        return {
            "id": getattr(user, "id", ""),
            "username": getattr(user, "username", ""),
            "role": getattr(user, "role", "user"),
            "status": getattr(user, "status", "active"),
        }  # noqa: E501

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "total": self.stats()["total"]}


class BillingModule(AdminModule):
    name = "billing"

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager
        self._subscriptions: list[dict[str, Any]] = []

    def seed_subscription(
        self, subscription_id: str, plan_id: str = "free", status: str = "active", price: float = 0.0
    ) -> None:  # noqa: E501
        self._subscriptions.append({"id": subscription_id, "plan_id": plan_id, "status": status, "price": price})

    def subscriptions(self) -> list[dict[str, Any]]:
        if self._manager is not None:
            return [subscription.to_dict() for subscription in self._manager.list_subscriptions()]
        return list(self._subscriptions)

    def invoices(self, tenant_id: str = "") -> list[Any]:
        if self._manager is not None:
            return self._manager.list_invoices(tenant_id)
        return []

    def payments(self, tenant_id: str = "") -> list[Any]:
        if self._manager is not None:
            return self._manager.list_payments(tenant_id)
        return []

    def revenue(self) -> dict[str, Any]:
        if self._manager is not None:
            return self._manager.metrics_summary()
        subscriptions = self.subscriptions()
        mrr = sum(float(sub.get("price", 0.0)) for sub in subscriptions if sub.get("status") in ("active", "trialing"))
        return {"mrr": mrr, "arr": mrr * 12, "active_subscriptions": len(subscriptions)}

    def stats(self) -> dict[str, Any]:
        subscriptions = self.subscriptions()
        by_plan: dict[str, int] = {}
        active = 0
        for subscription in subscriptions:
            by_plan[subscription.get("plan_id", "unknown")] = by_plan.get(subscription.get("plan_id", "unknown"), 0) + 1
            if subscription.get("status", "") == "active":
                active += 1
        return {"total_subscriptions": len(subscriptions), "active": active, "by_plan": by_plan}

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, **self.stats()}


class ModelsModule(AdminModule):
    name = "models"

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._models: dict[str, dict[str, Any]] = {}

    def seed(self, model_id: str, provider: str = "openai", status: str = "active") -> None:
        self._models[model_id] = {"id": model_id, "provider": provider, "status": status}

    def list(self) -> list[dict[str, Any]]:
        if self._source is not None:
            return [self._from_source(model) for model in self._source.list()]
        return list(self._models.values())

    def get(self, model_id: str) -> dict[str, Any]:
        if self._source is not None:
            return self._from_source(self._source.get(model_id))
        model = self._models.get(model_id)
        if model is None:
            raise ComponentUnavailableError(self.name, f"model {model_id!r} unknown")
        return model

    def stats(self) -> dict[str, Any]:
        models = self.list()
        by_provider: dict[str, int] = {}
        for model in models:
            by_provider[model.get("provider", "unknown")] = by_provider.get(model.get("provider", "unknown"), 0) + 1
        return {"total": len(models), "by_provider": by_provider}

    @staticmethod
    def _from_source(model: Any) -> dict[str, Any]:
        if isinstance(model, dict):
            return model
        return {
            "id": getattr(model, "id", ""),
            "provider": getattr(model, "provider", "unknown"),
            "status": getattr(model, "status", "active"),
        }  # noqa: E501

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, "total": self.stats()["total"]}


class KnowledgeModule(AdminModule):
    name = "knowledge"

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._documents: list[dict[str, Any]] = []

    def seed_document(self, document_id: str, title: str = "", chunks: int = 1) -> None:
        self._documents.append({"id": document_id, "title": title or document_id, "chunks": chunks})

    def documents(self) -> list[dict[str, Any]]:
        if self._source is not None and hasattr(self._source, "documents"):
            return self._source.documents()
        return list(self._documents)

    def stats(self) -> dict[str, Any]:
        documents = self.documents()
        chunks = sum(int(document.get("chunks", 0)) for document in documents)
        return {"total_documents": len(documents), "total_chunks": chunks}

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, **self.stats()}


class MemoryModule(AdminModule):
    name = "memory"

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._sessions: list[dict[str, Any]] = []

    def seed_session(self, session_id: str, messages: int = 0) -> None:
        self._sessions.append({"id": session_id, "messages": messages})

    def sessions(self) -> list[dict[str, Any]]:
        if self._source is not None and hasattr(self._source, "sessions"):
            return self._source.sessions()
        return list(self._sessions)

    def stats(self) -> dict[str, Any]:
        sessions = self.sessions()
        messages = sum(int(session.get("messages", 0)) for session in sessions)
        return {"total_sessions": len(sessions), "total_messages": messages}

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, **self.stats()}


class MCPModule(AdminModule):
    name = "mcp"

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._servers: list[dict[str, Any]] = []

    def seed_server(self, server_id: str, name: str = "", status: str = "connected") -> None:
        self._servers.append({"id": server_id, "name": name or server_id, "status": status})

    def servers(self) -> list[dict[str, Any]]:
        if self._source is not None and hasattr(self._source, "names"):
            return [{"id": name, "name": name, "status": "connected"} for name in self._source.names()]
        return list(self._servers)

    def stats(self) -> dict[str, Any]:
        servers = self.servers()
        connected = sum(1 for server in servers if server.get("status", "") == "connected")
        return {"total_servers": len(servers), "connected": connected}

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, **self.stats()}


class PluginsModule(AdminModule):
    name = "plugins"

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._plugins: list[dict[str, Any]] = []

    def seed_plugin(self, plugin_id: str, name: str = "", enabled: bool = True) -> None:
        self._plugins.append({"id": plugin_id, "name": name or plugin_id, "enabled": enabled})

    def plugins(self) -> list[dict[str, Any]]:
        if self._source is not None and hasattr(self._source, "get_enabled"):
            enabled = [
                {"id": name, "name": name, "enabled": True}
                for name in (getattr(p, "name", "") for p in self._source.get_enabled())
            ]  # noqa: E501
            return enabled + [{"id": name, "name": name, "enabled": False} for name in self._source.disabled()]
        return list(self._plugins)

    def stats(self) -> dict[str, Any]:
        plugins = self.plugins()
        enabled = sum(1 for plugin in plugins if plugin.get("enabled", False))
        return {"total_plugins": len(plugins), "enabled": enabled}

    def summary(self) -> dict[str, Any]:
        return {"name": self.name, **self.stats()}


class AdminAPI:
    """Facade for the admin dashboard backend.

    Exposes the five core views (dashboard, overview, health, statistics,
    system_status) plus per-module administration, observability endpoints,
    diagnostics, audit and operations.
    """

    def __init__(
        self,
        config: AdminConfig | None = None,
        logger: AdminLogger | None = None,
        metrics: AdminMetricsTracker | None = None,
        flags: FeatureFlagManager | None = None,
        settings: SystemSettingsManager | None = None,
        maintenance: MaintenanceManager | None = None,
        health: HealthCheckRegistry | None = None,
        analytics: AnalyticsService | None = None,
        statistics: StatisticsService | None = None,
        monitoring: MonitoringService | None = None,
        diagnostics: DiagnosticsService | None = None,
        audit: AuditService | None = None,
        operations: OperationsService | None = None,
        tenants: TenantsModule | None = None,
        organizations: OrganizationsModule | None = None,
        users: UsersModule | None = None,
        billing: BillingModule | None = None,
        models: ModelsModule | None = None,
        knowledge: KnowledgeModule | None = None,
        memory: MemoryModule | None = None,
        mcp: MCPModule | None = None,
        plugins: PluginsModule | None = None,
    ) -> None:
        self._config = config or AdminConfig()
        self._logger = logger or AdminLogger(self._config)
        self._metrics = metrics or AdminMetricsTracker(self._config, self._logger)
        self._flags = flags or FeatureFlagManager(self._config, logger=self._logger)
        self._settings = settings or SystemSettingsManager(logger=self._logger)
        self._maintenance = maintenance or MaintenanceManager(self._logger)
        self._health = health or create_default_registry()
        self._analytics = analytics or AnalyticsService(self._config, self._logger)
        self._statistics = statistics or StatisticsService(self._config, self._logger)
        self._monitoring = monitoring or MonitoringService(self._config, self._logger)
        self._diagnostics = diagnostics or DiagnosticsService(self._config, self._logger)
        self._audit = audit or AuditService(self._config, logger=self._logger)
        self._operations = operations or OperationsService(
            self._config, self._flags, self._settings, self._maintenance, self._monitoring, self._logger
        )  # noqa: E501
        self._tenants = tenants or TenantsModule()
        self._organizations = organizations or OrganizationsModule()
        self._users = users or UsersModule()
        self._billing = billing or BillingModule()
        self._models = models or ModelsModule()
        self._knowledge = knowledge or KnowledgeModule()
        self._memory = memory or MemoryModule()
        self._mcp = mcp or MCPModule()
        self._plugins = plugins or PluginsModule()
        self._modules: dict[str, AdminModule] = {
            self._tenants.name: self._tenants,
            self._organizations.name: self._organizations,
            self._users.name: self._users,
            self._billing.name: self._billing,
            self._models.name: self._models,
            self._knowledge.name: self._knowledge,
            self._memory.name: self._memory,
            self._mcp.name: self._mcp,
            self._plugins.name: self._plugins,
        }

    # ------------------------------------------------------------------ views

    @property
    def config(self) -> AdminConfig:
        return self._config

    @property
    def metrics(self) -> AdminMetricsTracker:
        return self._metrics

    @property
    def flags(self) -> FeatureFlagManager:
        return self._flags

    @property
    def maintenance(self) -> MaintenanceManager:
        return self._maintenance

    @property
    def analytics(self) -> AnalyticsService:
        return self._analytics

    @property
    def monitoring(self) -> MonitoringService:
        return self._monitoring

    @property
    def audit(self) -> AuditService:
        return self._audit

    @property
    def operations(self) -> OperationsService:
        return self._operations

    @property
    def modules(self) -> dict[str, AdminModule]:
        return dict(self._modules)

    def module(self, name: str) -> AdminModule:
        module = self._modules.get(name)
        if module is None:
            raise ModuleNotFoundError(name)
        return module

    def overview(self) -> dict[str, Any]:
        self._metrics.record_request("admin.overview")
        return {
            "tenants": self._tenants.stats(),
            "organizations": self._organizations.stats(),
            "users": self._users.stats(),
            "billing": self._billing.stats(),
            "models": self._models.stats(),
            "knowledge": self._knowledge.stats(),
            "memory": self._memory.stats(),
            "mcp": self._mcp.stats(),
            "plugins": self._plugins.stats(),
        }

    def health(self, component: str = "") -> list[dict[str, Any]]:
        self._metrics.record_request("admin.health")
        results = self._health.run(component=component)
        if component and not results:
            raise ComponentUnavailableError(component)
        return [result.to_dict() for result in results]

    def health_component(self, component: str) -> dict[str, Any]:
        return self._health.run_component(component).to_dict()

    def statistics(self) -> dict[str, Any]:
        self._metrics.record_request("admin.statistics")
        return {
            "requests": self._statistics.report(),
            "analytics": self._analytics.summary(),
        }

    def system_status(self) -> SystemStatus:
        self._metrics.record_request("admin.system_status")
        components = self._health.run()
        maintenance = self._maintenance.status()
        return SystemStatus(
            environment=self._config.environment,
            version=self._config.version,
            components=components,
            maintenance=MaintenanceStatus(maintenance["status"]),
            maintenance_reason=maintenance["reason"],
            active_alerts=len(self._monitoring.alerts("firing")),
            feature_flags_enabled=self._flags.enabled_count(),
        )

    def dashboard(self) -> DashboardReport:
        self._metrics.record_request("admin.dashboard")
        return DashboardReport(
            overview=self.overview(),
            system=self.system_status().to_dict(),
            analytics=self.statistics(),
        )

    # ------------------------------------------------------------- operations

    def toggle_feature(self, name: str, enabled: bool, actor: str = "admin") -> dict[str, Any]:
        return self._operations.toggle_feature(name, enabled, actor=actor)

    def register_feature(
        self, name: str, enabled: bool = False, owner: str = "platform", description: str = ""
    ) -> dict[str, Any]:  # noqa: E501
        return self._operations.register_feature(name, enabled=enabled, owner=owner, description=description)

    def delete_feature(self, name: str) -> bool:
        return self._operations.delete_feature(name)

    def feature_flags(self) -> list[dict[str, Any]]:
        return [flag.to_dict() for flag in self._flags.list()]

    def update_setting(self, key: str, value: Any, actor: str = "admin") -> dict[str, Any]:
        return self._operations.update_setting(key, value, actor=actor)

    def reset_setting(self, key: str) -> dict[str, Any]:
        return self._operations.reset_setting(key)

    def settings(self) -> dict[str, Any]:
        return self._settings.all()

    def setting(self, key: str) -> dict[str, Any]:
        return {"key": key, "value": self._settings.get(key)}

    def start_maintenance(self, reason: str = "scheduled maintenance", actor: str = "admin") -> dict[str, Any]:
        return self._operations.start_maintenance(reason, actor=actor)

    def end_maintenance(self, actor: str = "admin") -> dict[str, Any]:
        return self._operations.end_maintenance(actor=actor)

    def schedule_maintenance(self, start: float, end: float, reason: str = "") -> dict[str, Any]:
        return self._operations.schedule_maintenance(start, end, reason=reason)

    def maintenance_status(self) -> dict[str, Any]:
        return self._maintenance.status()

    def fire_alert(
        self, name: str, severity: str = "warning", message: str = "", labels: dict[str, str] | None = None
    ) -> dict[str, Any]:  # noqa: E501
        return self._operations.fire_alert(name, severity=severity, message=message, labels=labels)

    def acknowledge_alert(self, alert_id: str, actor: str = "admin") -> dict[str, Any]:
        return self._operations.acknowledge_alert(alert_id, actor=actor)

    def resolve_alert(self, alert_id: str) -> dict[str, Any]:
        return self._operations.resolve_alert(alert_id)

    def alerts(self, status: str = "") -> list[dict[str, Any]]:
        return [alert.to_dict() for alert in self._monitoring.alerts(status)]

    # -------------------------------------------------------- observability

    def prometheus_metrics(self) -> str:
        prometheus = self._monitoring.backends.get("prometheus")
        if prometheus is None:
            return ""
        return prometheus.exposition()

    def otel_traces(self) -> list[dict[str, Any]]:
        otel = self._monitoring.backends.get("otel")
        if otel is None:
            return []
        return otel.export()

    def loki_logs(self, level: str = "", limit: int = 100) -> list[dict[str, Any]]:
        loki = self._monitoring.backends.get("loki")
        if loki is None:
            return []
        return loki.query(level=level, limit=limit)

    def audit_log(self, actor: str = "", action: str = "", limit: int = 50) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self._audit.query(actor=actor, action=action, limit=limit)]

    def record_audit(
        self, actor: str, action: str, resource: str = "", details: dict[str, Any] | None = None
    ) -> dict[str, Any]:  # noqa: E501
        return self._audit.record(actor, action, resource=resource, details=details).to_dict()

    def diagnostics(self) -> dict[str, Any]:
        return self._diagnostics.collect().to_dict()

    def runtime_stats(self) -> dict[str, Any]:
        return {
            "environment": self._diagnostics.environment(),
            "runtime": self._diagnostics.runtime(),
            "integrations": self._diagnostics.integrations(),
        }

    def metrics_report(self) -> dict[str, Any]:
        return self._metrics.report()

    def monitor_status(self) -> dict[str, Any]:
        return self._monitoring.status()
