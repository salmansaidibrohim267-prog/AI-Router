"""Stage 10.6 — Admin Dashboard backend tests."""
from __future__ import annotations

import time

import pytest

from app.admin import (
    AdminAPI,
    AdminConfig,
    AdminError,
    AdminLogger,
    AdminMetricsTracker,
    AdminModule,
    AdminRepositories,
    AlertNotFoundError,
    AlertRecord,
    AlertSeverity,
    AlertStatus,
    AlertmanagerBackend,
    AnalyticsService,
    AnalyticsUnavailableError,
    AuditQueryError,
    AuditService,
    BillingModule,
    CallableHealthCheck,
    ComponentUnavailableError,
    ConfigurationError,
    DashboardError,
    DiagnosticsService,
    FeatureFlag,
    FeatureFlagInvalidError,
    FeatureFlagManager,
    FeatureFlagNotFoundError,
    GatewayHealthCheck,
    HealthCheck,
    HealthCheckFailedError,
    HealthCheckRegistry,
    HealthStatus,
    InMemoryAlertRepository,
    InMemoryAuditRepository,
    InMemoryFlagRepository,
    InMemorySettingsRepository,
    KnowledgeModule,
    LokiBackend,
    MCPModule,
    MaintenanceActiveError,
    MaintenanceManager,
    MaintenanceStatus,
    MemoryModule,
    ModelsModule,
    ModuleNotFoundError,
    MonitorError,
    MonitoringService,
    OpenTelemetryBackend,
    OperationsService,
    OrganizationsModule,
    PluginsModule,
    PrometheusBackend,
    SettingDefinition,
    SettingNotFoundError,
    SettingType,
    SettingValidationError,
    StatisticsService,
    SystemSettingsManager,
    SystemStatus,
    TenantsModule,
    UsersModule,
    create_admin_api,
    create_default_registry,
    generate_id,
)
from app.admin.models import (
    AdminEventType,
    AnalyticsPoint,
    AuditRecord,
    ComponentHealth,
    ComponentName,
    DashboardReport,
    DiagnosticsReport,
)
from app.admin.repositories import DEFAULT_SETTINGS


# ------------------------------------------------------------------ config


class TestAdminConfig:
    def test_defaults(self):
        config = AdminConfig()
        assert config.environment == "production"
        assert config.prometheus_enabled is True
        assert config.health_timeout_seconds == 5.0
        assert config.track_metrics is True
        assert config.log_events is True
        assert config.audit_enabled is True

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("ADM_ENVIRONMENT", "staging")
        monkeypatch.setenv("ADM_VERSION", "2.1.3")
        monkeypatch.setenv("ADM_PROMETHEUS", "0")
        monkeypatch.setenv("ADM_OTEL", "0")
        monkeypatch.setenv("ADM_LOKI", "0")
        monkeypatch.setenv("ADM_ALERTMANAGER", "0")
        monkeypatch.setenv("ADM_HEALTH_TIMEOUT", "9")
        monkeypatch.setenv("ADM_TRACK_METRICS", "0")
        monkeypatch.setenv("ADM_LOG_EVENTS", "0")
        monkeypatch.setenv("ADM_AUDIT", "0")
        config = AdminConfig.from_env()
        assert config.environment == "staging"
        assert config.version == "2.1.3"
        assert config.prometheus_enabled is False
        assert config.otel_enabled is False
        assert config.loki_enabled is False
        assert config.alertmanager_enabled is False
        assert config.health_timeout_seconds == 9.0
        assert config.track_metrics is False
        assert config.log_events is False
        assert config.audit_enabled is False

    def test_integration_enabled(self):
        config = AdminConfig()
        assert config.integration_enabled("prometheus") is True
        assert config.integration_enabled("unknown") is False
        disabled = AdminConfig(prometheus_enabled=False)
        assert disabled.integration_enabled("prometheus") is False


# ---------------------------------------------------------------- exceptions


class TestExceptions:
    def test_base_error(self):
        error = AdminError("boom", code=7)
        assert error.message == "boom"
        assert error.details == {"code": 7}
        assert str(error) == "boom"
        assert error.status_code == 400
        assert error.error_code == "admin_error"

    def test_subclasses(self):
        assert ComponentUnavailableError("db").status_code == 503
        assert HealthCheckFailedError("a", "b").status_code == 503
        assert FeatureFlagNotFoundError("x").status_code == 404
        assert FeatureFlagInvalidError("x").status_code == 422
        assert SettingNotFoundError("x").status_code == 404
        assert SettingValidationError("x", "y").status_code == 422
        assert MaintenanceActiveError().status_code == 503
        assert AlertNotFoundError("a").status_code == 404
        assert AnalyticsUnavailableError().status_code == 503
        assert AuditQueryError().status_code == 422
        assert ModuleNotFoundError("m").status_code == 404
        assert MonitorError("x").status_code == 500
        assert DashboardError("x").status_code == 500
        assert ConfigurationError("x").status_code == 500
        assert ComponentUnavailableError("db", "offline").details["detail"] == "offline"


# ------------------------------------------------------------------- logging


class TestAdminLogger:
    def test_log_event(self):
        logger = AdminLogger(AdminConfig(log_events=True))
        logger.log_event("thing.done", key="value")
        assert logger.events[0]["event"] == "admin_thing.done"
        assert logger.events[0]["data"] == {"key": "value"}

    def test_log_event_disabled(self):
        logger = AdminLogger(AdminConfig(log_events=False))
        logger.log_event("thing.done")
        assert logger.events == []


# --------------------------------------------------------------------- models


class TestModels:
    def test_generate_id(self):
        assert generate_id("abc").startswith("abc_")

    def test_feature_flag_to_dict(self):
        flag = FeatureFlag(name="x", enabled=True, owner="me", description="d")
        data = flag.to_dict()
        assert data["name"] == "x"
        assert data["enabled"] is True
        assert data["owner"] == "me"
        assert data["description"] == "d"

    def test_setting_definition_validate(self):
        assert SettingDefinition("s", SettingType.STRING).validate("v")
        assert not SettingDefinition("s", SettingType.STRING).validate(1)
        assert SettingDefinition("i", SettingType.INTEGER).validate(3)
        assert not SettingDefinition("i", SettingType.INTEGER).validate(3.0)
        assert not SettingDefinition("i", SettingType.INTEGER).validate(True)
        assert SettingDefinition("f", SettingType.FLOAT).validate(3)
        assert SettingDefinition("f", SettingType.FLOAT).validate(2.5)
        assert not SettingDefinition("f", SettingType.FLOAT).validate("x")
        assert SettingDefinition("b", SettingType.BOOLEAN).validate(True)
        assert not SettingDefinition("b", SettingType.BOOLEAN).validate(1)
        assert SettingDefinition("j", SettingType.JSON).validate({"a": 1})
        assert SettingDefinition("j", SettingType.JSON).validate([1, 2])
        assert not SettingDefinition("j", SettingType.JSON).validate("x")

    def test_component_health_to_dict(self):
        health = ComponentHealth(name="gateway", status=HealthStatus.DOWN, latency_ms=1.5, message="nope")
        data = health.to_dict()
        assert data["status"] == "down"
        assert data["latency_ms"] == 1.5
        assert data["message"] == "nope"
        assert "checked_at" in data

    def test_system_status_overall(self):
        ok = SystemStatus(environment="prod", version="1", components=[])
        assert ok.overall == HealthStatus.OK.value
        degraded = SystemStatus(
            environment="prod",
            version="1",
            components=[ComponentHealth(name="a"), ComponentHealth(name="b", status=HealthStatus.DEGRADED)],
        )
        assert degraded.overall == HealthStatus.DEGRADED.value
        down = SystemStatus(
            environment="prod",
            version="1",
            components=[ComponentHealth(name="a", status=HealthStatus.DOWN), ComponentHealth(name="b", status=HealthStatus.DEGRADED)],
        )
        assert down.overall == HealthStatus.DOWN.value

    def test_system_status_to_dict(self):
        status = SystemStatus(
            environment="prod",
            version="1.2.3",
            maintenance=MaintenanceStatus.ACTIVE,
            maintenance_reason="upgrade",
            active_alerts=2,
            feature_flags_enabled=1,
        )
        data = status.to_dict()
        assert data["environment"] == "prod"
        assert data["version"] == "1.2.3"
        assert data["maintenance"] == "active"
        assert data["maintenance_reason"] == "upgrade"
        assert data["active_alerts"] == 2
        assert data["feature_flags_enabled"] == 1
        assert "timestamp" in data

    def test_alert_record_to_dict(self):
        alert = AlertRecord(id="a1", name="cpu", severity=AlertSeverity.CRITICAL, status=AlertStatus.FIRING)
        data = alert.to_dict()
        assert data["severity"] == "critical"
        assert data["status"] == "firing"
        assert data["acknowledged_by"] == ""

    def test_analytics_point_to_dict(self):
        point = AnalyticsPoint(label="day-1", value=5.0, dimension="tokens")
        assert point.to_dict() == {"label": "day-1", "value": 5.0, "dimension": "tokens"}

    def test_dashboard_report_to_dict(self):
        report = DashboardReport(overview={"x": 1}, system={"y": 2}, analytics={"z": 3})
        data = report.to_dict()
        assert data["overview"] == {"x": 1}
        assert data["system"] == {"y": 2}
        assert data["analytics"] == {"z": 3}
        assert "generated_at" in data

    def test_diagnostics_report_to_dict(self):
        report = DiagnosticsReport(environment={"e": 1}, runtime={"r": 2}, integrations={"i": 3}, checks=[{"c": 4}])
        data = report.to_dict()
        assert data["environment"] == {"e": 1}
        assert data["checks"] == [{"c": 4}]

    def test_audit_record_to_dict(self):
        record = AuditRecord(id="a", actor="me", action="go", resource="r", details={"k": 1})
        data = record.to_dict()
        assert data["actor"] == "me"
        assert data["action"] == "go"
        assert data["resource"] == "r"
        assert data["details"] == {"k": 1}
        assert "created_at" in data

    def test_component_names(self):
        assert ComponentName.GATEWAY.value == "gateway"
        assert ComponentName.RATE_LIMITER.value == "rate_limiter"
        assert AdminEventType.ALERT_FIRED.value == "alert.fired"
        assert AdminEventType.MODULE_ACCESSED.value == "module.accessed"


# --------------------------------------------------------------- repositories


class TestRepositories:
    def test_flag_repository(self):
        repo = InMemoryFlagRepository()
        flag = FeatureFlag(name="a")
        assert repo.create(flag) is flag
        assert repo.get("a") is flag
        assert repo.list() == [flag]
        flag.enabled = True
        assert repo.update(flag) is flag
        assert repo.delete("a") is True
        assert repo.delete("a") is False
        with pytest.raises(FeatureFlagNotFoundError):
            repo.get("a")
        with pytest.raises(FeatureFlagNotFoundError):
            repo.update(flag)

    def test_settings_repository(self):
        repo = InMemorySettingsRepository()
        assert repo.get("missing") is None
        assert repo.set("k", 1) == 1
        assert repo.get("k") == 1
        assert repo.all() == {"k": 1}

    def test_alert_repository(self):
        repo = InMemoryAlertRepository()
        alert = AlertRecord(id="a1", name="x", status=AlertStatus.FIRING)
        repo.create(alert)
        resolved = AlertRecord(id="a2", name="y", status=AlertStatus.RESOLVED)
        repo.create(resolved)
        assert repo.get("a1") is alert
        assert repo.list() == [alert, resolved]
        assert [a.id for a in repo.list(status="firing")] == ["a1"]
        assert [a.id for a in repo.list(status="resolved")] == ["a2"]
        alert.status = AlertStatus.RESOLVED
        assert repo.update(alert) is alert
        with pytest.raises(AlertNotFoundError):
            repo.get("nope")
        with pytest.raises(AlertNotFoundError):
            repo.update(AlertRecord(id="nope", name="z"))

    def test_audit_repository(self):
        repo = InMemoryAuditRepository()
        first = AuditRecord(id="1", actor="a", action="create")
        second = AuditRecord(id="2", actor="b", action="delete")
        third = AuditRecord(id="3", actor="a", action="delete")
        repo.record(first)
        repo.record(second)
        repo.record(third)
        assert repo.query() == [third, second, first]
        assert [r.id for r in repo.query(actor="a")] == ["3", "1"]
        assert [r.id for r in repo.query(action="delete")] == ["3", "2"]
        assert [r.id for r in repo.query(limit=2)] == ["3", "2"]

    def test_admin_repositories(self):
        repos = AdminRepositories()
        assert repos.as_dict() == {"flags": repos.flags, "settings": repos.settings, "alerts": repos.alerts, "audit": repos.audit}

    def test_default_settings(self):
        assert "platform_name" in DEFAULT_SETTINGS
        assert DEFAULT_SETTINGS["max_upload_mb"].default == 100
        assert DEFAULT_SETTINGS["secret_overrides"].sensitive is True


# ------------------------------------------------------------- feature flags


class TestFeatureFlags:
    def test_register_and_toggle(self):
        manager = FeatureFlagManager()
        flag = manager.register("beta", enabled=False)
        assert flag.name == "beta"
        assert manager.get("beta").enabled is False
        assert manager.enable("beta").enabled is True
        assert manager.get("beta").enabled is True
        assert manager.enable("beta").enabled is True
        assert manager.disable("beta").enabled is False
        assert manager.disable("beta").enabled is False
        assert manager.set("beta", True).enabled is True
        assert manager.set("beta", False).enabled is False

    def test_set_invalid(self):
        manager = FeatureFlagManager()
        manager.register("beta")
        with pytest.raises(FeatureFlagInvalidError):
            manager.set("beta", "yes")

    def test_is_enabled_default(self):
        manager = FeatureFlagManager(AdminConfig(feature_defaults={"legacy": True}))
        assert manager.is_enabled("legacy") is True
        assert manager.is_enabled("unknown") is False

    def test_is_enabled_environment(self):
        manager = FeatureFlagManager()
        manager.register("staging_only", enabled=True, environment="staging")
        assert manager.is_enabled("staging_only") is True
        assert manager.is_enabled("staging_only", environment="production") is False
        manager.register("all_envs", enabled=True)
        assert manager.is_enabled("all_envs", environment="production") is True

    def test_delete_and_list(self):
        manager = FeatureFlagManager()
        manager.register("a")
        manager.register("b")
        assert len(manager.list()) == 2
        assert manager.enabled_count() == 0
        manager.enable("a")
        assert manager.enabled_count() == 1
        assert manager.delete("a") is True
        assert len(manager.list()) == 1
        with pytest.raises(FeatureFlagNotFoundError):
            manager.get("a")

    def test_subscribe_unsubscribe(self):
        manager = FeatureFlagManager()
        manager.register("beta")
        seen: list[FeatureFlag] = []

        def listener(flag: FeatureFlag) -> None:
            seen.append(flag)

        assert manager.subscribe("beta", listener) is None
        manager.enable("beta")
        assert len(seen) == 1
        assert seen[0].enabled is True
        assert manager.unsubscribe("beta", listener) is True
        assert manager.unsubscribe("beta", listener) is False
        manager.disable("beta")
        assert len(seen) == 1

    def test_subscribe_unknown_flag_still_fires(self):
        manager = FeatureFlagManager()
        seen: list[FeatureFlag] = []

        def listener(flag: FeatureFlag) -> None:
            seen.append(flag)

        manager.subscribe("future", listener)
        manager.register("future")
        assert seen == []
        flag = manager.enable("future")
        assert seen == [flag]


# ------------------------------------------------------------------ settings


class TestSettings:
    def test_get_and_set(self):
        settings = SystemSettingsManager()
        assert settings.get("platform_name") == "AI Router"
        assert settings.get("max_upload_mb") == 100
        assert settings.set("max_upload_mb", 250) == 250
        assert settings.get("max_upload_mb") == 250

    def test_unknown_key(self):
        settings = SystemSettingsManager()
        with pytest.raises(SettingNotFoundError):
            settings.get("nope")
        with pytest.raises(SettingNotFoundError):
            settings.set("nope", 1)
        with pytest.raises(SettingNotFoundError):
            settings.reset("nope")

    def test_validation(self):
        settings = SystemSettingsManager()
        with pytest.raises(SettingValidationError):
            settings.set("max_upload_mb", "big")
        with pytest.raises(SettingValidationError):
            settings.set("allow_public_signup", "yes")

    def test_reset(self):
        settings = SystemSettingsManager()
        settings.set("max_upload_mb", 300)
        assert settings.reset("max_upload_mb") == 100
        assert settings.get("max_upload_mb") == 100

    def test_sensitive_masking(self):
        settings = SystemSettingsManager()
        settings.set("secret_overrides", "hunter2")
        assert settings.all()["secret_overrides"] == "***"
        assert settings.all(include_sensitive=True)["secret_overrides"] == "hunter2"
        assert settings.get("secret_overrides") == "hunter2"

    def test_all_and_snapshot(self):
        settings = SystemSettingsManager()
        all_values = settings.all()
        assert all_values["platform_name"] == "AI Router"
        assert "maintenance_notice" in all_values
        snapshot = settings.snapshot()
        assert len(snapshot) == len(DEFAULT_SETTINGS)
        assert snapshot[0]["key"] == "platform_name"
        assert snapshot[0]["type"] == "string"

    def test_register_definition(self):
        settings = SystemSettingsManager()
        settings.register_definition(SettingDefinition("custom", SettingType.STRING, default="d"))
        assert settings.get("custom") == "d"
        assert "custom" in settings.definitions


# ---------------------------------------------------------------- maintenance


class TestMaintenance:
    def test_start_end(self):
        maintenance = MaintenanceManager()
        assert maintenance.in_maintenance() is False
        maintenance.start("upgrade")
        assert maintenance.in_maintenance() is True
        status = maintenance.status()
        assert status["status"] == "active"
        assert status["reason"] == "upgrade"
        maintenance.end()
        assert maintenance.in_maintenance() is False
        assert maintenance.status()["status"] == "none"

    def test_require_available(self):
        maintenance = MaintenanceManager()
        maintenance.require_available()
        maintenance.start("nope")
        with pytest.raises(MaintenanceActiveError):
            maintenance.require_available()

    def test_schedule_validation(self):
        maintenance = MaintenanceManager()
        with pytest.raises(MaintenanceActiveError):
            maintenance.schedule(10, 5)

    def test_scheduled_window_activates(self):
        maintenance = MaintenanceManager()
        maintenance.schedule(time.time() - 60, time.time() + 3600, "nightly")
        assert maintenance.in_maintenance() is True
        assert maintenance.status()["reason"] == "nightly"

    def test_scheduled_window_future(self):
        maintenance = MaintenanceManager()
        maintenance.schedule(time.time() + 3600, time.time() + 7200, "later")
        assert maintenance.in_maintenance() is False
        status = maintenance.status()
        assert status["scheduled_start"] is not None
        assert status["scheduled_end"] is not None
        assert status["scheduled_reason"] == "later"

    def test_scheduled_window_expiry(self):
        maintenance = MaintenanceManager()
        maintenance.start("manual")
        maintenance.schedule(time.time() - 7200, time.time() - 3600)
        assert maintenance.in_maintenance() is False
        assert maintenance.status()["status"] == "none"

    def test_status_fields(self):
        maintenance = MaintenanceManager()
        status = maintenance.status()
        assert status["status"] == "none"
        assert status["reason"] == ""
        assert status["scheduled_start"] is None


# --------------------------------------------------------------------- health


class TestHealth:
    def test_default_registry_has_all_components(self):
        registry = create_default_registry()
        names = registry.names()
        assert len(names) == 12
        for component in ComponentName:
            assert component.value in names

    def test_probes_drive_status(self):
        registry = create_default_registry(probes={"gateway": lambda: True, "billing": lambda: False})
        results = {result.name: result.status for result in registry.run()}
        assert results["gateway"] == HealthStatus.OK
        assert results["billing"] == HealthStatus.DOWN

    def test_probe_raising(self):
        def boom() -> bool:
            raise RuntimeError("down")

        registry = create_default_registry(probes={"auth": boom})
        result = registry.run_component("auth")
        assert result.status == HealthStatus.DOWN
        assert result.message == "down"
        assert registry.get("auth").check().message == "down"

    def test_component_filter(self):
        registry = create_default_registry()
        results = registry.run(component="gateway")
        assert len(results) == 1
        assert results[0].name == "gateway"

    def test_run_component_unknown(self):
        registry = create_default_registry()
        with pytest.raises(ComponentUnavailableError):
            registry.run_component("nope")

    def test_run_component_worst_status(self):
        registry = HealthCheckRegistry()
        registry.register(CallableHealthCheck(probe=lambda: True, name="a"))
        registry.register(CallableHealthCheck(probe=lambda: False, name="b"))
        result = registry.run_component("custom")
        assert result.status == HealthStatus.DOWN

    def test_register_unregister_get(self):
        registry = HealthCheckRegistry()
        check = CallableHealthCheck(probe=lambda: True, name="c")
        assert registry.unregister("c") is False
        registry.register(check)
        assert registry.get("c") is check
        assert registry.names() == ["c"]
        assert registry.unregister("c") is True
        with pytest.raises(HealthCheckFailedError):
            registry.get("c")

    def test_callable_check_default_probe(self):
        check = CallableHealthCheck()
        assert check.check().status == HealthStatus.OK
        gateway = GatewayHealthCheck()
        assert gateway.check().status == HealthStatus.OK

    def test_timeout_property(self):
        assert create_default_registry(timeout_seconds=2.0).timeout_seconds == 2.0

    def test_health_check_abstract(self):
        with pytest.raises(TypeError):
            HealthCheck()  # type: ignore[abstract]


# ---------------------------------------------------------------------- audit


class TestAudit:
    def test_record_and_query(self):
        audit = AuditService()
        record = audit.record("alice", "update", resource="flag:beta", details={"enabled": True})
        assert record.id.startswith("aud_")
        assert audit.count() == 1
        assert audit.by_actor("alice")[0].id == record.id
        assert audit.by_action("update")[0].id == record.id
        assert audit.query(actor="nobody") == []

    def test_query_limit_bounds(self):
        audit = AuditService()
        with pytest.raises(AuditQueryError):
            audit.query(limit=0)
        with pytest.raises(AuditQueryError):
            audit.query(limit=1001)
        assert audit.query(limit=1) == []


# ------------------------------------------------------------------ monitoring


class TestPrometheus:
    def test_inc_and_counter_value(self):
        backend = PrometheusBackend()
        backend.inc("requests", labels={"route": "/v1/chat"})
        backend.inc("requests", labels={"route": "/v1/chat"}, amount=3)
        backend.inc("requests")
        assert backend.counter_value("requests", {"route": "/v1/chat"}) == 4.0
        assert backend.counter_value("requests") == 1.0
        assert backend.counter_value("missing") == 0.0

    def test_gauge_and_histogram(self):
        backend = PrometheusBackend()
        backend.set_gauge("pool", 5.0)
        backend.observe("latency", 0.1)
        backend.observe("latency", 0.3, labels={"op": "embed"})
        exposition = backend.exposition()
        assert "# TYPE airouter_pool gauge" in exposition
        assert "airouter_pool{} 5.0" in exposition
        assert "# TYPE airouter_latency_seconds histogram" in exposition
        assert "airouter_latency_seconds_sum{} 0.1" in exposition
        assert "airouter_latency_seconds_count{op=\"embed\"} 1" in exposition

    def test_label_key_ordering(self):
        backend = PrometheusBackend()
        backend.inc("requests", labels={"z": "1", "a": "2"})
        assert "requests{a=\"2\",z=\"1\"} 1.0" in backend.exposition()

    def test_namespace(self):
        backend = PrometheusBackend(AdminConfig(prometheus_namespace="router"))
        backend.inc("requests")
        assert "# TYPE router_requests counter" in backend.exposition()


class TestOpenTelemetry:
    def test_spans_and_export(self):
        backend = OpenTelemetryBackend()
        span = backend.start_span("generate", attributes={"model": "gpt"})
        assert backend.export() == []
        backend.end_span(span)
        exported = backend.export()
        assert len(exported) == 1
        assert exported[0]["name"] == "generate"
        assert exported[0]["status"] == "OK"
        assert exported[0]["attributes"] == {"model": "gpt"}
        assert backend.trace_count() == 1

    def test_parent_trace(self):
        backend = OpenTelemetryBackend()
        parent = backend.start_span("root")
        child = backend.start_span("child", parent_id=parent)
        backend.end_span(child)
        backend.end_span(parent)
        spans = backend.export()
        child_span = next(span for span in spans if span["span_id"] == child)
        parent_span = next(span for span in spans if span["span_id"] == parent)
        assert child_span["trace_id"] == parent_span["trace_id"]

    def test_end_span_unknown_is_noop(self):
        backend = OpenTelemetryBackend()
        backend.end_span("missing")
        assert backend.export() == []

    def test_unknown_parent_new_trace(self):
        backend = OpenTelemetryBackend()
        span = backend.start_span("child", parent_id="ghost")
        backend.end_span(span)
        assert backend.trace_count() == 1
        assert backend.export()[0]["parent_id"] == "ghost"


class TestLoki:
    def test_ship_and_query(self):
        backend = LokiBackend()
        backend.ship("hello", labels={"app": "router"}, level="info")
        backend.ship("warn me", labels={"app": "router"}, level="warn")
        backend.ship("other", labels={"app": "worker"}, level="error")
        assert len(backend.query()) == 3
        assert len(backend.query(level="info")) == 1
        assert len(backend.query(limit=2)) == 2

    def test_push_payload(self):
        backend = LokiBackend()
        backend.ship("hello", labels={"app": "router"}, level="info")
        payload = backend.push_payload()
        assert len(payload["streams"]) == 1
        assert payload["streams"][0]["stream"] == {"app": "router"}
        assert payload["streams"][0]["values"][0][1] == "hello"


class TestAlertmanager:
    def test_fire_acknowledge_resolve(self):
        backend = AlertmanagerBackend()
        alert = backend.fire("cpu_high", severity="critical", message="cpu at 99%", labels={"host": "h1"})
        assert alert.status == AlertStatus.FIRING
        assert backend.active_count() == 1
        memory_alert = backend.fire("mem", severity=AlertSeverity.WARNING)
        assert memory_alert.status == AlertStatus.FIRING
        assert backend.active_count() == 2
        acknowledged = backend.acknowledge(alert.id, actor="ops")
        assert acknowledged.status == AlertStatus.ACKNOWLEDGED
        assert acknowledged.acknowledged_by == "ops"
        assert backend.active_count() == 1
        resolved = backend.resolve(alert.id)
        assert resolved.status == AlertStatus.RESOLVED
        assert backend.active_count() == 1
        assert len(backend.list(status="resolved")) == 1
        backend.resolve(memory_alert.id)
        assert backend.active_count() == 0

    def test_unknown_alert(self):
        backend = AlertmanagerBackend()
        with pytest.raises(AlertNotFoundError):
            backend.acknowledge("nope")
        with pytest.raises(AlertNotFoundError):
            backend.resolve("nope")

    def test_payloads(self):
        backend = AlertmanagerBackend()
        backend.fire("cpu")
        payloads = backend.payloads()
        assert payloads[0]["name"] == "cpu"
        assert payloads[0]["status"] == "firing"


class TestMonitoringService:
    def test_record_metric_kinds(self):
        service = MonitoringService()
        service.record_metric("requests", 5.0)
        service.record_metric("pool", 3.0, kind="gauge")
        service.record_metric("latency", 0.2, kind="histogram")
        prometheus = service.backend("prometheus")
        assert prometheus.counter_value("requests") == 5.0
        assert "airouter_pool" in prometheus.exposition()
        assert "airouter_latency_seconds" in prometheus.exposition()

    def test_record_span_and_ship_log(self):
        service = MonitoringService()
        service.record_span("generate", 12.5, attributes={"m": "x"})
        service.ship_log("hi", labels={"a": "b"}, level="warn")
        assert len(service.backend("otel").export()) == 1
        assert len(service.backend("loki").query(level="warn")) == 1

    def test_alert_lifecycle_via_service(self):
        service = MonitoringService()
        alert = service.fire_alert("cpu", severity="critical", message="high")
        assert service.alerts() == [alert]
        assert service.alerts(status="firing") == [alert]
        service.acknowledge_alert(alert.id, actor="me")
        service.resolve_alert(alert.id)
        assert service.alerts(status="firing") == []
        assert service.alerts(status="resolved") == [alert]

    def test_backend_missing(self):
        service = MonitoringService(AdminConfig(alertmanager_enabled=False))
        with pytest.raises(MonitorError):
            service.backend("alertmanager")
        with pytest.raises(MonitorError):
            service.fire_alert("x")
        with pytest.raises(MonitorError):
            service.acknowledge_alert("a1")
        with pytest.raises(MonitorError):
            service.resolve_alert("a1")
        assert service.alerts() == []
        assert "alertmanager" not in service.backends

    def test_missing_otel_span_noop(self):
        service = MonitoringService(AdminConfig(otel_enabled=False))
        service.record_span("x", 1.0)
        assert "otel" not in service.backends

    def test_disabled_prometheus_metrics_are_noops(self):
        service = MonitoringService(AdminConfig(prometheus_enabled=False))
        service.record_metric("requests", 1.0)
        service.record_span("x", 1.0)
        assert service.status()["enabled_backends"] == ["otel", "loki", "alertmanager"]

    def test_status(self):
        service = MonitoringService()
        status = service.status()
        assert status["prometheus"] is True
        assert "prometheus" in status["enabled_backends"]
        assert "otel" in status["enabled_backends"]
        assert "loki" in status["enabled_backends"]
        assert "alertmanager" in status["enabled_backends"]

    def test_prometheus_backend_is_prometheus(self):
        service = MonitoringService()
        assert isinstance(service.backend("prometheus"), PrometheusBackend)
        assert isinstance(service.backend("otel"), OpenTelemetryBackend)
        assert isinstance(service.backend("loki"), LokiBackend)
        assert isinstance(service.backend("alertmanager"), AlertmanagerBackend)


# ------------------------------------------------------------------ analytics


class TestAnalytics:
    def test_record_series_trend(self):
        analytics = AnalyticsService()
        now = time.time()
        analytics.record("tokens", 10, ts=now - 2 * 86400 + 3600)
        analytics.record("tokens", 20, ts=now - 86400 + 3600)
        analytics.record("tokens", 30, ts=now - 3 * 86400 + 3600)
        trend = analytics.trend("tokens", days=3)
        assert [point.value for point in trend] == [30.0, 10.0, 20.0]
        assert analytics.trend("missing")[0].value == 0.0

    def test_trend_days_invalid(self):
        analytics = AnalyticsService()
        with pytest.raises(AnalyticsUnavailableError):
            analytics.trend("tokens", days=0)

    def test_top(self):
        analytics = AnalyticsService()
        analytics.record("requests", 5, labels={"route": "/a"})
        analytics.record("requests", 9, labels={"route": "/b"})
        analytics.record("requests", 2, labels={"route": "/a"})
        top = analytics.top("requests", dimension="route")
        assert [point.label for point in top] == ["/b", "/a"]
        assert top[0].value == 9.0

    def test_series_since(self):
        analytics = AnalyticsService()
        analytics.record("m", 1, ts=100)
        analytics.record("m", 2, ts=200)
        assert [sample["value"] for sample in analytics.series("m", since=150)] == [2.0]

    def test_revenue_report(self):
        analytics = AnalyticsService()
        snapshots = [
            {"status": "active", "monthly_revenue": 100.0, "plan_id": "starter"},
            {"status": "trialing", "monthly_revenue": 0.0, "plan_id": "pro"},
            {"status": "cancelled", "monthly_revenue": 50.0, "plan_id": "pro"},
        ]
        report = analytics.revenue_report(snapshots)
        assert report["mrr"] == 100.0
        assert report["arr"] == 1200.0
        assert report["active_subscriptions"] == 2
        assert report["by_plan"] == {"starter": 100.0, "pro": 0.0}

    def test_revenue_report_source(self):
        analytics = AnalyticsService()
        analytics.register_source("revenue_snapshots", lambda: [{"status": "active", "monthly_revenue": 50.0, "plan_id": "x"}])
        assert analytics.revenue_report()["mrr"] == 50.0

    def test_source_missing(self):
        analytics = AnalyticsService()
        with pytest.raises(AnalyticsUnavailableError):
            analytics.source("revenue_snapshots")

    def test_usage_summary(self):
        analytics = AnalyticsService()
        analytics.record("tokens", 100)
        analytics.record("api_requests", 5)
        summary = analytics.usage_summary()
        assert summary["by_category"]["tokens"] == 100.0
        assert summary["by_category"]["api_requests"] == 5.0
        assert summary["total"] == 105.0

    def test_summary(self):
        analytics = AnalyticsService()
        analytics.record("tokens", 100)
        summary = analytics.summary()
        assert "usage" in summary
        assert "tokens" in summary["trends"]


# ---------------------------------------------------------------- statistics


class TestStatistics:
    def test_totals(self):
        stats = StatisticsService()
        stats.record_request("GET", "/health", 200, 5.0, ts=50)
        stats.record_request("POST", "/chat", 500, 20.0, ts=60)
        stats.record_request("GET", "/health", 200, 7.0, ts=100)
        totals = stats.totals()
        assert totals["total_requests"] == 3
        assert totals["error_requests"] == 1
        assert totals["error_rate"] == pytest.approx(0.3333)
        assert totals["avg_latency_ms"] == pytest.approx(10.67)
        assert stats.totals(since=1000)["total_requests"] == 0

    def test_percentiles(self):
        stats = StatisticsService()
        assert stats.percentiles() == {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0}
        for latency in (10.0, 20.0, 30.0, 40.0, 100.0):
            stats.record_request("GET", "/x", 200, latency)
        percentiles = stats.percentiles()
        assert percentiles["p50"] == 30.0
        assert percentiles["p90"] == 76.0
        assert percentiles["p99"] == 97.6

    def test_status_codes(self):
        stats = StatisticsService()
        for status in (200, 201, 404, 500, 503):
            stats.record_request("GET", "/x", status, 1.0)
        assert stats.status_codes() == {"2xx": 2, "4xx": 1, "5xx": 2}

    def test_top_endpoints(self):
        stats = StatisticsService()
        stats.record_request("GET", "/a", 200, 2.0)
        stats.record_request("GET", "/a", 200, 4.0)
        stats.record_request("POST", "/b", 200, 6.0)
        top = stats.top_endpoints()
        assert top[0]["endpoint"] == "GET /a"
        assert top[0]["count"] == 2
        assert top[0]["avg_latency_ms"] == 3.0
        assert len(stats.top_endpoints(limit=1)) == 1

    def test_throughput(self):
        stats = StatisticsService()
        now = time.time()
        stats.record_request("GET", "/x", 200, 1.0, ts=now)
        stats.record_request("GET", "/x", 200, 1.0, ts=now - 120)
        points = stats.throughput(window_minutes=10)
        assert points[0]["requests"] == 1
        assert points[2]["requests"] == 1
        assert len(points) == 10

    def test_report(self):
        stats = StatisticsService()
        stats.record_request("GET", "/x", 200, 1.0)
        report = stats.report()
        assert report["totals"]["total_requests"] == 1
        assert report["percentiles"]["p50"] == 1.0
        assert report["status_codes"] == {"2xx": 1}
        assert report["top_endpoints"] == [{"endpoint": "GET /x", "count": 1, "avg_latency_ms": 1.0}]


# ---------------------------------------------------------------- diagnostics


class TestDiagnostics:
    def test_collect(self):
        diagnostics = DiagnosticsService()
        report = diagnostics.collect()
        assert report.environment["environment"] == "production"
        assert report.runtime["maxsize"] == 2**63 - 1 if hasattr(2**63 - 1, "real") else report.runtime["maxsize"] > 0
        assert report.integrations["prometheus"]["enabled"] is True
        assert len(report.checks) == 5
        assert all(check["passed"] for check in report.checks)

    def test_summary(self):
        diagnostics = DiagnosticsService()
        summary = diagnostics.summary()
        assert summary["checks_total"] == 5
        assert summary["checks_passed"] == 5
        assert summary["checks_failed"] == 0

    def test_check_failure_counted(self):
        diagnostics = DiagnosticsService(checks={"flaky": lambda: False, "boom": lambda: (_ for _ in ()).throw(ValueError("x"))})
        assert diagnostics.summary()["checks_failed"] == 2

    def test_register_check(self):
        diagnostics = DiagnosticsService()
        diagnostics.register_check("custom_ok", lambda: True)
        assert diagnostics.collect().checks[-1]["name"] == "custom_ok"

    def test_environment_and_runtime(self):
        diagnostics = DiagnosticsService(AdminConfig(environment="staging", version="9.9.9"))
        env = diagnostics.environment()
        assert env["environment"] == "staging"
        assert env["version"] == "9.9.9"
        assert "python" in env
        assert "platform" in env
        assert "implementation" in env
        runtime = diagnostics.runtime()
        assert "sys_argv" in runtime
        assert "threads" in runtime


# --------------------------------------------------------------- operations


class TestOperations:
    def test_feature_operations(self):
        operations = OperationsService()
        assert operations.register_feature("beta", enabled=False, owner="me")["name"] == "beta"
        assert operations.toggle_feature("beta", True)["enabled"] is True
        assert operations.toggle_feature("beta", False, actor="ops")["enabled"] is False
        assert operations.delete_feature("beta") is True
        with pytest.raises(FeatureFlagNotFoundError):
            operations.toggle_feature("beta", True)
        with pytest.raises(FeatureFlagNotFoundError):
            operations.delete_feature("beta")

    def test_setting_operations(self):
        operations = OperationsService()
        assert operations.update_setting("max_upload_mb", 150, actor="me") == {"key": "max_upload_mb", "value": 150}
        assert operations.reset_setting("max_upload_mb") == {"key": "max_upload_mb", "value": 100}
        with pytest.raises(SettingValidationError):
            operations.update_setting("max_upload_mb", "big")

    def test_maintenance_operations(self):
        operations = OperationsService()
        assert operations.start_maintenance("upgrade", actor="me")["status"] == "active"
        with pytest.raises(MaintenanceActiveError):
            operations.require_available()
        assert operations.end_maintenance()["status"] == "none"
        operations.require_available()
        assert operations.schedule_maintenance(time.time() - 10, time.time() + 600, reason="window")["scheduled_start"] is not None
        with pytest.raises(MaintenanceActiveError):
            operations.schedule_maintenance(10, 5)

    def test_alert_operations(self):
        operations = OperationsService()
        alert = operations.fire_alert("cpu", severity="critical", message="high", labels={"h": "1"}, actor="me")
        assert alert["status"] == "firing"
        assert operations.acknowledge_alert(alert["id"], actor="ops")["status"] == "acknowledged"
        assert operations.resolve_alert(alert["id"])["status"] == "resolved"

    def test_properties(self):
        operations = OperationsService()
        assert operations.flags is not None
        assert operations.settings is not None
        assert operations.maintenance is not None
        assert operations.monitoring is not None


# ------------------------------------------------------------------ metrics


class TestAdminMetrics:
    def test_record_and_report(self):
        tracker = AdminMetricsTracker()
        tracker.record_request("admin.overview")
        tracker.record_request("admin.health", latency_ms=5.0)
        tracker.record_request("admin.health", latency_ms=10.0, error=True)
        report = tracker.report()
        assert report["total_requests"] == 3
        assert report["error_requests"] == 1
        assert report["error_rate"] == pytest.approx(0.3333)
        assert report["by_endpoint"] == {"admin.health": 2, "admin.overview": 1}

    def test_disabled_tracking(self):
        tracker = AdminMetricsTracker(AdminConfig(track_metrics=False))
        tracker.record_request("admin.overview")
        assert tracker.report() == {
            "total_requests": 0,
            "error_requests": 0,
            "error_rate": 0.0,
            "by_endpoint": {},
        }


# ---------------------------------------------------------------- AdminAPI


class TestAdminAPI:
    def test_default_construction(self):
        api = AdminAPI()
        assert len(api.modules) == 9
        for name in ("tenants", "organizations", "users", "billing", "models", "knowledge", "memory", "mcp", "plugins"):
            assert api.module(name).name == name
        with pytest.raises(ModuleNotFoundError):
            api.module("nope")

    def test_core_views(self):
        api = AdminAPI()
        overview = api.overview()
        assert set(overview.keys()) == {"tenants", "organizations", "users", "billing", "models", "knowledge", "memory", "mcp", "plugins"}
        health = api.health()
        assert len(health) == 12
        assert health[0]["status"] in ("ok", "down", "degraded")
        stats = api.statistics()
        assert stats["requests"]["totals"]["total_requests"] == 0
        assert "usage" in stats["analytics"]
        status = api.system_status()
        assert status.environment == "production"
        assert status.overall in ("ok", "down", "degraded")
        assert status.maintenance == MaintenanceStatus.NONE
        assert status.active_alerts == 0
        dashboard = api.dashboard()
        assert dashboard.overview["tenants"]["total"] == 0
        assert dashboard.system["maintenance"] == "none"
        assert dashboard.analytics["requests"]["totals"]["total_requests"] == 0

    def test_views_record_metrics(self):
        api = AdminAPI()
        api.overview()
        api.health()
        api.statistics()
        api.system_status()
        api.dashboard()
        assert api.metrics_report()["total_requests"] == 8

    def test_health_component(self):
        api = AdminAPI()
        result = api.health_component("gateway")
        assert result["name"] == "gateway"
        assert result["status"] == "ok"
        with pytest.raises(ComponentUnavailableError):
            api.health("nope")

    def test_feature_operations_via_api(self):
        api = AdminAPI()
        api.register_feature("beta", enabled=False, owner="me")
        assert api.toggle_feature("beta", True)["enabled"] is True
        assert api.feature_flags()[0]["name"] == "beta"
        assert api.delete_feature("beta") is True
        assert api.feature_flags() == []

    def test_settings_via_api(self):
        api = AdminAPI()
        assert api.update_setting("max_upload_mb", 200)["value"] == 200
        assert api.reset_setting("max_upload_mb")["value"] == 100
        assert api.setting("platform_name")["value"] == "AI Router"
        assert api.settings()["allow_public_signup"] is False
        assert api.settings()["secret_overrides"] == "***"

    def test_maintenance_via_api(self):
        api = AdminAPI()
        assert api.start_maintenance("upgrade")["status"] == "active"
        with pytest.raises(MaintenanceActiveError):
            api.operations.require_available()
        assert api.maintenance_status()["status"] == "active"
        assert api.end_maintenance()["status"] == "none"
        assert api.schedule_maintenance(time.time() + 60, time.time() + 3600)["scheduled_start"] is not None

    def test_alerts_via_api(self):
        api = AdminAPI()
        alert = api.fire_alert("cpu", severity="critical", message="high", labels={"host": "h1"})
        assert api.alerts(status="firing")[0]["id"] == alert["id"]
        assert api.acknowledge_alert(alert["id"], actor="ops")["status"] == "acknowledged"
        assert api.resolve_alert(alert["id"])["status"] == "resolved"
        assert api.alerts(status="firing") == []
        assert api.alerts(status="resolved")[0]["id"] == alert["id"]

    def test_observability_passthroughs(self):
        api = AdminAPI()
        assert "# TYPE airouter_requests counter" not in api.prometheus_metrics()
        api.monitoring.record_metric("requests", 3.0)
        assert "airouter_requests{} 3.0" in api.prometheus_metrics()
        api.monitoring.record_span("generate", 5.0)
        assert len(api.otel_traces()) == 1
        api.monitoring.ship_log("hello", level="warn")
        assert len(api.loki_logs(level="warn")) == 1
        assert len(api.loki_logs(limit=5)) == 1

    def test_audit_via_api(self):
        api = AdminAPI()
        record = api.record_audit("alice", "delete", resource="tenant:t1", details={"id": "t1"})
        assert record["actor"] == "alice"
        assert record["action"] == "delete"
        assert api.audit_log(actor="alice")[0]["id"] == record["id"]
        assert api.audit_log(actor="bob") == []

    def test_diagnostics_via_api(self):
        api = AdminAPI()
        report = api.diagnostics()
        assert len(report["checks"]) == 5
        runtime = api.runtime_stats()
        assert set(runtime.keys()) == {"environment", "runtime", "integrations"}
        assert api.monitor_status()["enabled_backends"] == ["prometheus", "otel", "loki", "alertmanager"]

    def test_seeded_modules(self):
        api = AdminAPI()
        tenants = api.module("tenants")
        tenants.seed("t1", name="Acme", plan="pro", status="active")
        tenants.seed("t2", status="suspended")
        assert tenants.list() == [
            {"id": "t1", "name": "Acme", "plan": "pro", "status": "active"},
            {"id": "t2", "name": "t2", "plan": "free", "status": "suspended"},
        ]
        assert tenants.get("t1")["name"] == "Acme"
        with pytest.raises(ComponentUnavailableError):
            tenants.get("nope")
        stats = tenants.stats()
        assert stats == {"total": 2, "active": 1, "by_plan": {"pro": 1, "free": 1}}
        assert tenants.summary()["total"] == 2

    def test_seeded_organizations(self):
        api = AdminAPI()
        orgs = api.module("organizations")
        orgs.seed("o1", name="Acme")
        orgs.seed("o2", status="suspended")
        assert orgs.stats() == {"total": 2, "active": 1}
        assert orgs.get("o1")["status"] == "active"
        with pytest.raises(ComponentUnavailableError):
            orgs.get("nope")

    def test_seeded_users(self):
        api = AdminAPI()
        users = api.module("users")
        users.seed("u1", username="alice", role="admin")
        users.seed("u2", status="disabled")
        stats = users.stats()
        assert stats["total"] == 2
        assert stats["active"] == 1
        assert stats["by_role"] == {"admin": 1, "user": 1}
        with pytest.raises(ComponentUnavailableError):
            users.get("nope")

    def test_seeded_billing(self):
        api = AdminAPI()
        billing = api.module("billing")
        billing.seed_subscription("s1", plan_id="pro", status="active", price=99.0)
        billing.seed_subscription("s2", plan_id="pro", status="cancelled", price=99.0)
        billing.seed_subscription("s3", plan_id="free")
        stats = billing.stats()
        assert stats["total_subscriptions"] == 3
        assert stats["active"] == 2
        assert stats["by_plan"] == {"pro": 2, "free": 1}
        revenue = billing.revenue()
        assert revenue["mrr"] == 99.0
        assert revenue["arr"] == 1188.0
        assert billing.invoices() == []
        assert billing.payments() == []
        assert billing.summary()["name"] == "billing"

    def test_seeded_models(self):
        api = AdminAPI()
        models = api.module("models")
        models.seed("gpt-4", provider="openai")
        models.seed("claude-3", provider="anthropic", status="disabled")
        stats = models.stats()
        assert stats == {"total": 2, "by_provider": {"openai": 1, "anthropic": 1}}
        assert models.get("gpt-4")["provider"] == "openai"
        with pytest.raises(ComponentUnavailableError):
            models.get("nope")

    def test_seeded_knowledge(self):
        api = AdminAPI()
        knowledge = api.module("knowledge")
        knowledge.seed_document("d1", title="Guide", chunks=3)
        knowledge.seed_document("d2")
        stats = knowledge.stats()
        assert stats == {"total_documents": 2, "total_chunks": 4}
        assert knowledge.summary()["name"] == "knowledge"

    def test_seeded_memory(self):
        api = AdminAPI()
        memory = api.module("memory")
        memory.seed_session("s1", messages=5)
        memory.seed_session("s2")
        stats = memory.stats()
        assert stats == {"total_sessions": 2, "total_messages": 5}

    def test_seeded_mcp(self):
        api = AdminAPI()
        mcp = api.module("mcp")
        mcp.seed_server("srv1", name="files")
        mcp.seed_server("srv2", status="disconnected")
        stats = mcp.stats()
        assert stats == {"total_servers": 2, "connected": 1}

    def test_seeded_plugins(self):
        api = AdminAPI()
        plugins = api.module("plugins")
        plugins.seed_plugin("p1", name="plugin-a")
        plugins.seed_plugin("p2", enabled=False)
        stats = plugins.stats()
        assert stats == {"total_plugins": 2, "enabled": 1}

    def test_source_backed_modules(self):
        class TenantSource:
            def list(self):
                return [{"id": "t1", "name": "Acme", "plan": "pro", "status": "active"}]

            def get(self, tenant_id):
                return {"id": tenant_id, "name": "Acme", "plan": "pro", "status": "active"}

        class UserSource:
            def list(self):
                return [{"id": "u1", "username": "alice", "role": "admin", "status": "active"}]

            def get(self, user_id):
                return {"id": user_id, "username": "alice", "role": "admin", "status": "active"}

        class ModelSource:
            def list(self):
                return [{"id": "m1", "provider": "openai", "status": "active"}]

            def get(self, model_id):
                return {"id": model_id, "provider": "openai", "status": "active"}

        class OrgSource:
            def list(self):
                return [{"id": "o1", "name": "Acme", "status": "active"}]

            def get(self, org_id):
                return {"id": org_id, "name": "Acme", "status": "active"}

        class KnowledgeSource:
            def documents(self):
                return [{"id": "d1", "title": "Guide", "chunks": 3}]

        class MemorySource:
            def sessions(self):
                return [{"id": "s1", "messages": 5}]

        class MCPSource:
            def names(self):
                return ["files", "search"]

        class PluginSource:
            def get_enabled(self):
                return [type("P", (), {"name": "enabled"})()]

            def disabled(self):
                return ["disabled_plugin"]

        class BillingManager:
            def list_subscriptions(self):
                return [type("S", (), {"to_dict": lambda self: {"id": "s1", "plan_id": "pro", "status": "active", "price": 99.0}})()]

            def list_invoices(self, tenant_id=""):
                return [{"id": "inv1"}]

            def list_payments(self, tenant_id=""):
                return [{"id": "pay1"}]

            def metrics_summary(self):
                return {"mrr": 99.0, "arr": 1188.0, "active_subscriptions": 1}

        api = AdminAPI(
            tenants=TenantsModule(source=TenantSource()),
            organizations=OrganizationsModule(source=OrgSource()),
            users=UsersModule(source=UserSource()),
            models=ModelsModule(source=ModelSource()),
            knowledge=KnowledgeModule(source=KnowledgeSource()),
            memory=MemoryModule(source=MemorySource()),
            mcp=MCPModule(source=MCPSource()),
            plugins=PluginsModule(source=PluginSource()),
            billing=BillingModule(manager=BillingManager()),
        )
        assert api.overview()["tenants"]["total"] == 1
        assert api.module("tenants").get("t1")["name"] == "Acme"
        assert api.overview()["users"]["total"] == 1
        assert api.module("users").get("u1")["role"] == "admin"
        assert api.overview()["models"]["total"] == 1
        assert api.overview()["organizations"]["total"] == 1
        assert api.module("knowledge").stats() == {"total_documents": 1, "total_chunks": 3}
        assert api.module("memory").stats() == {"total_sessions": 1, "total_messages": 5}
        assert api.module("mcp").stats() == {"total_servers": 2, "connected": 2}
        assert api.module("plugins").stats() == {"total_plugins": 2, "enabled": 1}
        assert api.module("billing").stats()["active"] == 1
        assert api.module("billing").invoices() == [{"id": "inv1"}]
        assert api.module("billing").payments() == [{"id": "pay1"}]
        assert api.module("billing").revenue()["mrr"] == 99.0

    def test_object_backed_tenants(self):
        class Tenant:
            id = "t1"
            name = "Acme"
            plan = "pro"
            status = "active"

        api = AdminAPI(tenants=TenantsModule(source=type("Source", (), {"list": lambda self: [Tenant()], "get": lambda self, tid: Tenant()})()))
        assert api.overview()["tenants"]["total"] == 1
        assert api.module("tenants").get("t1")["id"] == "t1"

    def test_property_accessors(self):
        api = AdminAPI()
        assert api.config.environment == "production"
        assert api.flags is not None
        assert api.settings is not None
        assert api.maintenance is not None
        assert api.health is not None
        assert api.analytics is not None
        assert api.statistics is not None
        assert api.monitoring is not None
        assert api.diagnostics is not None
        assert api.audit is not None
        assert api.operations is not None
        assert api.metrics is not None

    def test_create_admin_api(self):
        api = create_admin_api()
        assert isinstance(api, AdminAPI)
        assert api.health(component="gateway")[0]["name"] == "gateway"
        assert api.dashboard().system["environment"] == "production"

    def test_modules_and_admin_module_base(self):
        base = AdminAPI().module("tenants")
        assert base.describe() == {"name": "tenants"}
        assert base.summary()["name"] == "tenants"

    def test_admin_module_base_summary(self):
        class Bare(AdminModule):
            name = "bare"

        module = Bare()
        assert module.describe() == {"name": "bare"}
        assert module.summary() == {"name": "bare"}

    def test_module_summaries(self):
        api = AdminAPI()
        api.module("tenants").seed("t1")
        api.module("organizations").seed("o1")
        api.module("users").seed("u1")
        api.module("models").seed("m1")
        api.module("knowledge").seed_document("d1")
        api.module("memory").seed_session("s1")
        api.module("mcp").seed_server("srv1")
        api.module("plugins").seed_plugin("p1")
        api.module("billing").seed_subscription("s1", plan_id="pro", status="active", price=99.0)
        assert api.module("tenants").summary() == {"name": "tenants", "total": 1}
        assert api.module("organizations").summary() == {"name": "organizations", "total": 1}
        assert api.module("users").summary() == {"name": "users", "total": 1}
        assert api.module("models").summary() == {"name": "models", "total": 1}
        assert api.module("knowledge").summary() == {"name": "knowledge", "total_documents": 1, "total_chunks": 1}
        assert api.module("memory").summary() == {"name": "memory", "total_sessions": 1, "total_messages": 0}
        assert api.module("mcp").summary() == {"name": "mcp", "total_servers": 1, "connected": 1}
        assert api.module("plugins").summary() == {"name": "plugins", "total_plugins": 1, "enabled": 1}
        assert api.module("billing").summary()["name"] == "billing"

    def test_users_get_and_summary(self):
        api = AdminAPI()
        users = api.module("users")
        users.seed("u1", username="alice", role="admin")
        assert users.get("u1")["username"] == "alice"
        assert users.summary()["total"] == 1

    def test_source_backed_non_dict_objects(self):
        class Org:
            id = "o1"
            name = "Acme"
            status = "active"

        class User:
            id = "u1"
            username = "alice"
            role = "admin"
            status = "active"

        class Model:
            id = "m1"
            provider = "openai"
            status = "active"

        class OrgSource:
            def list(self):
                return [Org()]

            def get(self, org_id):
                return Org()

        class UserSource:
            def list(self):
                return [User()]

            def get(self, user_id):
                return User()

        class ModelSource:
            def list(self):
                return [Model()]

            def get(self, model_id):
                return Model()

        api = AdminAPI(
            organizations=OrganizationsModule(source=OrgSource()),
            users=UsersModule(source=UserSource()),
            models=ModelsModule(source=ModelSource()),
        )
        assert api.module("organizations").get("o1")["name"] == "Acme"
        assert api.module("organizations").summary()["total"] == 1
        assert api.module("users").get("u1")["role"] == "admin"
        assert api.module("users").summary()["total"] == 1
        assert api.module("models").get("m1")["provider"] == "openai"
        assert api.module("models").summary()["total"] == 1

    def test_observability_passthroughs_with_missing_backends(self):
        config = AdminConfig(prometheus_enabled=False, otel_enabled=False, loki_enabled=False)
        api = AdminAPI(monitoring=MonitoringService(config))
        assert api.prometheus_metrics() == ""
        assert api.otel_traces() == []
        assert api.loki_logs() == []

    def test_repository_and_service_properties(self):
        repos = AdminRepositories()
        flags = FeatureFlagManager(repository=repos.flags)
        assert flags.repository is repos.flags
        settings = SystemSettingsManager(repository=repos.settings, definitions={"extra": SettingDefinition("extra", SettingType.STRING, default="x")})
        assert settings.repository is repos.settings
        assert "extra" in settings.definitions
        audit = AuditService(repository=repos.audit)
        assert audit.repository is repos.audit

    def test_health_check_async(self):
        check = CallableHealthCheck(probe=lambda: True, name="c")
        assert check.check_async().status == HealthStatus.OK

    def test_logging_except_branch(self):
        class Broken:
            def __str__(self):
                raise ValueError("nope")

        logger = AdminLogger()
        logger.log_event("thing", payload=Broken())
        assert logger.events[0]["event"] == "admin_thing"

    def test_statistics_percentile_direct(self):
        assert StatisticsService._percentile([], 0.5) == 0.0
        assert StatisticsService._percentile([1.0, 2.0], 0.0) == 1.0

    def test_analytics_integration_via_api(self):
        api = AdminAPI()
        api.analytics.register_source("revenue_snapshots", lambda: [{"status": "active", "monthly_revenue": 100.0, "plan_id": "pro"}])
        assert api.analytics.revenue_report()["mrr"] == 100.0
        assert api.statistics()["analytics"]["usage"]["total"] == 0.0
