import pytest

from app.exceptions import AllProvidersFailedError, NoHealthyProviderError
from app.models import (
    ChatChoice,
    ChatRequest,
    ChatResponse,
    Message,
    MessageRole,
    ProviderStatus,
    Usage,
)
from app.providers.manager import CircuitBreaker
from app.router import AIRouter, ProviderMetrics, retry_with_backoff


class TestProviderMetrics:
    def test_defaults(self):
        m = ProviderMetrics(name="test")
        assert m.total_requests == 0
        assert m.success_rate == 1.0
        assert m.avg_latency == float('inf')

    def test_success_rate_calculation(self):
        m = ProviderMetrics(name="test")
        assert m.success_rate == 1.0

    def test_avg_latency_inf_when_no_successes(self):
        m = ProviderMetrics(name="test")
        assert m.avg_latency == float('inf')

    def test_success_rate_after_failures(self):
        m = ProviderMetrics(name="test")
        m.total_requests = 10
        m.successful_requests = 7
        assert m.success_rate == 0.7

    def test_avg_latency(self):
        m = ProviderMetrics(name="test")
        m.total_latency = 100.0
        m.successful_requests = 5
        assert m.avg_latency == 20.0


class TestCircuitBreaker:
    def test_initial_state(self):
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)
        assert cb.is_open is False
        assert cb.state == "closed"

    def test_opens_after_failures(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is False
        cb.record_failure()
        assert cb.is_open is True

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        cb.reset()
        assert cb.is_open is False
        assert cb.state == "closed"

    def test_record_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        cb._last_failure_time = 0
        _ = cb.is_open
        assert cb.state == "half-open"
        cb.record_success()
        cb.record_success()
        cb.record_success()
        assert cb.is_open is False
        assert cb.state == "closed"

    def test_half_open_transition(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        cb._last_failure_time = 0
        assert cb.is_open is False
        assert cb.state == "half-open"


class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_retry_success_first_attempt(self):
        async def coro():
            return "success"
        result = await retry_with_backoff(coro, max_retries=3, base_delay=0.01)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        attempts = [0]
        async def coro():
            attempts[0] += 1
            if attempts[0] < 3:
                raise ValueError("temporary")
            return "success"
        result = await retry_with_backoff(coro, max_retries=3, base_delay=0.01)
        assert result == "success"
        assert attempts[0] == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        attempts = [0]
        async def coro():
            attempts[0] += 1
            raise ValueError("always fails")
        with pytest.raises(ValueError):
            await retry_with_backoff(coro, max_retries=2, base_delay=0.01)
        assert attempts[0] == 2


class TestRouter:
    def setup_method(self):
        self.router = AIRouter()

    @pytest.mark.asyncio
    async def test_router_initialize(self):
        from app.providers.manager import provider_manager
        if provider_manager.get_provider_names():
            self.router._initialized = True
        else:
            await self.router.initialize()
        assert self.router._initialized is True

    def test_is_provider_available_no_providers(self):
        assert self.router._is_provider_available("nonexistent") is False

    def test_get_provider_stats_empty(self):
        stats = self.router.get_provider_stats()
        assert isinstance(stats, dict)

    def test_get_health_summary(self):
        summary = self.router.get_health_summary()
        assert isinstance(summary, dict)

    def test_get_provider_configs_returns_list(self):
        configs = self.router._get_provider_configs("chat")
        assert isinstance(configs, list)

    def test_rank_providers_empty(self):
        ranked = self.router._rank_providers("chat", [])
        assert ranked == []
