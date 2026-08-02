from __future__ import annotations

import math
import time

from app.memory.config import MemoryVectorConfig
from app.memory.exceptions import MemoryScoringError
from app.memory.models import MemoryItem, MemorySearchResult


class MemoryScorer:
    def __init__(self, config: MemoryVectorConfig | None = None):
        self._config = config or MemoryVectorConfig()

    def score(
        self,
        item: MemoryItem,
        similarity: float = 0.0,
        now: float | None = None,
    ) -> MemorySearchResult:
        try:
            now = now if now is not None else time.time()
            recency = self.recency_score(item, now)
            access = self.access_score(item)
            result = MemorySearchResult(
                item=item,
                similarity=similarity,
                recency=recency,
                access=access,
                importance=item.importance,
                confidence=item.confidence,
            )
            result.score = self.combine(result)
            return result
        except Exception as e:
            raise MemoryScoringError(f"Memory scoring failed: {e}") from e

    def combine(self, result: MemorySearchResult) -> float:
        weights = {
            "similarity": self._config.similarity_weight,
            "recency": self._config.recency_weight,
            "access": self._config.access_weight,
            "importance": self._config.importance_weight,
            "confidence": self._config.confidence_weight,
        }
        total_w = sum(weights.values())
        score = (
            weights["similarity"] * result.similarity
            + weights["recency"] * result.recency
            + weights["access"] * result.access
            + weights["importance"] * result.importance
            + weights["confidence"] * result.confidence
        )
        return score / total_w if total_w > 0 else 0.0

    def recency_score(self, item: MemoryItem, now: float | None = None) -> float:
        now = now if now is not None else time.time()
        age_days = (now - item.last_accessed_at) / 86400.0
        halflife_days = self._config.recency_halflife_days
        if halflife_days <= 0:
            return 1.0
        return 0.5 ** (age_days / halflife_days)

    def access_score(self, item: MemoryItem) -> float:
        if item.access_count <= 0:
            return 0.0
        return min(1.0, math.log10(1 + item.access_count) / 2.0)

    def boost(self, item: MemoryItem, boost_factor: float) -> MemoryItem:
        item.importance = min(1.0, item.importance * boost_factor)
        return item

    def decay(self, item: MemoryItem, decay_factor: float) -> MemoryItem:
        item.importance = max(0.0, item.importance * decay_factor)
        item.confidence = max(0.0, item.confidence * decay_factor)
        return item
