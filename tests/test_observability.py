"""Tests for the observability subsystem (Stage 10.10)."""

import json
import time

import pytest

from app.observability import (
    AlertEngine,
    AlertIncident,
    AlertRule,
    AlertingError,
    BurnRateAlertBuilder,
    DashboardError,
    DashboardGenerator,
    ObservabilityConfig,
    SliCollector,
    SliSnapshot,
    SloDefinition,
    SloError,
    create_alert_engine,
    create_sli_collector,
)


class TestObservabilityConfig:
    def test_defaults(self):
        config = ObservabilityConfig()
        assert config.window_seconds == 30 * 86400
        assert config.default_slo == 99.9
        assert config.alerts_enabled is True
        assert config.metrics_enabled is True
        assert config.traces_enabled is True

    def test_kwargs(self):
        config = ObservabilityConfig(default_slo=99.0, alerts_enabled=False)
        assert config.default_slo == 99.0
        assert config.alerts_enabled is False

    def test_unknown_kwarg_raises(self):
        with pytest.raises(TypeError):
            ObservabilityConfig(bogus=1)

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("OBS_DEFAULT_SLO", "99.5")
        monkeypatch.setenv("OBS_ALERTS_ENABLED", "false")
        config = ObservabilityConfig.from_env()
        assert config.default_slo == 99.5
        assert config.alerts_enabled is False

    def test_as_dict(self):
        assert ObservabilityConfig().as_dict()["default_slo"] == 99.9


class TestSloDefinition:
    def test_valid(self):
        slo = SloDefinition("availability")
        assert slo.target == 99.9
        assert slo.error_budget_pct == 0.1

    def test_invalid_target(self):
        with pytest.raises(SloError):
            SloDefinition("x", target=0)
        with pytest.raises(SloError):
            SloDefinition("x", target=100.5)
        with pytest.raises(SloError):
            SloDefinition("x", target=-1)

    def test_invalid_window_and_name(self):
        with pytest.raises(SloError):
            SloDefinition("x", window_seconds=0)
        with pytest.raises(SloError):
            SloDefinition("")

    def test_to_dict(self):
        data = SloDefinition("x", target=99.0).to_dict()
        assert data["error_budget_pct"] == 1.0
        assert data["name"] == "x"


class TestSliSnapshot:
    def test_empty(self):
        snapshot = SliSnapshot(SloDefinition("x"))
        assert snapshot.success_ratio == 100.0
        assert snapshot.error_rate == 0.0
        assert snapshot.error_budget_remaining() == 100.0
        assert snapshot.burn_rate() == 0.0

    def test_with_data(self):
        snapshot = SliSnapshot(SloDefinition("x", target=99.0))
        snapshot.good = 99
        snapshot.bad = 1
        assert snapshot.success_ratio == 99.0
        assert snapshot.error_rate == 1.0
        assert snapshot.error_budget_remaining() == 0.0
        assert snapshot.burn_rate() == 1.0

    def test_error_budget_remaining_partial(self):
        snapshot = SliSnapshot(SloDefinition("x", target=90.0))
        snapshot.good = 49
        snapshot.bad = 1
        assert snapshot.error_budget_remaining() == 80.0

    def test_budget_overrun_clamps_to_zero(self):
        snapshot = SliSnapshot(SloDefinition("x", target=99.0))
        snapshot.bad = 10
        assert snapshot.error_budget_remaining() == 0.0

    def test_to_dict(self):
        snapshot = SliSnapshot(SloDefinition("x"))
        data = snapshot.to_dict()
        assert data["total"] == 0
        assert data["burn_rate"] == 0.0


class TestSliCollector:
    def setup_method(self):
        self.collector = SliCollector()

    def test_define_and_define_many(self):
        self.collector.define(SloDefinition("api", target=99.9))
        self.collector.define_many([SloDefinition("a"), SloDefinition("b")])
        assert len(self.collector.definitions()) == 3

    def test_define_empty_name_raises(self):
        with pytest.raises(SloError):
            self.collector.define(SloDefinition(""))

    def test_record_good_and_bad(self):
        self.collector.define(SloDefinition("api", target=99.9))
        self.collector.record_good("api", 90)
        self.collector.record_bad("api", 10)
        snapshot = self.collector.snapshot("api")
        assert snapshot.good == 90
        assert snapshot.bad == 10
        assert snapshot.total == 100

    def test_record_outcome(self):
        self.collector.define(SloDefinition("api"))
        self.collector.record_outcome("api", True)
        self.collector.record_outcome("api", False)
        snapshot = self.collector.snapshot("api")
        assert (snapshot.good, snapshot.bad) == (1, 1)

    def test_auto_define_with_default_slo(self):
        self.collector.record_good("unknown", 5)
        self.collector.record_bad("unknown", 1)
        assert len(self.collector.definitions()) == 1
        snapshot = self.collector.snapshot("unknown")
        assert snapshot.slo.target == 99.9
        assert snapshot.bad == 1

    def test_snapshot_unknown_raises(self):
        with pytest.raises(SloError):
            self.collector.snapshot("nope")

    def test_snapshots_and_status(self):
        self.collector.define(SloDefinition("api"))
        self.collector.record_good("api")
        assert len(self.collector.snapshots()) == 1
        status = self.collector.status()
        assert status["slo_count"] == 1
        assert len(status["snapshots"]) == 1

    def test_error_budget_and_burn_rate_helpers(self):
        self.collector.define(SloDefinition("api", target=99.0))
        self.collector.record_good("api", 99)
        self.collector.record_bad("api", 1)
        assert self.collector.error_budget_remaining("api") == 0.0
        assert self.collector.burn_rate("api") == 1.0

    def test_window_roll(self):
        self.collector.define(SloDefinition("api", window_seconds=1))
        self.collector.record_good("api", 100)
        snapshot = self.collector.snapshot("api")
        snapshot.window_start = time.time() - 2
        self.collector.record_good("api", 1)
        rolled = self.collector.snapshot("api")
        assert rolled.good == 1
        assert rolled.bad == 0

    def test_history_capped(self):
        self.collector.define(SloDefinition("api"))
        for _ in range(6000):
            self.collector.record_good("api")
        assert len(self.collector._history["api"]) <= 5000

    def test_factory(self):
        collector = create_sli_collector(ObservabilityConfig())
        assert isinstance(collector, SliCollector)


class TestAlertRule:
    def test_validation(self):
        with pytest.raises(AlertingError):
            AlertRule("")
        with pytest.raises(AlertingError):
            AlertRule("x", severity="bogus")
        with pytest.raises(AlertingError):
            AlertRule("x", condition="", evaluator=None)

    def test_valid(self):
        rule = AlertRule("x", condition="burn_rate:api>0.5", severity="warning")
        assert rule.notify == ["slack", "pagerduty"]

    def test_to_dict(self):
        data = AlertRule("x", condition="burn_rate:api>0.5").to_dict()
        assert data["name"] == "x"
        assert data["notify"] == ["slack", "pagerduty"]


class TestAlertEngine:
    def setup_method(self):
        self.engine = AlertEngine()

    def test_disabled_returns_empty(self):
        engine = AlertEngine(ObservabilityConfig(alerts_enabled=False))
        engine.add_rule(AlertRule("x", condition="burn_rate:api>0.5"))
        assert engine.evaluate({}) == []

    def test_burn_rate_condition_fires(self):
        self.engine.add_rule(AlertRule("burn", condition="burn_rate:api>0.5"))
        fired = self.engine.evaluate({"burn_rate_api": 0.7})
        assert len(fired) == 1
        assert fired[0].rule == "burn"
        assert fired[0].severity == "warning"
        assert fired[0].metadata["burn_rate_api"] == 0.7

    def test_condition_not_fired(self):
        self.engine.add_rule(AlertRule("burn", condition="burn_rate:api>0.5"))
        assert self.engine.evaluate({"burn_rate_api": 0.1}) == []

    def test_error_budget_condition(self):
        self.engine.add_rule(AlertRule("budget", condition="error_budget:api<20"))
        fired = self.engine.evaluate({"error_budget_api": 10.0})
        assert len(fired) == 1
        assert fired[0].rule == "budget"

    def test_malformed_condition_raises(self):
        self.engine.add_rule(AlertRule("bad", condition="bogus"))
        with pytest.raises(AlertingError):
            self.engine.evaluate({})

    def test_evaluator_callable(self):
        self.engine.add_rule(AlertRule("custom", evaluator=lambda ctx: ctx.get("flag", False), severity="critical"))
        fired = self.engine.evaluate({"flag": True})
        assert len(fired) == 1
        assert fired[0].severity == "critical"

    def test_for_seconds_window(self):
        self.engine.add_rule(AlertRule("slow", condition="burn_rate:api>0.5", for_seconds=60))
        assert self.engine.evaluate({"burn_rate_api": 1.0}) == []
        assert self.engine.evaluate({"burn_rate_api": 1.0}) == []
        self.engine._firing_since["slow"] = time.time() - 61
        fired = self.engine.evaluate({"burn_rate_api": 1.0})
        assert len(fired) == 1

    def test_recovery_resets_firing(self):
        self.engine.add_rule(AlertRule("x", condition="burn_rate:api>0.5"))
        self.engine.evaluate({"burn_rate_api": 1.0})
        assert "x" in self.engine._firing_since
        self.engine.evaluate({"burn_rate_api": 0.1})
        assert "x" not in self.engine._firing_since

    def test_handlers_swallow_errors(self):
        def handler(incident):
            raise RuntimeError("boom")

        self.engine.add_rule(AlertRule("x", condition="burn_rate:api>0.5"))
        self.engine.add_handler(handler)
        fired = self.engine.evaluate({"burn_rate_api": 1.0})
        assert len(fired) == 1

    def test_add_rules_and_incidents(self):
        self.engine.add_rules([AlertRule("a", condition="burn_rate:api>0.5"), AlertRule("b", condition="error_budget:api<5")])
        self.engine.evaluate({"burn_rate_api": 1.0, "error_budget_api": 1.0})
        assert len(self.engine.incidents()) == 2
        assert len(self.engine.rules()) == 2

    def test_status(self):
        status = self.engine.status()
        assert status["rules"] == 0
        assert status["enabled"] is True

    def test_factory(self):
        assert isinstance(create_alert_engine(ObservabilityConfig()), AlertEngine)


class TestBurnRateAlertBuilder:
    def test_build(self):
        slo = SloDefinition("api")
        rules = BurnRateAlertBuilder().build(slo)
        assert [r.name for r in rules] == ["api-burn-rate-warning", "api-burn-rate-critical"]
        assert rules[0].severity == "warning"
        assert rules[1].severity == "critical"
        assert rules[0].condition == "burn_rate:api>0.5"
        assert rules[1].condition == "burn_rate:api>2.0"


class TestDashboardGenerator:
    def test_generate_defaults(self):
        generator = DashboardGenerator()
        dashboard = generator.generate("ai-router")
        assert dashboard["dashboard"]["title"] == "ai-router overview"
        assert dashboard["dashboard"]["uid"] == "ai_router_overview"
        assert len(dashboard["dashboard"]["panels"]) == 6
        assert dashboard["overwrite"] is True

    def test_generate_empty_service_raises(self):
        with pytest.raises(DashboardError):
            DashboardGenerator().generate("")

    def test_generate_custom_panels(self):
        generator = DashboardGenerator()
        dashboard = generator.generate("svc", panels=[{"id": "p1", "title": "custom"}])
        assert dashboard["dashboard"]["panels"] == [{"id": "p1", "title": "custom"}]

    def test_default_panels_promql(self):
        generator = DashboardGenerator()
        panels = generator._default_panels("ai-router")
        assert "sum(rate(ai_router_request_total[5m]))" in panels[0]["targets"][0]["expr"]
        assert "sum(rate(ai_router_request_failed[5m]))" in panels[1]["targets"][0]["expr"]
        assert "histogram_quantile" in panels[2]["targets"][0]["expr"]
        assert "ai_router_provider_latency_seconds_bucket" in panels[2]["targets"][0]["expr"]

    def test_to_json(self):
        generator = DashboardGenerator()
        text = generator.to_json(generator.generate("svc"))
        assert json.loads(text)["dashboard"]["title"] == "svc overview"
