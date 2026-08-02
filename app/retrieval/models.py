from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SimilarityMetric(str, Enum):
    COSINE = "cosine"
    DOT_PRODUCT = "dot_product"
    EUCLIDEAN = "euclidean"


@dataclass
class MetadataFilter:
    field: str
    value: Any
    operator: str = "eq"

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "value": self.value, "operator": self.operator}


@dataclass
class SearchQuery:
    text: str = ""
    vector: list[float] | None = None
    top_k: int = 10
    score_threshold: float | None = None
    max_distance: float | None = None
    collection: str = ""
    namespace: str = "default"
    similarity: SimilarityMetric = SimilarityMetric.COSINE
    metadata_filters: list[MetadataFilter] = field(default_factory=list)
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    language: str | None = None
    source: str | None = None
    tenant: str | None = None
    custom_filters: dict[str, Any] = field(default_factory=dict)
    offset: int = 0
    limit: int = 10
    cursor: str | None = None
    include_metadata: bool = True
    include_vector: bool = False
    recency_boost: bool = True
    quality_boost: bool = True
    metadata_boost: bool = True
    manual_boost: bool = True

    fusion_strategy: str = "weighted_sum"
    normalization_strategy: str = "min_max"
    semantic_weight: float = 0.5
    keyword_weight: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "top_k": self.top_k,
            "score_threshold": self.score_threshold,
            "max_distance": self.max_distance,
            "collection": self.collection,
            "namespace": self.namespace,
            "similarity": self.similarity.value,
            "metadata_filters": [f.to_dict() for f in self.metadata_filters],
            "author": self.author,
            "tags": self.tags,
            "language": self.language,
            "source": self.source,
            "tenant": self.tenant,
            "custom_filters": self.custom_filters,
            "offset": self.offset,
            "limit": self.limit,
            "include_metadata": self.include_metadata,
            "include_vector": self.include_vector,
            "fusion_strategy": self.fusion_strategy,
            "normalization_strategy": self.normalization_strategy,
            "semantic_weight": self.semantic_weight,
            "keyword_weight": self.keyword_weight,
        }


@dataclass
class SearchResultItem:
    id: str
    score: float
    rank: int = 0
    vector: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"
    collection: str = ""
    similarity_score: float = 0.0
    keyword_score: float = 0.0
    recency_score: float = 0.0
    quality_score: float = 0.0
    metadata_boost_score: float = 0.0
    manual_boost: float = 0.0
    final_score: float = 0.0

    def to_dict(self, include_vector: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "score": self.score,
            "rank": self.rank,
            "metadata": self.metadata,
            "namespace": self.namespace,
            "collection": self.collection,
        }
        if include_vector:
            d["vector"] = self.vector
        return d


@dataclass
class SearchResponse:
    results: list[SearchResultItem]
    total: int
    offset: int
    limit: int
    next_cursor: str | None = None
    query_time_ms: float = 0.0
    statistics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, include_vector: bool = False) -> dict[str, Any]:
        return {
            "results": [r.to_dict(include_vector=include_vector) for r in self.results],
            "total": self.total,
            "offset": self.offset,
            "limit": self.limit,
            "next_cursor": self.next_cursor,
            "query_time_ms": self.query_time_ms,
            "statistics": self.statistics,
        }


@dataclass
class RetrievalStatistics:
    query_count: int = 0
    total_latency_ms: float = 0.0
    average_latency_ms: float = 0.0
    total_vectors_scanned: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_comparisons: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_count": self.query_count,
            "total_latency_ms": round(self.total_latency_ms, 4),
            "average_latency_ms": round(self.average_latency_ms, 4),
            "total_vectors_scanned": self.total_vectors_scanned,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "total_comparisons": self.total_comparisons,
        }
