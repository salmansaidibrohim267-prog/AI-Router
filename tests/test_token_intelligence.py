"""Tests for the Token Intelligence engine."""

import time
from unittest.mock import patch

import pytest

from app.costs import TokenAccounting, token_accounting
from app.routing import estimate_prompt_tokens
from app.token_intelligence import (
    CACHE_MAX_SIZE,
    CACHE_TTL,
    TokenIntelligence,
    TokenStats,
    token_intelligence,
)


# ---- Fixtures ----


@pytest.fixture
def ti():
    return TokenIntelligence()


@pytest.fixture
def empty_accounting():
    ta = TokenAccounting()
    yield ta
    ta.reset()


# ---- TokenStats ----


class TestTokenStats:
    def test_defaults(self):
        ts = TokenStats(model="test")
        assert ts.request_count == 0
        assert ts.avg_prompt_tokens == 0.0
        assert ts.avg_estimation_error == 0.0

    def test_avg_prompt(self):
        ts = TokenStats(model="test", total_prompt_tokens=1000, request_count=10)
        assert ts.avg_prompt_tokens == 100.0

    def test_avg_completion(self):
        ts = TokenStats(model="test", total_completion_tokens=500, request_count=5)
        assert ts.avg_completion_tokens == 100.0

    def test_avg_estimation_error(self):
        ts = TokenStats(model="test", estimation_errors=5.0, total_estimates=10)
        assert ts.avg_estimation_error == 0.5

    def test_to_dict(self):
        ts = TokenStats(model="gpt-4o", request_count=5, total_prompt_tokens=1000)
        d = ts.to_dict()
        assert d["model"] == "gpt-4o"
        assert d["request_count"] == 5
        assert d["avg_prompt_tokens"] == 200.0


# ---- Fallback Tokenizer ----


class TestFallbackEstimator:
    def test_empty_string(self):
        ti = TokenIntelligence()
        assert ti.estimate("", "gpt-4o") == 1

    def test_short_text(self):
        ti = TokenIntelligence()
        assert ti.estimate("hello world", "gpt-4o") == len("hello world") // 4

    def test_longer_text(self):
        ti = TokenIntelligence()
        text = "hello world " * 100
        assert ti.estimate(text, "gpt-4o") == len(text) // 4

    def test_defaults_to_fallback_without_tiktoken(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "test " * 20
        count = ti.estimate(text, "unknown-model", "unknown-provider")
        assert count == max(1, len(text) // 4)

    def test_provider_specific_claude(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        count = ti.estimate("hello world claude", "claude-3-5-sonnet-20241022", "anthropic")
        assert count == max(1, len("hello world claude") // 3)

    def test_provider_specific_gemini(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        count = ti.estimate("hello gemini", "gemini-1.5-pro", "google")
        assert count == max(1, len("hello gemini") // 3)

    def test_provider_specific_llama(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        count = ti.estimate("hello llama", "llama-3.1-8b", "meta")
        assert count == max(1, len("hello llama") // 3)


# ---- Caching ----


class TestCaching:
    def test_cache_hit_returns_same_value(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "hello world " * 50
        first = ti.estimate(text, "gpt-4o")
        second = ti.estimate(text, "gpt-4o")
        assert first == second

    def test_cache_eviction(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        for i in range(CACHE_MAX_SIZE + 10):
            ti.estimate(f"text {i}", "gpt-4o")
        assert len(ti._text_cache) <= CACHE_MAX_SIZE

    def test_cache_ttl(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "cache me"
        key = ti._cache_key(text, "gpt-4o")
        ti.estimate(text, "gpt-4o")
        assert key in ti._text_cache
        entry = ti._text_cache[key]
        entry.timestamp = time.time() - CACHE_TTL - 1
        # should miss now
        cached = ti._get_from_cache(key)
        assert cached is None

    def test_different_models_different_cache(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "same text"
        c1 = ti.estimate(text, "gpt-4o")
        c2 = ti.estimate(text, "gpt-3.5-turbo")
        assert ti._cache_key(text, "gpt-4o") != ti._cache_key(text, "gpt-3.5-turbo")


# ---- Estimate Messages ----


class TestEstimateMessages:
    def test_empty_messages(self):
        ti = TokenIntelligence()
        result = ti.estimate_messages([], "gpt-4o")
        assert result["total"] == 0
        assert result["per_role"] == {}

    def test_single_message(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        msgs = [{"role": "user", "content": "hello world"}]
        result = ti.estimate_messages(msgs, "gpt-4o")
        assert result["total"] > 0
        assert "user" in result["per_role"]

    def test_multiple_messages(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        msgs = [
            {"role": "system", "content": "You are a helper"},
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is machine intelligence"},
        ]
        result = ti.estimate_messages(msgs, "gpt-4o")
        assert result["total"] > 0
        assert set(result["per_role"].keys()) == {"system", "user", "assistant"}

    def test_object_messages(self):
        from app.models import Message, MessageRole

        ti = TokenIntelligence()
        msgs = [Message(role=MessageRole.USER, content="hello")]
        result = ti.estimate_messages(msgs, "gpt-4o")
        assert result["total"] > 0


# ---- Recording & Stats ----


class TestRecording:
    def test_record_creates_stats(self):
        ti = TokenIntelligence()
        ti.record("gpt-4o", 100, 50)
        stats = ti.get_stats("gpt-4o")
        assert stats["request_count"] == 1
        assert stats["total_prompt_tokens"] == 100
        assert stats["total_completion_tokens"] == 50

    def test_record_cache_tokens(self):
        ti = TokenIntelligence()
        ti.record("gpt-4o", 100, 50, cache_tokens=200)
        stats = ti.get_stats("gpt-4o")
        assert stats["total_cache_tokens"] == 200

    def test_record_reasoning_tokens(self):
        ti = TokenIntelligence()
        ti.record("gpt-4o", 100, 50, reasoning_tokens=300)
        stats = ti.get_stats("gpt-4o")
        assert stats["total_reasoning_tokens"] == 300

    def test_record_multiple_times(self):
        ti = TokenIntelligence()
        for _ in range(10):
            ti.record("gpt-4o", 100, 50)
        stats = ti.get_stats("gpt-4o")
        assert stats["request_count"] == 10
        assert stats["total_prompt_tokens"] == 1000

    def test_get_stats_for_nonexistent_model(self):
        ti = TokenIntelligence()
        stats = ti.get_stats("nonexistent")
        assert stats == {}

    def test_get_summary(self):
        ti = TokenIntelligence()
        ti.record("gpt-4o", 1000, 500, cache_tokens=200, reasoning_tokens=50)
        summary = ti.get_summary()
        assert summary["total_requests"] == 1
        assert summary["total_prompt_tokens"] == 1000
        assert summary["total_completion_tokens"] == 500
        assert summary["total_cache_tokens"] == 200
        assert summary["total_reasoning_tokens"] == 50
        assert summary["total_tokens"] == 1750

    def test_reset(self):
        ti = TokenIntelligence()
        ti.record("gpt-4o", 100, 50)
        ti.reset()
        assert ti.get_summary()["total_requests"] == 0
        assert ti.get_stats() == {}

    def test_estimation_error_tracking(self):
        ti = TokenIntelligence()
        ti.record("gpt-4o", 100, 50, estimated_prompt=90)
        stats = ti.get_stats("gpt-4o")
        assert stats["total_estimates"] == 1
        assert stats["avg_estimation_error_pct"] > 0

    def test_estimation_error_zero_actual(self):
        ti = TokenIntelligence()
        ti.record("gpt-4o", 0, 0, estimated_prompt=50)
        stats = ti.get_stats("gpt-4o")
        assert stats["total_estimates"] == 1


# ---- Cost Estimation ----


class TestCostEstimation:
    def test_estimate_request_cost(self):
        ti = TokenIntelligence()
        cost = ti.estimate_request_cost("openai", "gpt-4o", 1000, 500)
        assert cost["provider"] == "openai"
        assert cost["model"] == "gpt-4o"
        assert cost["prompt_tokens"] == 1000
        assert cost["estimated_cost_usd"] > 0

    def test_estimate_request_cost_zero_completion(self):
        ti = TokenIntelligence()
        cost = ti.estimate_request_cost("openai", "gpt-4o", 1000)
        assert cost["expected_completion_tokens"] == 500

    def test_estimate_request_cost_ollama_free(self):
        ti = TokenIntelligence()
        cost = ti.estimate_request_cost("ollama", "llama2", 1000, 500)
        assert cost["estimated_cost_usd"] == 0.0

    def test_estimate_request_cost_with_model_override(self):
        ti = TokenIntelligence()
        cost_mini = ti.estimate_request_cost("openai", "gpt-4o-mini", 1000, 500)
        cost_4o = ti.estimate_request_cost("openai", "gpt-4o", 1000, 500)
        assert cost_mini["estimated_cost_usd"] < cost_4o["estimated_cost_usd"]


# ---- Integration with routing ----


class TestEstimatePromptTokens:
    def test_estimate_prompt_tokens_empty(self):
        assert estimate_prompt_tokens("") == 1

    def test_estimate_prompt_tokens_short(self):
        assert estimate_prompt_tokens("hello") == 1

    def test_estimate_prompt_tokens_without_model(self):
        text = "hello world " * 50
        count = estimate_prompt_tokens(text)
        expected = max(1, len(text) // 4)
        assert count == expected

    def test_estimate_prompt_tokens_with_model(self):
        text = "hello world " * 20
        count = estimate_prompt_tokens(text, model="gpt-4o")
        assert count >= 1

    def test_estimate_prompt_tokens_with_provider(self):
        text = "hello claude " * 10
        count = estimate_prompt_tokens(text, model="claude-3-5-sonnet-20241022", provider="anthropic")
        assert count >= 1


# ---- Global Instance ----


class TestGlobalInstance:
    def test_token_intelligence_global(self):
        assert token_intelligence is not None
        assert isinstance(token_intelligence, TokenIntelligence)

    def test_token_accounting_cache_reasoning(self):
        ta = TokenAccounting()
        try:
            usage = ta.record("test_provider", "test_model", prompt_tokens=100, completion_tokens=50, cache_tokens=200, reasoning_tokens=30)
            assert usage.cache_tokens == 200
            assert usage.reasoning_tokens == 30
            assert usage.total_tokens == 380
        finally:
            ta.reset()


# ---- API Tests ----


class TestTokenAPI:
    def test_get_tokens(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/tokens")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "models" in data

    def test_get_tokens_with_model(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/tokens?model=gpt-4o")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "model_stats" in data

    def test_estimate_endpoint(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/tokens/estimate?text=hello%20world&model=gpt-4o")
        assert response.status_code == 200
        data = response.json()
        assert "estimated_tokens" in data
        assert "estimated_cost" in data
        assert data["text_length"] == 11
        assert data["estimated_tokens"] > 0


# ---- Edge Cases ----


class TestEdgeCases:
    def test_unicode_text(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "Hello, 世界! 🌍 привет"
        count = ti.estimate(text, "gpt-4o")
        assert count >= 1

    def test_very_long_text(self):
        ti = TokenIntelligence()
        text = "word " * 100000
        count = ti.estimate(text, "gpt-4o")
        assert count > 0

    def test_special_characters(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "!@#$%^&*()_+-=[]{}|;':\",./<>?`~"
        count = ti.estimate(text, "gpt-4o")
        assert count >= 1

    def test_multiline_text(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "line1\nline2\nline3\n"
        count = ti.estimate(text, "gpt-4o")
        assert count == max(1, len(text) // 4)

    def test_estimate_with_known_provider_model_pair(self):
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "hello from claude"
        count = ti.estimate(text, "claude-3-5-sonnet-20241022", "anthropic")
        assert count == max(1, len(text) // 3)


# ---- Benchmark Tests ----


class TestTokenBenchmarks:
    def test_benchmark_fallback_speed(self):
        import time
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "hello world " * 1000
        start = time.perf_counter()
        for _ in range(100):
            ti.estimate(text, "gpt-4o")
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0

    def test_benchmark_cache_speed(self):
        import time
        ti = TokenIntelligence()
        ti._tiktoken_available = False
        text = "hello world " * 1000
        ti.estimate(text, "gpt-4o")
        start = time.perf_counter()
        for _ in range(1000):
            ti.estimate(text, "gpt-4o")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0

    def test_benchmark_recording_speed(self):
        import time
        ti = TokenIntelligence()
        start = time.perf_counter()
        for _ in range(1000):
            ti.record("gpt-4o", 100, 50)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0

    def test_benchmark_estimate_messages(self):
        import time
        ti = TokenIntelligence()
        msgs = [{"role": "user", "content": "hello world " * 100}] * 10
        start = time.perf_counter()
        for _ in range(50):
            ti.estimate_messages(msgs, "gpt-4o")
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0
