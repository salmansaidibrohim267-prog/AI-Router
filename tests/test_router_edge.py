import pytest
from app.router import AIRouter, ProviderMetrics, retry_with_backoff
from app.models import ChatRequest, Message, TaskType


class TestProviderMetricsEdge:
    def test_success_rate_with_no_requests(self):
        m = ProviderMetrics(name="test")
        assert m.success_rate == 1.0

    def test_avg_latency_with_no_successes(self):
        m = ProviderMetrics(name="test")
        m.total_requests = 5
        m.failed_requests = 5
        assert m.avg_latency == float('inf')

    def test_fields_after_records(self):
        m = ProviderMetrics(name="test")
        m.total_requests = 10
        m.successful_requests = 7
        m.failed_requests = 3
        m.total_latency = 350.0
        m.last_latency = 25.0
        m.consecutive_failures = 2
        assert m.success_rate == 0.7
        assert m.avg_latency == 50.0
        assert m.last_latency == 25.0
        assert m.consecutive_failures == 2


class TestRetryWithBackoffEdge:
    @pytest.mark.asyncio
    async def test_base_delay_used(self):
        delays = []
        import asyncio
        original_sleep = asyncio.sleep

        async def mock_sleep(d):
            delays.append(d)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(asyncio, "sleep", mock_sleep)
            attempt_count = [0]
            async def coro():
                attempt_count[0] += 1
                if attempt_count[0] < 3:
                    raise ValueError("retry")
                return "ok"

            result = await retry_with_backoff(coro, max_retries=3, base_delay=1.0)
            assert result == "ok"
            assert len(delays) == 2
            assert delays[0] >= 1.0 and delays[0] < 1.6
            assert delays[1] >= 2.0 and delays[1] < 2.6
            assert attempt_count[0] == 3

    @pytest.mark.asyncio
    async def test_max_retries_one(self):
        async def coro():
            raise ValueError("fail")
        with pytest.raises(ValueError):
            await retry_with_backoff(coro, max_retries=1, base_delay=0.01)


class TestRouterEdgeCases:
    def setup_method(self):
        self.router = AIRouter()

    def test_rank_providers_single_model_multiple_providers(self):
        candidates = [("provider_a", "model1"), ("provider_b", "model1")]
        ranked = self.router._rank_providers("chat", candidates)
        assert len(ranked) == 2
        assert all(m == "model1" for _, m in ranked)

    def test_rank_providers_with_scoring(self):
        candidates = [("ollama", "model1")]
        ranked = self.router._rank_providers("chat", candidates)
        assert len(ranked) == 1

    def test_rank_providers_with_user_preference(self):
        candidates = [("ollama", "model1"), ("openai", "model2")]
        ranked = self.router._rank_providers("chat", candidates, user_preference="ollama")
        assert len(ranked) == 2

    def test_rank_providers_empty_config(self):
        ranked = self.router._rank_providers("chat", [])
        assert ranked == []

    def test_get_provider_configs_known_task(self):
        configs = self.router._get_provider_configs("chat")
        assert len(configs) > 0
        for name, model in configs:
            assert isinstance(name, str)
            assert isinstance(model, str)

    def test_get_provider_configs_unknown_task(self):
        configs = self.router._get_provider_configs("nonexistent")
        assert configs == []

    def test_get_health_summary_empty(self):
        summary = self.router.get_health_summary()
        assert isinstance(summary, dict)

    def test_get_provider_stats_empty(self):
        stats = self.router.get_provider_stats()
        assert stats == {}
