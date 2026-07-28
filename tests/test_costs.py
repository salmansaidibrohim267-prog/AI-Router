import pytest
from app.costs import TokenAccounting, PROVIDER_COST_PER_1K, MODEL_COST_OVERRIDES


class TestTokenAccounting:
    def setup_method(self):
        self.accounting = TokenAccounting()

    def test_estimate_cost_openai_default(self):
        cost = self.accounting.estimate_cost("openai", "gpt-4", 1000, 500)
        assert cost > 0
        expected = (1000 / 1000) * 0.01 + (500 / 1000) * 0.03
        assert cost == round(expected, 8)

    def test_estimate_cost_with_model_override(self):
        cost = self.accounting.estimate_cost("openai", "gpt-4o", 1000, 500)
        expected = (1000 / 1000) * 0.01 + (500 / 1000) * 0.03
        assert cost == round(expected, 8)

    def test_estimate_cost_ollama_free(self):
        cost = self.accounting.estimate_cost("ollama", "llama2", 1000, 500)
        assert cost == 0.0

    def test_record_returns_usage(self):
        usage = self.accounting.record("openai", "gpt-4", 100, 50)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.estimated_cost > 0

    def test_get_summary(self):
        self.accounting.record("openai", "gpt-4", 1000, 500)
        self.accounting.record("ollama", "llama2", 500, 250)
        summary = self.accounting.get_summary()
        assert summary["total_prompt_tokens"] == 1500
        assert summary["total_completion_tokens"] == 750
        assert summary["total_tokens"] == 2250
        assert summary["total_cost"] > 0

    def test_get_provider_cost(self):
        self.accounting.record("openai", "gpt-4", 100, 50)
        cost = self.accounting.get_provider_cost("openai")
        assert cost["request_count"] == 1
        assert cost["total_tokens"] == 150

    def test_get_provider_cost_missing(self):
        assert self.accounting.get_provider_cost("nonexistent") == {}

    def test_reset(self):
        self.accounting.record("openai", "gpt-4", 100, 50)
        self.accounting.reset()
        summary = self.accounting.get_summary()
        assert summary["total_tokens"] == 0
        assert summary["total_cost"] == 0.0

    def test_model_key_extraction(self):
        cost = self.accounting.estimate_cost("openrouter", "openai/gpt-4o", 100, 50)
        assert cost > 0


class TestCostData:
    def test_provider_cost_per_1k_has_expected_keys(self):
        assert "openai" in PROVIDER_COST_PER_1K
        assert "anthropic" in PROVIDER_COST_PER_1K
        assert "google" in PROVIDER_COST_PER_1K
        assert "ollama" in PROVIDER_COST_PER_1K
        assert PROVIDER_COST_PER_1K["ollama"]["prompt"] == 0.0

    def test_model_cost_overrides(self):
        assert "gpt-4o" in MODEL_COST_OVERRIDES
        assert "claude-3-5-sonnet-20241022" in MODEL_COST_OVERRIDES
