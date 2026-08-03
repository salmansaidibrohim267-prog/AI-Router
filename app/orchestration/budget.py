from __future__ import annotations

from typing import Any

from app.models import Usage


class BudgetEntry:
    def __init__(self):
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.total_cost: float = 0.0
        self.max_latency_ms: float = 0.0


class BudgetManager:
    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._max_cost = self._config.get("max_cost", 10.0)
        self._max_tokens = self._config.get("max_tokens", 1000000)
        self._max_latency = self._config.get("max_latency_ms", 60000.0)
        self._entries: list[BudgetEntry] = []

    @property
    def total_cost(self) -> float:
        return sum(e.total_cost for e in self._entries)

    @property
    def total_tokens(self) -> int:
        return sum(e.total_tokens for e in self._entries)

    @property
    def remaining_budget(self) -> float:
        return max(0.0, self._max_cost - self.total_cost)

    @property
    def remaining_tokens(self) -> int:
        return max(0, self._max_tokens - self.total_tokens)

    def record(self, usage: Usage, cost: float = 0.0, latency_ms: float = 0.0) -> None:
        entry = BudgetEntry()
        entry.prompt_tokens = usage.prompt_tokens or 0
        entry.completion_tokens = usage.completion_tokens or 0
        entry.total_tokens = usage.total_tokens or 0
        entry.total_cost = cost
        entry.max_latency_ms = max(entry.max_latency_ms, latency_ms)
        self._entries.append(entry)

    def check_limits(
        self,
        estimated_tokens: int = 0,
        estimated_cost: float = 0.0,
        estimated_latency_ms: float = 0.0,
    ) -> tuple[bool, str]:
        if self.remaining_tokens < estimated_tokens:
            return False, f"Token budget exhausted: {self.total_tokens}/{self._max_tokens}"
        if self.remaining_budget < estimated_cost:
            return False, f"Cost budget exhausted: ${self.total_cost:.4f}/${self._max_cost:.4f}"
        max_latency = max(e.max_latency_ms for e in self._entries) if self._entries else 0
        if max_latency > self._max_latency:
            return False, f"Latency limit exceeded: {max_latency:.0f}ms > {self._max_latency:.0f}ms"
        return True, ""

    def get_downgrade_suggestion(self) -> str:
        if not self._entries:
            return ""
        tiers = ["gpt4", "claude", "gemma", "qwen", "ollama"]
        current = self._entries[-1]
        if current.total_cost > 0 and self.remaining_budget < current.total_cost * 2:
            for i, tier in enumerate(tiers):
                if tier in str(self._entries[-1].total_cost):
                    if i + 1 < len(tiers):
                        return tiers[i + 1]
        return ""

    def reset(self) -> None:
        self._entries.clear()

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "remaining_budget": self.remaining_budget,
            "remaining_tokens": self.remaining_tokens,
            "max_cost": self._max_cost,
            "max_tokens": self._max_tokens,
            "max_latency_ms": self._max_latency,
            "entry_count": len(self._entries),
            "downgrade_suggestion": self.get_downgrade_suggestion(),
        }
