import pytest
from app.stats import RouterStats, ProviderStats, ModelStats
from app.models import TaskType


class TestModelStats:
    def test_defaults(self):
        m = ModelStats()
        assert m.avg_latency_ms == 0.0
        assert m.success_rate == 1.0
        assert m.failure_rate == 0.0

    def test_avg_latency(self):
        m = ModelStats()
        m.successful_requests = 4
        m.total_latency_ms = 200.0
        assert m.avg_latency_ms == 50.0

    def test_success_rate(self):
        m = ModelStats()
        m.total_requests = 10
        m.successful_requests = 8
        assert m.success_rate == 0.8
        assert abs(m.failure_rate - 0.2) < 0.001


class TestProviderStats:
    def test_defaults(self):
        p = ProviderStats()
        assert p.total_requests == 0
        assert p.success_rate == 1.0

    def test_success_rate(self):
        p = ProviderStats()
        p.total_requests = 10
        p.successful_requests = 7
        assert p.success_rate == 0.7


class TestRouterStats:
    def setup_method(self):
        self.stats = RouterStats()

    def test_initial_state(self):
        s = self.stats.summary()
        assert s.total_requests == 0
        assert s.successful_requests == 0
        assert s.failed_requests == 0

    def test_record_success(self):
        self.stats.record(
            provider="openai", model="gpt-4", task=TaskType.CHAT,
            latency_ms=100.0, success=True,
            prompt_tokens=50, completion_tokens=100, total_tokens=150,
        )
        s = self.stats.summary()
        assert s.total_requests == 1
        assert s.successful_requests == 1
        assert s.failed_requests == 0
        assert s.average_latency_ms == 100.0

    def test_record_failure(self):
        self.stats.record(
            provider="ollama", model="llama2", task=TaskType.CODING,
            latency_ms=50.0, success=False,
        )
        s = self.stats.summary()
        assert s.total_requests == 1
        assert s.successful_requests == 0
        assert s.failed_requests == 1

    def test_multiple_records(self):
        for i in range(10):
            self.stats.record(
                provider="openai", model="gpt-4", task=TaskType.CHAT,
                latency_ms=100.0, success=i % 2 == 0,
            )
        s = self.stats.summary()
        assert s.total_requests == 10
        assert s.successful_requests == 5
        assert s.failed_requests == 5
        assert s.success_rate == 0.5

    def test_provider_usage(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=10.0, success=True)
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=10.0, success=True)
        self.stats.record(provider="ollama", model="llama2", task=TaskType.CHAT, latency_ms=10.0, success=True)
        s = self.stats.summary()
        assert s.provider_usage["openai"] == 2
        assert s.provider_usage["ollama"] == 1

    def test_model_usage(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=10.0, success=True)
        self.stats.record(provider="openai", model="gpt-4o", task=TaskType.CHAT, latency_ms=10.0, success=True)
        s = self.stats.summary()
        assert s.model_usage["gpt-4"] == 1
        assert s.model_usage["gpt-4o"] == 1

    def test_task_usage(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CODING, latency_ms=10.0, success=True)
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=10.0, success=True)
        s = self.stats.summary()
        assert s.task_usage["coding"] == 1
        assert s.task_usage["chat"] == 1

    def test_get_provider_stats(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=100.0, success=True)
        result = self.stats.get_provider_stats("openai")
        assert result is not None
        assert result["total_requests"] == 1
        assert result["successful_requests"] == 1

    def test_get_provider_stats_missing(self):
        assert self.stats.get_provider_stats("nonexistent") is None

    def test_get_model_stats(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=100.0, success=True, prompt_tokens=10, completion_tokens=20, total_tokens=30)
        result = self.stats.get_model_stats("openai", "gpt-4")
        assert result is not None
        assert result["total_prompt_tokens"] == 10
        assert result["total_completion_tokens"] == 20
        assert result["total_tokens"] == 30

    def test_get_model_stats_missing(self):
        assert self.stats.get_model_stats("nonexistent", "model") is None

    def test_get_task_stats(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CODING, latency_ms=10.0, success=True)
        result = self.stats.get_task_stats(TaskType.CODING)
        assert result["task"] == "coding"
        assert result["requests"] == 1

    def test_get_error_stats(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=10.0, success=True)
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=10.0, success=False)
        result = self.stats.get_error_stats()
        assert result["total_errors"] == 1

    def test_reset(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=10.0, success=True)
        self.stats.reset()
        s = self.stats.summary()
        assert s.total_requests == 0

    def test_get_uptime_seconds(self):
        uptime = self.stats.get_uptime_seconds()
        assert uptime > 0

    def test_provider_ranking(self):
        self.stats.record(provider="openai", model="gpt-4", task=TaskType.CHAT, latency_ms=100.0, success=True)
        self.stats.record(provider="ollama", model="llama2", task=TaskType.CHAT, latency_ms=50.0, success=True)
        s = self.stats.summary()
        assert len(s.provider_ranking) == 2
