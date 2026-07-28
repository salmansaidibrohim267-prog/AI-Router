"""Tests for the reputation engine."""

import time
from collections import deque

import pytest

from app.reputation import (
    AGING_DECAY_PER_SECOND,
    REPUTATION_WEIGHTS,
    Trend,
    TrendData,
    apply_aging,
    circuit_breaker_multiplier,
    compute_reputation,
    compute_trend,
)


class TestComputeReputation:
    def test_perfect_provider(self):
        score = compute_reputation(
            success_rate=1.0,
            ewma_latency=10.0,
            avg_cost=0.001,
            uptime_seconds=86400,  # 24 hours
            consecutive_success=100,
            consecutive_failure=0,
        )
        assert score > 80.0
        assert score <= 100.0

    def test_poor_provider(self):
        score = compute_reputation(
            success_rate=0.5,
            ewma_latency=2000.0,
            avg_cost=0.05,
            uptime_seconds=60,  # 1 minute
            consecutive_success=0,
            consecutive_failure=10,
        )
        assert score < 50.0

    def test_success_rate_weight(self):
        high_sr = compute_reputation(
            success_rate=0.99, ewma_latency=50.0, avg_cost=0.01,
            uptime_seconds=3600, consecutive_success=10, consecutive_failure=0,
        )
        low_sr = compute_reputation(
            success_rate=0.5, ewma_latency=50.0, avg_cost=0.01,
            uptime_seconds=3600, consecutive_success=10, consecutive_failure=0,
        )
        assert high_sr > low_sr

    def test_latency_weight(self):
        fast = compute_reputation(
            success_rate=0.95, ewma_latency=20.0, avg_cost=0.01,
            uptime_seconds=3600, consecutive_success=5, consecutive_failure=0,
        )
        slow = compute_reputation(
            success_rate=0.95, ewma_latency=500.0, avg_cost=0.01,
            uptime_seconds=3600, consecutive_success=5, consecutive_failure=0,
        )
        assert fast > slow

    def test_uptime_weight(self):
        old = compute_reputation(
            success_rate=0.95, ewma_latency=50.0, avg_cost=0.01,
            uptime_seconds=604800, consecutive_success=5, consecutive_failure=0,
        )
        new = compute_reputation(
            success_rate=0.95, ewma_latency=50.0, avg_cost=0.01,
            uptime_seconds=60, consecutive_success=5, consecutive_failure=0,
        )
        assert old > new

    def test_cost_weight(self):
        cheap = compute_reputation(
            success_rate=0.95, ewma_latency=50.0, avg_cost=0.001,
            uptime_seconds=3600, consecutive_success=5, consecutive_failure=0,
        )
        expensive = compute_reputation(
            success_rate=0.95, ewma_latency=50.0, avg_cost=0.05,
            uptime_seconds=3600, consecutive_success=5, consecutive_failure=0,
        )
        assert cheap > expensive

    def test_consistency_weight(self):
        consistent = compute_reputation(
            success_rate=0.95, ewma_latency=50.0, avg_cost=0.01,
            uptime_seconds=3600, consecutive_success=20, consecutive_failure=0,
        )
        inconsistent = compute_reputation(
            success_rate=0.95, ewma_latency=50.0, avg_cost=0.01,
            uptime_seconds=3600, consecutive_success=0, consecutive_failure=5,
        )
        assert consistent > inconsistent

    def test_zero_uptime(self):
        score = compute_reputation(
            success_rate=1.0, ewma_latency=10.0, avg_cost=0.0,
            uptime_seconds=0, consecutive_success=1, consecutive_failure=0,
        )
        assert score > 0
        assert score < 100

    def test_zero_latency_defaults_to_max(self):
        score = compute_reputation(
            success_rate=1.0, ewma_latency=0.0, avg_cost=0.0,
            uptime_seconds=3600, consecutive_success=1, consecutive_failure=0,
        )
        assert score > 70.0

    def test_zero_cost_defaults_to_100(self):
        score = compute_reputation(
            success_rate=1.0, ewma_latency=50.0, avg_cost=0.0,
            uptime_seconds=3600, consecutive_success=1, consecutive_failure=0,
        )
        assert score > 70.0

    def test_reputation_weights_sum(self):
        total = sum(REPUTATION_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_mixed_provider(self):
        score = compute_reputation(
            success_rate=0.9, ewma_latency=100.0, avg_cost=0.005,
            uptime_seconds=43200, consecutive_success=15, consecutive_failure=2,
        )
        assert 40.0 < score < 95.0


class TestTrendDetection:
    def test_stable_trend_equal_windows(self):
        history = deque(maxlen=100)
        for _ in range(72):
            history.append(True)
        for _ in range(8):
            history.append(False)
        for _ in range(18):
            history.append(True)
        for _ in range(2):
            history.append(False)
        trend = compute_trend(history)
        assert trend.trend == Trend.STABLE

    def test_improving_trend(self):
        history = deque(maxlen=100)
        # First 80: 50% errors
        for _ in range(40):
            history.append(True)
        for _ in range(40):
            history.append(False)
        # Last 20: 10% errors
        for _ in range(18):
            history.append(True)
        for _ in range(2):
            history.append(False)
        trend = compute_trend(history)
        assert trend.trend == Trend.IMPROVING
        assert trend.score_delta > 0

    def test_degrading_trend(self):
        history = deque(maxlen=100)
        # First 80: 10% errors
        for _ in range(72):
            history.append(True)
        for _ in range(8):
            history.append(False)
        # Last 20: 50% errors
        for _ in range(10):
            history.append(True)
        for _ in range(10):
            history.append(False)
        trend = compute_trend(history)
        assert trend.trend == Trend.DEGRADING
        assert trend.score_delta < 0

    def test_insufficient_data_returns_stable(self):
        history = deque(maxlen=100)
        for _ in range(3):
            history.append(True)
        trend = compute_trend(history)
        assert trend.trend == Trend.STABLE
        assert trend.score_delta == 0.0

    def test_empty_history(self):
        trend = compute_trend(deque(maxlen=100))
        assert trend.trend == Trend.STABLE
        assert trend.score_delta == 0.0

    def test_trend_enum_values(self):
        assert Trend.IMPROVING.value == "improving"
        assert Trend.STABLE.value == "stable"
        assert Trend.DEGRADING.value == "degrading"

    def test_improving_score_delta_bounded(self):
        history = deque(maxlen=100)
        for _ in range(50):
            history.append(False)
        for _ in range(20):
            history.append(True)
        trend = compute_trend(history)
        assert 0 <= trend.score_delta <= 15.0

    def test_degrading_score_delta_bounded(self):
        history = deque(maxlen=100)
        for _ in range(50):
            history.append(True)
        for _ in range(20):
            history.append(False)
        trend = compute_trend(history)
        assert -30.0 <= trend.score_delta <= 0

    def test_trend_data_dataclass(self):
        td = TrendData(trend=Trend.IMPROVING, short_window_error_rate=0.1, long_window_error_rate=0.5, score_delta=10.0)
        assert td.trend == Trend.IMPROVING
        assert td.short_window_error_rate == 0.1
        assert td.score_delta == 10.0


class TestCircuitBreakerMultiplier:
    def test_closed(self):
        assert circuit_breaker_multiplier("closed") == 1.0

    def test_half_open(self):
        assert circuit_breaker_multiplier("half-open") == 0.4

    def test_open(self):
        assert circuit_breaker_multiplier("open") == 0.0

    def test_none_treated_as_closed(self):
        assert circuit_breaker_multiplier(None) == 1.0

    def test_unknown_treated_as_closed(self):
        assert circuit_breaker_multiplier("unknown") == 1.0

    def test_empty_string(self):
        assert circuit_breaker_multiplier("") == 1.0

    def test_case_sensitive(self):
        assert circuit_breaker_multiplier("OPEN") == 0.0  # case-insensitive match


class TestAging:
    def test_no_aging_when_recent(self):
        class MockStats:
            last_seen = time.time()
            total_latency = 100.0
            ewma_latency = 50.0
            total_cost = 1.0
            total_requests = 100
            successful_requests = 80
            failed_requests = 20
            total_prompt_tokens = 5000
            total_completion_tokens = 3000

        stats = MockStats()
        apply_aging(stats)
        assert abs(stats.total_latency - 100.0) < 0.01
        assert abs(stats.total_cost - 1.0) < 0.01

    def test_decay_over_time(self):
        class MockStats:
            last_seen = time.time() - 3600  # 1 hour ago
            total_latency = 100.0
            ewma_latency = 50.0
            total_cost = 1.0
            total_requests = 100
            successful_requests = 80
            failed_requests = 20
            total_prompt_tokens = 5000
            total_completion_tokens = 3000

        stats = MockStats()
        apply_aging(stats)
        assert stats.total_latency < 100.0  # decayed
        assert stats.total_latency > 0
        assert stats.total_requests < 100

    def test_heavy_decay(self):
        class MockStats:
            last_seen = time.time() - 86400 * 30  # 30 days ago
            total_latency = 1000.0
            ewma_latency = 50.0
            total_cost = 10.0
            total_requests = 500
            successful_requests = 400
            failed_requests = 100
            total_prompt_tokens = 50000
            total_completion_tokens = 30000

        stats = MockStats()
        apply_aging(stats, decay_per_second=0.999)
        assert stats.total_latency < 100.0  # heavily decayed
        assert stats.total_requests < 50

    def test_no_decay_with_zero_elapsed(self):
        class MockStats:
            last_seen = time.time()
            total_latency = 100.0
            ewma_latency = 50.0
            total_cost = 1.0
            total_requests = 100
            successful_requests = 80
            failed_requests = 20
            total_prompt_tokens = 5000
            total_completion_tokens = 3000

        stats = MockStats()
        apply_aging(stats, decay_per_second=1.0)  # no decay
        assert stats.total_latency == 100.0

    def test_aging_does_not_go_below_zero(self):
        class MockStats:
            last_seen = time.time() - 999999
            total_latency = 100.0
            ewma_latency = 50.0
            total_cost = 1.0
            total_requests = 100
            successful_requests = 80
            failed_requests = 20
            total_prompt_tokens = 5000
            total_completion_tokens = 3000

        stats = MockStats()
        apply_aging(stats)
        assert stats.total_latency >= 0
        assert stats.total_requests >= 0
        assert stats.total_prompt_tokens >= 0

    def test_decay_constant(self):
        assert 0 < AGING_DECAY_PER_SECOND < 1.0


class TestAnalyticsAPI:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from app.router import router as live_router
        self.router = live_router

    def test_get_provider_stats_includes_reputation(self):
        stats = self.router.get_provider_stats()
        assert isinstance(stats, dict)
        for name, ps in stats.items():
            assert "reputation" in ps
            assert "trend" in ps
            assert "uptime_seconds" in ps
            assert isinstance(ps["reputation"], (int, float))
            assert isinstance(ps["trend"], str)

    def test_get_provider_stats_includes_new_fields(self):
        stats = self.router.get_provider_stats()
        for name, ps in stats.items():
            assert "ewma_latency_ms" in ps
            assert "p95_latency_ms" in ps
            assert "rolling_success_rate" in ps
            assert "rolling_throughput" in ps
            assert "avg_cost" in ps
            assert "consecutive_success" in ps
            assert "consecutive_failures" in ps


class TestReputationIntegration:
    def test_reputation_in_routing_context(self):
        from app.routing import build_reputation
        from app.router import ProviderMetrics

        m = ProviderMetrics(name="test")
        for _ in range(50):
            m.record_success(50.0, cost_usd=0.01)

        rep = build_reputation(m)
        assert rep.reputation_score > 0
        assert rep.reputation_score <= 100
        assert rep.trend_delta == 0.0
        assert rep.circuit_breaker_multiplier == 1.0

    def test_reputation_with_failures(self):
        from app.routing import build_reputation
        from app.router import ProviderMetrics

        m = ProviderMetrics(name="unreliable")
        for _ in range(30):
            m.record_success(100.0)
        for _ in range(20):
            m.record_failure(100.0)

        rep = build_reputation(m)
        assert rep.reputation_score < 70  # failures bring score down

    def test_reputation_trend_detected(self):
        from app.routing import build_reputation
        from app.router import ProviderMetrics

        m = ProviderMetrics(name="degrading")
        for _ in range(80):
            m.record_success(50.0)
        for _ in range(20):
            m.record_failure(200.0)

        rep = build_reputation(m)
        assert rep.trend_delta <= 0  # last 20 are failures = degrading

    def test_circuit_breaker_multiplier_in_rep(self):
        from app.routing import build_reputation
        from app.router import ProviderMetrics

        m = ProviderMetrics(name="test")
        m.record_success(10.0)

        rep = build_reputation(m, circuit_breaker_state="half-open")
        assert rep.circuit_breaker_multiplier == 0.4

        rep2 = build_reputation(m, circuit_breaker_state="open")
        assert rep2.circuit_breaker_multiplier == 0.0

    def test_scoring_with_reputation_and_breaker(self):
        from app.models import HealthCheckResponse, ProviderStatus
        from app.routing import RoutingEngine, RoutingContext, build_reputation
        from app.router import ProviderMetrics

        engine = RoutingEngine()
        health = HealthCheckResponse(status=ProviderStatus.HEALTHY, provider="test")

        m = ProviderMetrics(name="good")
        for _ in range(20):
            m.record_success(50.0)

        rep_open = build_reputation(m, circuit_breaker_state="open")
        rep_closed = build_reputation(m, circuit_breaker_state="closed")
        ctx = RoutingContext()

        open_score = engine.score_provider("test", "gpt-4o", rep_open, health, 0, ctx)
        closed_score = engine.score_provider("test", "gpt-4o", rep_closed, health, 0, ctx)
        assert closed_score > open_score
        assert open_score == 0.0  # open breaker = 0 multiplier
