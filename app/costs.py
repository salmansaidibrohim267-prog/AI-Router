"""Token accounting and cost estimation for AI Router."""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

# Estimated cost per 1K tokens (USD)
PROVIDER_COST_PER_1K = {
    "openai": {"prompt": 0.01, "completion": 0.03},
    "anthropic": {"prompt": 0.008, "completion": 0.024},
    "google": {"prompt": 0.0025, "completion": 0.01},
    "mistral": {"prompt": 0.002, "completion": 0.006},
    "groq": {"prompt": 0.0005, "completion": 0.001},
    "openrouter": {"prompt": 0.001, "completion": 0.003},
    "ollama": {"prompt": 0.0, "completion": 0.0},
}

# Per-model overrides
MODEL_COST_OVERRIDES = {
    "gpt-4o": {"prompt": 0.01, "completion": 0.03},
    "gpt-4o-mini": {"prompt": 0.0025, "completion": 0.0075},
    "claude-3-5-sonnet-20241022": {"prompt": 0.003, "completion": 0.015},
    "claude-3-5-haiku-20241022": {"prompt": 0.001, "completion": 0.005},
    "gemini-1.5-pro": {"prompt": 0.00125, "completion": 0.005},
    "gemini-1.5-flash": {"prompt": 0.00025, "completion": 0.001},
}


@dataclass
class TokenUsage:
    """Token usage for a single request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost: float = 0.0
    provider: str = ""
    model: str = ""


@dataclass
class ProviderCostStats:
    """Cost statistics per provider."""

    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cache_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0


class TokenAccounting:
    """Track token usage and estimate costs."""

    def __init__(self):
        self._lock = threading.RLock()
        self._provider_stats: dict[str, ProviderCostStats] = defaultdict(ProviderCostStats)
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_cache_tokens: int = 0
        self._total_reasoning_tokens: int = 0
        self._total_tokens: int = 0
        self._total_cost: float = 0.0

    def estimate_cost(
        self, provider: str, model: str, prompt_tokens: int, completion_tokens: int, cache_tokens: int = 0
    ) -> float:  # noqa: E501
        """Estimate cost for a request."""
        # Check model-specific pricing first
        model_key = model.split("/")[-1] if "/" in model else model
        if model_key in MODEL_COST_OVERRIDES:
            pricing = MODEL_COST_OVERRIDES[model_key]
        else:
            pricing = PROVIDER_COST_PER_1K.get(provider, PROVIDER_COST_PER_1K.get("openai"))

        # Apply 50% discount for cached prompt tokens
        effective_prompt = max(0, prompt_tokens - cache_tokens * 0.5)
        prompt_cost = (effective_prompt / 1000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1000) * pricing["completion"]
        return round(prompt_cost + completion_cost, 8)

    def record(
        self,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> TokenUsage:
        """Record token usage and return estimated cost."""
        total_tokens = prompt_tokens + completion_tokens + cache_tokens + reasoning_tokens
        cost = self.estimate_cost(provider, model, prompt_tokens, completion_tokens, cache_tokens)

        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cache_tokens=cache_tokens,
            reasoning_tokens=reasoning_tokens,
            estimated_cost=cost,
            provider=provider,
            model=model,
        )

        with self._lock:
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens
            self._total_cache_tokens += cache_tokens
            self._total_reasoning_tokens += reasoning_tokens
            self._total_tokens += total_tokens
            self._total_cost += cost

            ps = self._provider_stats[provider]
            ps.total_prompt_tokens += prompt_tokens
            ps.total_completion_tokens += completion_tokens
            ps.total_cache_tokens += cache_tokens
            ps.total_reasoning_tokens += reasoning_tokens
            ps.total_tokens += total_tokens
            ps.total_cost += cost
            ps.request_count += 1

        return usage

    def get_summary(self) -> dict[str, Any]:
        """Get token accounting summary."""
        with self._lock:
            return {
                "total_prompt_tokens": self._total_prompt_tokens,
                "total_completion_tokens": self._total_completion_tokens,
                "total_cache_tokens": self._total_cache_tokens,
                "total_reasoning_tokens": self._total_reasoning_tokens,
                "total_tokens": self._total_tokens,
                "total_cost": round(self._total_cost, 6),
                "providers": {
                    name: {
                        "prompt_tokens": ps.total_prompt_tokens,
                        "completion_tokens": ps.total_completion_tokens,
                        "cache_tokens": ps.total_cache_tokens,
                        "reasoning_tokens": ps.total_reasoning_tokens,
                        "total_tokens": ps.total_tokens,
                        "total_cost": round(ps.total_cost, 6),
                        "request_count": ps.request_count,
                    }
                    for name, ps in self._provider_stats.items()
                },
            }

    def get_provider_cost(self, provider: str) -> dict[str, Any]:
        """Get cost stats for a specific provider."""
        with self._lock:
            ps = self._provider_stats.get(provider)
            if not ps:
                return {}
            return {
                "prompt_tokens": ps.total_prompt_tokens,
                "completion_tokens": ps.total_completion_tokens,
                "cache_tokens": ps.total_cache_tokens,
                "reasoning_tokens": ps.total_reasoning_tokens,
                "total_tokens": ps.total_tokens,
                "total_cost": round(ps.total_cost, 6),
                "request_count": ps.request_count,
            }

    def reset(self) -> None:
        """Reset all accounting."""
        with self._lock:
            self._provider_stats.clear()
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._total_cache_tokens = 0
            self._total_reasoning_tokens = 0
            self._total_tokens = 0
            self._total_cost = 0.0


token_accounting = TokenAccounting()
