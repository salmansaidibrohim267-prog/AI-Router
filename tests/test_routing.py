"""Tests for the adaptive routing engine."""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.models import HealthCheckResponse, ProviderStatus
from app.router import ProviderMetrics
from app.routing import (
    MODE_WEIGHTS,
    OptimizationMode,
    ProviderReputation,
    RoutingContext,
    RoutingEngine,
    build_reputation,
    estimate_prompt_tokens,
    get_model_context_window,
    get_model_cost,
)


class TestEWMALatency:
    def test_initial_ewma_is_zero(self):
        m = ProviderMetrics(name="test")
        assert m.ewma_latency == 0.0

    def test_first_request_sets_ewma(self):
        m = ProviderMetrics(name="test")
        m.record_success(100.0)
        assert m.ewma_latency == 100.0

    def test_ewma_convergence(self):
        m = ProviderMetrics(name="test")
        for _ in range(20):
            m.record_success(100.0)
        assert m.ewma_latency > 90.0
        assert m.ewma_latency < 110.0

    def test_ewma_recent_weighted(self):
        m = ProviderMetrics(name="test")
        for _ in range(10):
            m.record_success(10.0)
        assert m.ewma_latency < 20.0
        for _ in range(10):
            m.record_success(200.0)
        assert m.ewma_latency > 80.0
        assert m.ewma_latency < 200.0

    def test_ewma_after_failure(self):
        m = ProviderMetrics(name="test")
        m.record_success(100.0)
        m.record_failure(200.0)
        assert m.ewma_latency == 100.0  # failures don't update EWMA


class TestPercentileLatency:
    def test_p95_returns_ewma_when_no_history(self):
        m = ProviderMetrics(name="test")
        assert m.p95_latency == 0.0
        m.record_success(50.0)
        assert m.p95_latency == 50.0

    def test_p95_single_value(self):
        m = ProviderMetrics(name="test")
        m.record_success(42.0)
        assert m.p95_latency == 42.0

    def test_p95_many_values(self):
        m = ProviderMetrics(name="test")
        for _ in range(100):
            m.record_success(10.0)
        for _ in range(5):
            m.record_success(500.0)
        assert m.p95_latency >= 10.0
        assert m.p95_latency <= 500.0

    def test_p99_many_values(self):
        m = ProviderMetrics(name="test")
        for _ in range(99):
            m.record_success(10.0)
        m.record_success(999.0)
        assert m.p99_latency == 999.0

    def test_p95_p99_order(self):
        m = ProviderMetrics(name="test")
        for _ in range(100):
            m.record_success(50.0)
        assert m.p95_latency >= m.p99_latency - 0.01 or abs(m.p95_latency - m.p99_latency) < 0.01


class TestRollingStats:
    def test_rolling_success_rate_starts_at_one(self):
        m = ProviderMetrics(name="test")
        assert m.rolling_success_rate == 1.0

    def test_rolling_success_rate_all_success(self):
        m = ProviderMetrics(name="test")
        for _ in range(50):
            m.record_success(10.0)
        assert m.rolling_success_rate == 1.0

    def test_rolling_success_rate_mixed(self):
        m = ProviderMetrics(name="test")
        for _ in range(80):
            m.record_success(10.0)
        for _ in range(20):
            m.record_failure(10.0)
        assert abs(m.rolling_success_rate - 0.8) < 0.001

    def test_rolling_failure_rate(self):
        m = ProviderMetrics(name="test")
        for _ in range(60):
            m.record_success(10.0)
        for _ in range(40):
            m.record_failure(10.0)
        assert abs(m.rolling_failure_rate - 0.4) < 0.001

    def test_rolling_history_limited(self):
        m = ProviderMetrics(name="test")
        for _ in range(200):
            m.record_success(10.0)
        assert len(m.request_history) == 100

    def test_consecutive_success(self):
        m = ProviderMetrics(name="test")
        for _ in range(5):
            m.record_success(10.0)
        assert m.consecutive_success == 5
        m.record_failure(10.0)
        assert m.consecutive_success == 0

    def test_consecutive_failure_resets_on_success(self):
        m = ProviderMetrics(name="test")
        m.record_failure(10.0)
        m.record_failure(10.0)
        assert m.consecutive_failures == 2
        m.record_success(10.0)
        assert m.consecutive_failures == 0


class TestAverageCost:
    def test_avg_cost_no_requests(self):
        m = ProviderMetrics(name="test")
        assert m.avg_cost == 0.0

    def test_avg_cost_calculation(self):
        m = ProviderMetrics(name="test")
        m.record_success(10.0, cost_usd=0.02)
        m.record_success(10.0, cost_usd=0.04)
        assert abs(m.avg_cost - 0.03) < 0.001

    def test_avg_cost_single_request(self):
        m = ProviderMetrics(name="test")
        m.record_success(10.0, cost_usd=0.05)
        assert abs(m.avg_cost - 0.05) < 0.001


class TestEstimatePromptTokens:
    def test_empty(self):
        assert estimate_prompt_tokens("") == 1

    def test_short_string(self):
        assert estimate_prompt_tokens("hello") == 1

    def test_long_string(self):
        text = "hello " * 100
        assert estimate_prompt_tokens(text) >= 50
        assert estimate_prompt_tokens(text) <= 200

    def test_exact_divisible(self):
        text = "abcd" * 25
        assert estimate_prompt_tokens(text) == 25


class TestModelContextWindow:
    def test_known_model(self):
        assert get_model_context_window("gpt-4o") == 128000

    def test_known_model_with_prefix(self):
        assert get_model_context_window("openai/gpt-4o") == 128000

    def test_unknown_model(self):
        assert get_model_context_window("unknown-model") is None

    def test_claude_window(self):
        assert get_model_context_window("claude-3-5-sonnet-20241022") == 200000

    def test_gemini_window(self):
        assert get_model_context_window("gemini-1.5-pro") == 1048576


class TestGetModelCost:
    def test_openai_gpt4o(self):
        cost = get_model_cost("openai", "gpt-4o")
        assert cost > 0.0
        assert cost < 1.0

    def test_ollama_free(self):
        cost = get_model_cost("ollama", "llama2")
        assert cost == 0.0

    def test_unknown_provider_falls_back(self):
        cost = get_model_cost("unknown", "some-model")
        assert cost > 0.0

    def test_model_override(self):
        cost_gpt4 = get_model_cost("openai", "gpt-4o")
        cost_mini = get_model_cost("openai", "gpt-4o-mini")
        assert cost_gpt4 > cost_mini


class TestBuildReputation:
    def test_empty_metrics(self):
        m = ProviderMetrics(name="test")
        rep = build_reputation(m)
        assert rep.success_rate == 1.0
        assert rep.ewma_latency == 0.0
        assert rep.avg_cost == 0.0

    def test_with_metrics(self):
        m = ProviderMetrics(name="test")
        m.record_success(100.0, cost_usd=0.05)
        rep = build_reputation(m)
        assert rep.total_requests == 1
        assert rep.avg_cost == 0.05
        assert rep.ewma_latency == 100.0

    def test_consecutive_tracking(self):
        m = ProviderMetrics(name="test")
        m.record_success(10.0)
        m.record_success(10.0)
        m.record_failure(10.0)
        rep = build_reputation(m)
        assert rep.consecutive_success == 0
        assert rep.consecutive_failure == 1
        assert rep.rolling_success_rate == 2.0 / 3.0


class TestRoutingEngineScoring:
    def setup_method(self):
        self.engine = RoutingEngine(OptimizationMode.BALANCED)
        self.rep = ProviderReputation()
        self.ctx = RoutingContext()

    def _make_health(self, status: ProviderStatus = ProviderStatus.HEALTHY):
        return HealthCheckResponse(status=status, provider="test")

    def test_unhealthy_provider_eliminated(self):
        health = self._make_health(ProviderStatus.UNHEALTHY)
        score = self.engine.score_provider("test", "gpt-4o", self.rep, health, 0, self.ctx)
        assert score == -99999.0

    def test_healthy_provider_positive_score(self):
        health = self._make_health(ProviderStatus.HEALTHY)
        score = self.engine.score_provider("test", "gpt-4o", self.rep, health, 0, self.ctx)
        assert score > -1000.0

    def test_better_reliability_scores_higher(self):
        health = self._make_health()
        good_rep = ProviderReputation(rolling_success_rate=0.99, consecutive_success=10)
        bad_rep = ProviderReputation(rolling_success_rate=0.5, consecutive_failure=5)
        good_score = self.engine.score_provider("a", "gpt-4o", good_rep, health, 0, self.ctx)
        bad_score = self.engine.score_provider("b", "gpt-4o", bad_rep, health, 0, self.ctx)
        assert good_score > bad_score

    def test_lower_latency_scores_higher(self):
        health = self._make_health()
        fast_rep = ProviderReputation(ewma_latency=50.0, rolling_success_rate=1.0)
        slow_rep = ProviderReputation(ewma_latency=500.0, rolling_success_rate=1.0)
        fast_score = self.engine.score_provider("a", "gpt-4o", fast_rep, health, 0, self.ctx)
        slow_score = self.engine.score_provider("b", "gpt-4o", slow_rep, health, 0, self.ctx)
        assert fast_score > slow_score

    def test_user_preference_boost(self):
        health = self._make_health()
        ctx = RoutingContext(user_preference="openai")
        rep = ProviderReputation(rolling_success_rate=1.0)
        pref_score = self.engine.score_provider("openai", "gpt-4o", rep, health, 0, ctx)
        no_pref_score = self.engine.score_provider("anthropic", "claude-3", rep, health, 0, ctx)
        assert pref_score > no_pref_score


class TestContextAwareRouting:
    def setup_method(self):
        self.engine = RoutingEngine(OptimizationMode.BALANCED)
        self.rep = ProviderReputation(rolling_success_rate=1.0)
        self.health = HealthCheckResponse(status=ProviderStatus.HEALTHY, provider="test")

    def test_prompt_fits_context(self):
        ctx = RoutingContext(prompt_token_estimate=1000)
        score = self.engine.score_provider("test", "gpt-4o", self.rep, self.health, 0, ctx)
        assert score > -100.0

    def test_prompt_exceeds_context(self):
        ctx = RoutingContext(prompt_token_estimate=999999)
        score = self.engine.score_provider("test", "gpt-4o-mini", self.rep, self.health, 0, ctx)
        assert score < -300.0

    def test_context_overflow_preferred_over_fit(self):
        ctx_fit = RoutingContext(prompt_token_estimate=100)
        ctx_overflow = RoutingContext(prompt_token_estimate=999999)
        fit_score = self.engine.score_provider("test", "gpt-4o-mini", self.rep, self.health, 0, ctx_fit)
        overflow_score = self.engine.score_provider("test", "gpt-4o-mini", self.rep, self.health, 0, ctx_overflow)
        assert fit_score > overflow_score

    def test_unknown_context_window(self):
        ctx = RoutingContext(prompt_token_estimate=1000)
        score = self.engine.score_provider("test", "unknown-model", self.rep, self.health, 0, ctx)
        assert score > -100.0

    def test_large_prompt_prefers_large_context(self):
        ctx = RoutingContext(prompt_token_estimate=150000)
        small_model_score = self.engine.score_provider("test", "gemma2-9b", self.rep, self.health, 0, ctx)
        large_model_score = self.engine.score_provider("test", "gemini-1.5-pro", self.rep, self.health, 0, ctx)
        assert large_model_score > small_model_score


class TestCostAwareRouting:
    def test_cheapest_mode_prefers_cheaper(self):
        cheap_engine = RoutingEngine(OptimizationMode.CHEAPEST)
        balanced_engine = RoutingEngine(OptimizationMode.BALANCED)
        rep = ProviderReputation(rolling_success_rate=1.0)
        health = HealthCheckResponse(status=ProviderStatus.HEALTHY, provider="test")
        ctx = RoutingContext()

        cheap_score = cheap_engine.score_provider("test", "gpt-4o-mini", rep, health, 0, ctx)
        expensive_score = cheap_engine.score_provider("test", "gpt-4o", rep, health, 0, ctx)
        assert cheap_score > expensive_score

        bal_cheap = balanced_engine.score_provider("test", "gpt-4o-mini", rep, health, 0, ctx)
        bal_expensive = balanced_engine.score_provider("test", "gpt-4o", rep, health, 0, ctx)
        cheap_diff = cheap_score - expensive_score
        bal_diff = bal_cheap - bal_expensive
        assert cheap_diff > bal_diff

    def test_fastest_mode_weights(self):
        weights = MODE_WEIGHTS[OptimizationMode.FASTEST]
        assert weights["latency"] == 0.40
        assert weights["cost"] == 0.05
        assert weights["reliability"] == 0.20

    def test_quality_mode_weights(self):
        weights = MODE_WEIGHTS[OptimizationMode.QUALITY]
        assert weights["reliability"] == 0.35
        assert weights["latency"] == 0.20
        assert weights["cost"] == 0.05

    def test_balanced_mode_weights(self):
        weights = MODE_WEIGHTS[OptimizationMode.BALANCED]
        assert abs(weights["latency"] - weights["reliability"]) < 0.01


class TestOptimizationMode:
    def test_enum_values(self):
        assert OptimizationMode.QUALITY.value == "quality"
        assert OptimizationMode.BALANCED.value == "balanced"
        assert OptimizationMode.CHEAPEST.value == "cheapest"
        assert OptimizationMode.FASTEST.value == "fastest"

    def test_set_mode_string(self):
        engine = RoutingEngine()
        engine.set_mode("fastest")
        assert engine.mode == OptimizationMode.FASTEST

    def test_set_mode_enum(self):
        engine = RoutingEngine()
        engine.set_mode(OptimizationMode.CHEAPEST)
        assert engine.mode == OptimizationMode.CHEAPEST


class TestRankProviders:
    def setup_method(self):
        self.engine = RoutingEngine(OptimizationMode.BALANCED)
        self.manager = MagicMock()
        self.manager.get_health_status.return_value = HealthCheckResponse(
            status=ProviderStatus.HEALTHY, provider="test"
        )

    def test_empty_candidates(self):
        ranked = self.engine.rank_providers([], {}, self.manager, RoutingContext())
        assert ranked == []

    def test_single_candidate(self):
        ranked = self.engine.rank_providers(
            [("openai", "gpt-4o")], {}, self.manager, RoutingContext()
        )
        assert ranked == [("openai", "gpt-4o")]

    def test_multiple_candidates_ranked(self):
        metrics_map = {
            "fast": ProviderMetrics(name="fast"),
            "slow": ProviderMetrics(name="slow"),
        }
        for _ in range(10):
            metrics_map["fast"].record_success(10.0)
        for _ in range(10):
            metrics_map["slow"].record_success(500.0)
        ranked = self.engine.rank_providers(
            [("slow", "gpt-4o"), ("fast", "gpt-4o")], metrics_map, self.manager, RoutingContext()
        )
        assert ranked[0][0] == "fast"


class TestProviderMetricsRecord:
    def test_record_success_updates_all_fields(self):
        m = ProviderMetrics(name="test")
        m.record_success(100.0, cost_usd=0.01)
        assert m.total_requests == 1
        assert m.successful_requests == 1
        assert m.last_latency == 100.0
        assert m.consecutive_success == 1
        assert m.total_cost == 0.01
        assert m.last_success_time > 0

    def test_record_failure_updates_all_fields(self):
        m = ProviderMetrics(name="test")
        m.record_failure(50.0)
        assert m.total_requests == 1
        assert m.failed_requests == 1
        assert m.last_failure_time > 0
        assert m.consecutive_failures == 1
        assert m.consecutive_success == 0

    def test_uptime_seconds(self):
        m = ProviderMetrics(name="test")
        assert m.uptime_seconds > 0

    def test_rolling_throughput(self):
        m = ProviderMetrics(name="test")
        for _ in range(50):
            m.record_success(10.0)
        assert m.rolling_throughput > 0


class TestRetryableEdgeCases:
    @pytest.mark.asyncio
    async def test_non_retryable_400_raised_immediately(self):
        from app.exceptions import ProviderError
        from app.router import retry_with_backoff

        attempt = [0]

        async def coro():
            attempt[0] += 1
            raise ProviderError("bad request", status_code=400)

        with pytest.raises(ProviderError):
            await retry_with_backoff(coro, max_retries=3, base_delay=0.01)
        assert attempt[0] == 1

    @pytest.mark.asyncio
    async def test_non_retryable_401_raised_immediately(self):
        from app.exceptions import ProviderAuthError
        from app.router import retry_with_backoff

        async def coro():
            raise ProviderAuthError("unauthorized")

        with pytest.raises(ProviderAuthError):
            await retry_with_backoff(coro, max_retries=3, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_retryable_429_retried(self):
        from app.exceptions import ProviderRateLimitError
        from app.router import retry_with_backoff

        attempt = [0]

        async def coro():
            attempt[0] += 1
            if attempt[0] < 3:
                raise ProviderRateLimitError("rate limited")
            return "ok"

        result = await retry_with_backoff(coro, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert attempt[0] == 3

    @pytest.mark.asyncio
    async def test_retryable_503_retried(self):
        from app.exceptions import ProviderUnavailableError
        from app.router import retry_with_backoff

        attempt = [0]

        async def coro():
            attempt[0] += 1
            if attempt[0] < 2:
                raise ProviderUnavailableError("unavailable")
            return "ok"

        result = await retry_with_backoff(coro, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert attempt[0] == 2

    @pytest.mark.asyncio
    async def test_network_timeout_retried(self):
        import httpx
        from app.router import retry_with_backoff

        attempt = [0]

        async def coro():
            attempt[0] += 1
            if attempt[0] < 2:
                raise httpx.TimeoutException("timeout")
            return "ok"

        result = await retry_with_backoff(coro, max_retries=3, base_delay=0.01)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_connection_reset_retried(self):
        from app.router import retry_with_backoff

        attempt = [0]

        async def coro():
            attempt[0] += 1
            if attempt[0] < 2:
                raise ConnectionResetError("reset")
            return "ok"

        result = await retry_with_backoff(coro, max_retries=3, base_delay=0.01)
        assert result == "ok"


class TestHealthCheckParallel:
    @pytest.mark.asyncio
    async def test_check_health_parallel_execution(self):
        from app.providers.manager import ProviderManager

        manager = ProviderManager()
        mock_provider = MagicMock()
        mock_provider.name = "test_provider"

        async def slow_health():
            await asyncio.sleep(0.1)
            return HealthCheckResponse(status=ProviderStatus.HEALTHY, provider="test_provider")

        mock_provider.health_check = slow_health
        manager._providers = {"test_provider": mock_provider}
        manager._circuit_breakers = {}

        start = time.time()
        results = await manager.check_health(max_concurrency=5)
        elapsed = time.time() - start

        assert "test_provider" in results
        assert elapsed < 0.15

    @pytest.mark.asyncio
    async def test_check_health_with_timeout(self):
        from app.providers.manager import ProviderManager

        manager = ProviderManager()
        mock_provider = MagicMock()
        mock_provider.name = "timeout_provider"

        async def very_slow():
            await asyncio.sleep(10)
            return HealthCheckResponse(status=ProviderStatus.HEALTHY, provider="test")

        mock_provider.health_check = very_slow
        manager._providers = {"timeout_provider": mock_provider}
        manager._circuit_breakers = {}

        results = await manager.check_health(max_concurrency=5, timeout=0.05)
        assert "timeout_provider" in results
        assert results["timeout_provider"].status == ProviderStatus.UNHEALTHY
