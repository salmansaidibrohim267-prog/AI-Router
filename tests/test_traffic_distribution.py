"""Tests for Adaptive Traffic Distribution engine."""

import random
import threading
import time
from unittest.mock import patch

import pytest

from app.traffic_distribution import (
    ABTestConfig,
    CanaryConfig,
    MIN_WEIGHT,
    ProviderWeight,
    SelectionResult,
    ShadowConfig,
    TrafficDistribution,
    TrafficDistributionConfig,
    traffic_distribution,
)


# ---- Fixtures ----


@pytest.fixture
def td():
    return TrafficDistribution()


@pytest.fixture
def sample_scores():
    return [
        (96.0, "provider_a", "model-a"),
        (93.0, "provider_b", "model-b"),
        (88.0, "provider_c", "model-c"),
    ]


@pytest.fixture
def td_with_rebalance():
    cfg = TrafficDistributionConfig(rebalance_interval_seconds=1)
    return TrafficDistribution(cfg)


# ---- Weight Computation ----


class TestWeightComputation:
    def test_empty_scored(self, td):
        weights = td._compute_weights([])
        assert weights == []

    def test_single_provider(self, td):
        weights = td._compute_weights([(100.0, "only", "model")])
        assert len(weights) == 1
        assert weights[0].weight == 1.0

    def test_three_providers(self, td, sample_scores):
        weights = td._compute_weights(sample_scores)
        assert len(weights) == 3
        for w in weights:
            assert 0.0 <= w.weight <= 1.0
        total = sum(w.weight for w in weights)
        assert abs(total - 1.0) < 0.01

    def test_higher_score_gets_higher_weight(self, td, sample_scores):
        weights = td._compute_weights(sample_scores)
        w_map = {w.provider: w.weight for w in weights}
        assert w_map["provider_a"] >= w_map["provider_b"]
        assert w_map["provider_b"] >= w_map["provider_c"]

    def test_equal_scores_get_equal_weights(self, td):
        weights = td._compute_weights([
            (50.0, "p1", "m1"),
            (50.0, "p2", "m2"),
        ])
        w_map = {w.provider: w.weight for w in weights}
        assert abs(w_map["p1"] - w_map["p2"]) < 0.01

    def test_starvation_prevention(self, td):
        weights = td._compute_weights([
            (100.0, "fast", "m1"),
            (1.0, "slow", "m2"),
        ])
        w_map = {w.provider: w.weight for w in weights}
        assert w_map["slow"] >= MIN_WEIGHT

    def test_many_providers(self, td):
        scores = [(float(i), f"p{i}", f"m{i}") for i in range(20)]
        weights = td._compute_weights(scores)
        assert len(weights) == 20
        total = sum(w.weight for w in weights)
        assert abs(total - 1.0) < 0.01


# ---- Selection ----


class TestSelection:
    def test_select_empty(self, td):
        result = td.select([])
        assert result is None

    def test_select_returns_result(self, td, sample_scores):
        result = td.select(sample_scores)
        assert result is not None
        assert result.provider in {"provider_a", "provider_b", "provider_c"}

    def test_select_returns_provider_with_score(self, td, sample_scores):
        results = {}
        for _ in range(1000):
            r = td.select(sample_scores)
            results[r.provider] = results.get(r.provider, 0) + 1

        total = sum(results.values())
        provider_a_pct = results.get("provider_a", 0) / total
        provider_c_pct = results.get("provider_c", 0) / total
        assert provider_a_pct > provider_c_pct

    def test_select_disabled_distribution(self, td, sample_scores):
        td._config.enabled = False
        result = td.select(sample_scores)
        assert result is not None
        assert result.provider == "provider_a"

    def test_select_fallback_list(self, td):
        # Test with (provider, model) tuples
        result = td.select([("p1", "m1"), ("p2", "m2")])
        assert result is not None
        assert result.provider in {"p1", "p2"}


# ---- Weighted Pick ----


class TestWeightedPick:
    def test_empty(self, td):
        assert td._weighted_pick([]) is None

    def test_single(self, td):
        pw = ProviderWeight(provider="p", model="m", score=50.0, weight=1.0)
        assert td._weighted_pick([pw]).provider == "p"

    def test_distribution_over_many(self, td):
        weights = [
            ProviderWeight(provider="a", model="m", score=100.0, weight=0.8),
            ProviderWeight(provider="b", model="m", score=50.0, weight=0.2),
        ]
        results = {"a": 0, "b": 0}
        for _ in range(2000):
            pick = td._weighted_pick(weights)
            results[pick.provider] += 1
        total = sum(results.values())
        a_pct = results["a"] / total
        assert 0.65 < a_pct < 0.95


# ---- Starvation Prevention ----


class TestStarvationPrevention:
    def test_apply_starvation_floor(self):
        weights = [
            ProviderWeight(provider="a", model="m", score=100.0, weight=0.99),
            ProviderWeight(provider="b", model="m", score=10.0, weight=0.01),
        ]
        TrafficDistribution._apply_starvation_floor(weights)
        assert all(w.weight >= MIN_WEIGHT for w in weights)

    def test_all_zero_weights(self):
        weights = [
            ProviderWeight(provider="a", model="m", score=0.0, weight=0.0),
            ProviderWeight(provider="b", model="m", score=0.0, weight=0.0),
        ]
        TrafficDistribution._apply_starvation_floor(weights)
        total = sum(w.weight for w in weights)
        assert abs(total - 1.0) < 0.01

    def test_shadow_excluded_from_floor(self):
        weights = [
            ProviderWeight(provider="main", model="m", score=100.0, weight=1.0),
            ProviderWeight(provider="shadow", model="m", score=0.0, weight=0.0, is_shadow=True),
        ]
        TrafficDistribution._apply_starvation_floor(weights)
        shadow = [w for w in weights if w.is_shadow][0]
        assert shadow.weight < MIN_WEIGHT


# ---- Canary ----


class TestCanary:
    def test_canary_capped(self):
        cfg = TrafficDistributionConfig(
            canary=CanaryConfig(provider="new_provider", model="new_model", max_traffic_share=0.1),
        )
        td = TrafficDistribution(cfg)
        weights = td._compute_weights([
            (100.0, "new_provider", "new_model"),
            (90.0, "stable", "stable_model"),
        ])
        w_map = {w.provider: w.weight for w in weights}
        assert w_map["new_provider"] <= 0.11

    def test_canary_identified(self, td):
        td._config.canary = CanaryConfig(provider="canary", model="cm", max_traffic_share=0.05)
        assert td._is_canary("canary", "cm") is True
        assert td._is_canary("other", "om") is False


# ---- A/B Testing ----


class TestABTesting:
    def test_ab_returns_variant_occasionally(self):
        cfg = TrafficDistributionConfig(
            ab_tests=[
                ABTestConfig(
                    name="test1",
                    control_provider="old", control_model="om",
                    variant_provider="new", variant_model="nm",
                    traffic_split=0.5,
                ),
            ],
        )
        td = TrafficDistribution(cfg)
        results = {"variant": 0, "control": 0}
        for _ in range(1000):
            ab = td._check_ab_test([])
            if ab:
                results["variant" if ab[1] else "control"] += 1
        total = results["variant"] + results["control"]
        variant_pct = results["variant"] / total
        assert 0.35 < variant_pct < 0.65


# ---- Shadow Traffic ----


class TestShadow:
    def test_shadow_identified(self, td):
        td._config.shadow = ShadowConfig(provider="shadow", model="sm", capture_metrics=True)
        assert td._is_shadow("shadow", "sm") is True
        assert td._is_shadow("other", "om") is False

    def test_shadow_in_selection_result(self, td, sample_scores):
        td._config.shadow = ShadowConfig(provider="shadow_p", model="shadow_m", capture_metrics=True)
        result = td.select(sample_scores)
        assert result.shadow_provider == "shadow_p"
        assert result.shadow_model == "shadow_m"


# ---- Rebalancing ----


class TestRebalancing:
    def test_needs_rebalance_after_time(self, td_with_rebalance):
        assert td_with_rebalance._needs_rebalance() is True

    def test_not_needs_rebalance_immediately(self, td):
        td._last_rebalance = time.time()
        assert td._needs_rebalance() is False

    def test_force_rebalance(self, td, sample_scores):
        td.force_rebalance(sample_scores)
        assert len(td._weights) == 3

    def test_rebuild_weights(self, td, sample_scores):
        td._rebuild_weights(sample_scores)
        assert td._last_rebalance > 0

    def test_start_stop(self, td):
        td.start()
        assert td._running is True
        td.stop()
        assert td._running is False


# ---- Stats & Reporting ----


class TestReporting:
    def test_get_weights_returns_list(self, td, sample_scores):
        td.force_rebalance(sample_scores)
        weights = td.get_weights()
        assert len(weights) == 3
        for w in weights:
            assert "provider" in w
            assert "weight" in w
            assert "score" in w

    def test_get_distribution_report(self, td, sample_scores):
        td.force_rebalance(sample_scores)
        report = td.get_distribution_report()
        assert report["enabled"] is True
        assert report["total_selections"] == 0
        assert len(report["weights"]) == 3

    def test_distribution_report_after_selections(self, td, sample_scores):
        for _ in range(100):
            td.select(sample_scores)
        report = td.get_distribution_report()
        assert report["total_selections"] == 100
        pct = report["selection_percentages"]
        assert abs(sum(pct.values()) - 100.0) < 1.0

    def test_reset_stats(self, td, sample_scores):
        for _ in range(50):
            td.select(sample_scores)
        td.reset_stats()
        assert td._total_selections == 0
        for pw in td._weights.values():
            assert pw.assigned_requests == 0

    def test_report_includes_canary_and_ab(self):
        cfg = TrafficDistributionConfig(
            canary=CanaryConfig(provider="canary", model="cm", max_traffic_share=0.05),
            ab_tests=[
                ABTestConfig(name="myab", control_provider="old", control_model="om",
                             variant_provider="new", variant_model="nm", traffic_split=0.5),
            ],
            shadow=ShadowConfig(provider="shadow", model="sm"),
        )
        td = TrafficDistribution(cfg)
        report = td.get_distribution_report()
        assert report["canary"]["active"] is True
        assert len(report["ab_tests"]) == 1
        assert report["shadow"]["active"] is True


# ---- Config ----


class TestConfig:
    def test_default_config(self):
        td = TrafficDistribution()
        assert td._config.enabled is True
        assert td._config.rebalance_interval_seconds == 60
        assert td._config.canary is None

    def test_update_config(self, td):
        td.config = TrafficDistributionConfig(enabled=False)
        assert td.enabled is False

    def test_min_weight_in_config(self):
        cfg = TrafficDistributionConfig(min_weight=0.05)
        assert cfg.min_weight == 0.05


# ---- API Tests ----


class TestDistributionAPI:
    def test_get_distribution(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/distribution")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "weights" in data

    def test_post_rebalance(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.post("/distribution/rebalance")
        assert response.status_code == 200

    def test_post_reset(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.post("/distribution/reset")
        assert response.status_code == 200

    def test_post_config(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.post("/distribution/config?enabled=true&min_weight=0.02")
        assert response.status_code == 200


# ---- Prometheus Integration ----


class TestPrometheusMetrics:
    def test_distribution_metrics_exist(self):
        from app.metrics import (
            distribution_weight,
            distribution_selections_total,
            canary_traffic_total,
            shadow_traffic_total,
        )
        assert distribution_weight is not None
        assert distribution_selections_total is not None
        assert canary_traffic_total is not None
        assert shadow_traffic_total is not None

    def test_record_distribution_selection(self):
        from app.metrics import record_distribution_selection
        record_distribution_selection("test_provider", "test_model")
        record_distribution_selection("test_canary", "test_model", is_canary=True)
        record_distribution_selection("test_shadow", "test_model", is_shadow=True)

    def test_update_distribution_metrics(self):
        from app.metrics import update_distribution_metrics
        update_distribution_metrics()


# ---- Global Instance ----


class TestGlobalInstance:
    def test_traffic_distribution_global(self):
        assert traffic_distribution is not None
        assert isinstance(traffic_distribution, TrafficDistribution)


# ---- Concurrency ----


class TestConcurrency:
    def test_thread_safe_selection(self, sample_scores):
        td = TrafficDistribution()
        errors = []

        def select_many():
            try:
                for _ in range(100):
                    td.select(sample_scores)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=select_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert td._total_selections == 1000


# ---- Edge Cases ----


class TestEdgeCases:
    def test_single_candidate(self, td):
        result = td.select([(50.0, "only", "model")])
        assert result.provider == "only"

    def test_very_low_score(self, td):
        weights = td._compute_weights([(0.001, "low", "m"), (100.0, "high", "m")])
        w_map = {w.provider: w.weight for w in weights}
        assert w_map["low"] >= MIN_WEIGHT

    def test_negative_scores(self, td):
        weights = td._compute_weights([(-50.0, "bad", "m"), (100.0, "good", "m")])
        w_map = {w.provider: w.weight for w in weights}
        assert w_map["good"] >= w_map["bad"]

    def test_many_concurrent_selections(self, sample_scores):
        td = TrafficDistribution()
        for _ in range(10000):
            td.select(sample_scores)
        assert td._total_selections == 10000

    def test_select_returns_all_providers_eventually(self, sample_scores):
        td = TrafficDistribution()
        seen = set()
        for _ in range(5000):
            r = td.select(sample_scores)
            seen.add(r.provider)
        assert seen == {"provider_a", "provider_b", "provider_c"}


# ---- Benchmark Tests ----


class TestBenchmarks:
    def test_benchmark_selection_speed(self):
        import time
        td = TrafficDistribution()
        scores = [(float(i), f"p{i}", f"m{i}") for i in range(10)]
        start = time.perf_counter()
        for _ in range(5000):
            td.select(scores)
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0

    def test_benchmark_weight_computation_speed(self):
        import time
        td = TrafficDistribution()
        scores = [(float(i), f"p{i}", f"m{i}") for i in range(50)]
        start = time.perf_counter()
        for _ in range(1000):
            td._compute_weights(scores)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0
