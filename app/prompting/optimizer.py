from __future__ import annotations

from typing import Callable

from app.prompting.config import PromptingConfig
from app.prompting.exceptions import PromptOptimizerError
from app.prompting.models import ContextItem, ContextSource


class ContextOptimizer:
    def __init__(self, config: PromptingConfig | None = None):
        self._config = config or PromptingConfig()

    def optimize(
        self,
        items: list[ContextItem],
        tokenizer: Callable | None = None,
    ) -> list[ContextItem]:
        if not items:
            return []
        try:
            if self._config.dedup_enabled:
                items = self._deduplicate(items)
            if self._config.merge_overlap:
                items = self._merge_overlapping(items)
            items = self._remove_low_score(items)
            if self._config.priority_recent:
                items = self._prioritize(items)
            return items
        except Exception as e:
            raise PromptOptimizerError(f"Context optimization failed: {e}") from e

    def _deduplicate(self, items: list[ContextItem]) -> list[ContextItem]:
        seen: set[str] = set()
        result: list[ContextItem] = []
        for item in items:
            normalized = self._normalize_content(item.content)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(item)
        return result

    def _normalize_content(self, content: str) -> str:
        return " ".join(content.strip().lower().split())

    def _merge_overlapping(self, items: list[ContextItem]) -> list[ContextItem]:
        if len(items) < 2:
            return items
        sorted_items = sorted(items, key=lambda i: i.score, reverse=True)
        merged: list[ContextItem] = []
        used: set[int] = set()
        for i, item in enumerate(sorted_items):
            if i in used:
                continue
            base = item
            for j in range(i + 1, len(sorted_items)):
                if j in used:
                    continue
                other = sorted_items[j]
                if self._overlap_ratio(base.content, other.content) >= self._config.overlap_ratio:
                    used.add(j)
                    base = self._join_items(base, other)
            merged.append(base)
        return merged

    def _overlap_ratio(self, a: str, b: str) -> float:
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        common = len(tokens_a & tokens_b)
        return common / min(len(tokens_a), len(tokens_b))

    def _join_items(self, a: ContextItem, b: ContextItem) -> ContextItem:
        separator = "\n\n" if not a.content.endswith("\n") else ""
        combined = a.content + separator + b.content
        return ContextItem(
            content=combined,
            source=a.source,
            score=max(a.score, b.score),
            timestamp=max(a.timestamp, b.timestamp),
            metadata={**a.metadata, **b.metadata},
        )

    def _remove_low_score(self, items: list[ContextItem]) -> list[ContextItem]:
        threshold = self._config.min_score_threshold
        return [i for i in items if i.score >= threshold]

    def _prioritize(self, items: list[ContextItem]) -> list[ContextItem]:
        def sort_key(item: ContextItem) -> tuple[float, float]:
            source_boost = 1.0 if item.source == ContextSource.USER else 0.0
            return (item.score + source_boost, item.timestamp)

        return sorted(items, key=sort_key, reverse=True)
