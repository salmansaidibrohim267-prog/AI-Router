"""Token Intelligence engine — multi-strategy token estimation and statistics."""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


CACHE_TTL = 300.0
CACHE_MAX_SIZE = 10000


@dataclass
class TokenStats:
    """Per-model token statistics."""
    model: str = ""
    total_estimates: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cache_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_estimated_prompt: int = 0
    estimation_errors: float = 0.0
    request_count: int = 0

    @property
    def avg_prompt_tokens(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_prompt_tokens / self.request_count

    @property
    def avg_completion_tokens(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_completion_tokens / self.request_count

    @property
    def avg_estimation_error(self) -> float:
        if self.total_estimates == 0:
            return 0.0
        return self.estimation_errors / self.total_estimates

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "request_count": self.request_count,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cache_tokens": self.total_cache_tokens,
            "total_reasoning_tokens": self.total_reasoning_tokens,
            "total_estimated_prompt": self.total_estimated_prompt,
            "total_estimates": self.total_estimates,
            "avg_prompt_tokens": round(self.avg_prompt_tokens, 1),
            "avg_completion_tokens": round(self.avg_completion_tokens, 1),
            "avg_estimation_error_pct": round(self.avg_estimation_error * 100, 2),
        }


@dataclass
class TokenCacheEntry:
    count: int
    timestamp: float


class TokenIntelligence:
    """Token estimation with tiktoken → provider-specific → fallback chain.

    Caches estimates, tracks per-model statistics, and provides
    pre-routing cost-aware token estimates.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._stats: dict[str, TokenStats] = {}
        self._text_cache: dict[str, TokenCacheEntry] = {}
        self._tiktoken_available = False
        self._tiktoken_encodings: dict[str, Any] = {}
        self._init_tiktoken()

    def _init_tiktoken(self) -> None:
        try:
            import tiktoken
            self._tiktoken = tiktoken
            self._tiktoken_available = True
        except ImportError:
            self._tiktoken_available = False

    def _cache_key(self, text: str, model: str) -> str:
        return hashlib.md5(f"{model}::{text}".encode()).hexdigest()

    def _get_from_cache(self, key: str) -> int | None:
        entry = self._text_cache.get(key)
        if entry and (time.time() - entry.timestamp) < CACHE_TTL:
            return entry.count
        return None

    def _put_in_cache(self, key: str, count: int) -> None:
        if len(self._text_cache) >= CACHE_MAX_SIZE:
            oldest = min(self._text_cache.keys(), key=lambda k: self._text_cache[k].timestamp)
            del self._text_cache[oldest]
        self._text_cache[key] = TokenCacheEntry(count=count, timestamp=time.time())

    # --- Tokenizer strategies ---

    def _tiktoken_count(self, text: str, model: str) -> int | None:
        if not self._tiktoken_available:
            return None
        try:
            model_key = model.split("/")[-1] if "/" in model else model
            enc_name = self._tiktoken.encoding_for_model(model_key)
            if enc_name not in self._tiktoken_encodings:
                self._tiktoken_encodings[enc_name] = self._tiktoken.get_encoding(enc_name)
            enc = self._tiktoken_encodings[enc_name]
            return len(enc.encode(text))
        except Exception:
            try:
                enc = self._tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(text))
            except Exception:
                return None

    def _provider_count(self, text: str, provider: str, model: str) -> int | None:
        model_lower = model.lower()
        provider_lower = provider.lower()
        if "claude" in model_lower or provider_lower == "anthropic":
            return self._anthropic_count(text)
        if "gemini" in model_lower or provider_lower == "google":
            return self._gemini_count(text)
        if "llama" in model_lower:
            return self._llama_count(text)
        return None

    @staticmethod
    def _anthropic_count(text: str) -> int:
        return max(1, len(text) // 3)

    @staticmethod
    def _gemini_count(text: str) -> int:
        return max(1, len(text) // 3)

    @staticmethod
    def _llama_count(text: str) -> int:
        return max(1, len(text) // 3)

    @staticmethod
    def _fallback_count(text: str) -> int:
        return max(1, len(text) // 4)

    # --- Public API ---

    def estimate(self, text: str, model: str, provider: str = "") -> int:
        """Best-effort token count: tiktoken → provider-specific → fallback."""
        cache_key = self._cache_key(text, model)
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        count = self._tiktoken_count(text, model)
        if count is None and provider:
            count = self._provider_count(text, provider, model)
        if count is None:
            count = self._fallback_count(text)

        self._put_in_cache(cache_key, count)
        return count

    def estimate_messages(self, messages: list[dict | Any], model: str, provider: str = "") -> dict[str, int]:
        """Estimate tokens for a full message list. Returns per-role breakdown."""
        total = 0
        per_role: dict[str, int] = defaultdict(int)
        for msg in messages:
            content = ""
            role = ""
            if isinstance(msg, dict):
                content = msg.get("content", "") or ""
                role = msg.get("role", "") or ""
            else:
                content = getattr(msg, "content", "") or ""
                role = getattr(msg, "role", "") or ""
            tokens = self.estimate(content, model, provider)
            total += tokens
            per_role[role] += tokens
        return {"total": total, "per_role": dict(per_role)}

    def estimate_request_cost(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        expected_completion_tokens: int = 0,
    ) -> dict[str, Any]:
        """Estimate cost before routing using token counts and pricing."""
        from app.costs import MODEL_COST_OVERRIDES, PROVIDER_COST_PER_1K
        model_key = model.split("/")[-1] if "/" in model else model
        if model_key in MODEL_COST_OVERRIDES:
            pricing = MODEL_COST_OVERRIDES[model_key]
        else:
            pricing = PROVIDER_COST_PER_1K.get(provider, PROVIDER_COST_PER_1K.get("openai"))
        prompt_usd = (prompt_tokens / 1000) * pricing["prompt"]
        if expected_completion_tokens > 0:
            completion_usd = (expected_completion_tokens / 1000) * pricing["completion"]
        else:
            completion_usd = prompt_usd * 0.5
        total = round(prompt_usd + completion_usd, 8)
        return {
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "expected_completion_tokens": expected_completion_tokens or prompt_tokens // 2,
            "estimated_cost_usd": total,
            "prompt_cost_usd": round(prompt_usd, 8),
            "completion_cost_usd": round(completion_usd, 8),
        }

    def record(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int = 0,
        cache_tokens: int = 0,
        reasoning_tokens: int = 0,
        estimated_prompt: int = 0,
    ) -> None:
        """Record actual token usage to refine future estimates."""
        with self._lock:
            if model not in self._stats:
                self._stats[model] = TokenStats(model=model)
            s = self._stats[model]
            s.request_count += 1
            s.total_prompt_tokens += prompt_tokens
            s.total_completion_tokens += completion_tokens
            s.total_cache_tokens += cache_tokens
            s.total_reasoning_tokens += reasoning_tokens
            if estimated_prompt > 0:
                s.total_estimates += 1
                error = abs(prompt_tokens - estimated_prompt) / max(prompt_tokens, 1)
                s.estimation_errors += error
                s.total_estimated_prompt += estimated_prompt

    def get_stats(self, model: str | None = None) -> dict[str, Any]:
        """Get token statistics."""
        with self._lock:
            if model:
                s = self._stats.get(model)
                if not s:
                    return {}
                return s.to_dict()
            return {
                model: s.to_dict()
                for model, s in sorted(self._stats.items())
            }

    def get_summary(self) -> dict[str, Any]:
        """Get aggregated summary across all models."""
        with self._lock:
            total_req = sum(s.request_count for s in self._stats.values())
            total_prompt = sum(s.total_prompt_tokens for s in self._stats.values())
            total_completion = sum(s.total_completion_tokens for s in self._stats.values())
            total_cache = sum(s.total_cache_tokens for s in self._stats.values())
            total_reasoning = sum(s.total_reasoning_tokens for s in self._stats.values())
            return {
                "total_requests": total_req,
                "total_prompt_tokens": total_prompt,
                "total_completion_tokens": total_completion,
                "total_cache_tokens": total_cache,
                "total_reasoning_tokens": total_reasoning,
                "total_tokens": total_prompt + total_completion + total_cache + total_reasoning,
                "models_count": len(self._stats),
                "cache_size": len(self._text_cache),
                "tiktoken_available": self._tiktoken_available,
            }

    def reset(self) -> None:
        with self._lock:
            self._stats.clear()
            self._text_cache.clear()


token_intelligence = TokenIntelligence()
