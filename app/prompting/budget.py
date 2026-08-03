from __future__ import annotations

from app.prompting.config import PromptingConfig
from app.prompting.exceptions import PromptBudgetError


class TokenBudgetManager:
    def __init__(self, config: PromptingConfig | None = None):
        self._config = config or PromptingConfig()

    def plan(
        self,
        total_estimate: int,
        token_budget: int | None = None,
        response_reservation: int | None = None,
    ) -> dict[str, int]:
        budget = token_budget or self._config.token_budget
        reservation = response_reservation or self._config.response_reservation
        if reservation >= budget:
            raise PromptBudgetError(f"Response reservation ({reservation}) must be less than token budget ({budget})")
        available = budget - reservation
        used = min(total_estimate, available)
        return {
            "budget": budget,
            "reservation": reservation,
            "available": available,
            "used": used,
            "truncated": total_estimate > available,
        }

    def trim_to_budget(
        self,
        text: str,
        max_tokens: int,
        tokenizer=None,
    ) -> str:
        count = self.count_tokens(text, tokenizer)
        if count <= max_tokens:
            return text
        words = text.split()
        budget_words = int(max_tokens * 1.3)
        if budget_words >= len(words):
            return text
        trimmed = " ".join(words[:budget_words])
        while self.count_tokens(trimmed, tokenizer) > max_tokens and len(words) > 0:
            words = words[:-1]
            trimmed = " ".join(words)
        return trimmed

    def count_tokens(self, text: str, tokenizer=None) -> int:
        if not text:
            return 0
        if tokenizer is not None:
            try:
                return len(tokenizer(text))
            except Exception:
                pass
        return len(text.split())

    def estimate_section_budget(
        self,
        sections: list[tuple[str, str]],
        available: int,
        tokenizer=None,
    ) -> dict[str, int]:
        counts = {name: self.count_tokens(content, tokenizer) for name, content in sections}
        total = sum(counts.values())
        if total == 0:
            return {name: 0 for name, _ in sections}
        if total <= available:
            return counts
        scale = available / total
        return {name: max(int(count * scale), 0) for name, count in counts.items()}
