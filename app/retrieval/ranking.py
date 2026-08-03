from __future__ import annotations

import math
import time

from app.retrieval.config import RetrievalConfig
from app.retrieval.models import SearchQuery, SearchResultItem


class Ranker:
    def __init__(self, config: RetrievalConfig | None = None):
        self._config = config or RetrievalConfig()

    def rank(
        self,
        candidates: list[SearchResultItem],
        query: SearchQuery,
    ) -> list[SearchResultItem]:
        for item in candidates:
            item.similarity_score = item.score
            item.recency_score = self._compute_recency(item) if query.recency_boost else 0.0
            item.quality_score = self._compute_quality(item) if query.quality_boost else 0.0
            item.metadata_boost_score = self._compute_metadata_boost(item, query) if query.metadata_boost else 0.0
            item.manual_boost = self._get_manual_boost(item) if query.manual_boost else 0.0
            item.final_score = self._aggregate(item)

        ranked = sorted(candidates, key=lambda x: x.final_score, reverse=True)
        for i, item in enumerate(ranked):
            item.rank = i + 1
        return ranked

    def _compute_recency(self, item: SearchResultItem) -> float:
        created_at = item.metadata.get("created_at") or item.metadata.get("timestamp")
        if created_at is None:
            return 0.0
        try:
            age_seconds = time.time() - float(created_at)
            age_hours = age_seconds / 3600.0
            decay = self._config.recency_decay_hours
            if decay <= 0:
                return 1.0
            return math.exp(-age_hours / decay)
        except (ValueError, TypeError):
            return 0.0

    def _compute_quality(self, item: SearchResultItem) -> float:
        quality = item.metadata.get("quality", 0.5)
        try:
            return float(quality)
        except (ValueError, TypeError):
            return 0.5

    def _compute_metadata_boost(
        self,
        item: SearchResultItem,
        query: SearchQuery,
    ) -> float:
        boost = 0.0
        count = 0
        metadata = item.metadata

        if query.author is not None and metadata.get("author") == query.author:
            boost += 0.1
            count += 1

        if query.tags:
            item_tags = metadata.get("tags", [])
            if isinstance(item_tags, str):
                item_tags = [item_tags]
            matched = sum(1 for t in query.tags if t in item_tags)
            if matched:
                boost += 0.1 * matched
                count += 1

        if query.language is not None and metadata.get("language") == query.language:
            boost += 0.05
            count += 1

        if query.source is not None and metadata.get("source") == query.source:
            boost += 0.05
            count += 1

        if query.tenant is not None and metadata.get("tenant") == query.tenant:
            boost += 0.05
            count += 1

        return boost / max(count, 1)

    def _get_manual_boost(self, item: SearchResultItem) -> float:
        try:
            return float(item.metadata.get("boost", 0.0))
        except (ValueError, TypeError):
            return 0.0

    def _aggregate(self, item: SearchResultItem) -> float:
        sim = item.similarity_score
        rec = item.recency_score * 0.1 if self._config.enable_recency_boost else 0
        qual = item.quality_score * self._config.quality_weight if self._config.enable_quality_boost else 0
        meta = (
            item.metadata_boost_score * self._config.metadata_boost_weight if self._config.enable_metadata_boost else 0
        )  # noqa: E501
        manual = item.manual_boost * self._config.manual_boost_weight if self._config.enable_manual_boost else 0
        return sim + rec + qual + meta + manual
