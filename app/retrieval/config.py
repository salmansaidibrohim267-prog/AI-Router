from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalConfig:
    top_k_default: int = 10
    top_k_max: int = 100
    score_threshold_default: float | None = None
    max_distance_default: float | None = None
    default_similarity: str = "cosine"
    enable_recency_boost: bool = True
    enable_quality_boost: bool = True
    enable_metadata_boost: bool = True
    enable_manual_boost: bool = True
    recency_decay_hours: float = 24.0
    quality_weight: float = 0.3
    metadata_boost_weight: float = 0.2
    manual_boost_weight: float = 0.4
    track_statistics: bool = True
    log_queries: bool = True

    default_fusion: str = "weighted_sum"
    default_normalization: str = "min_max"
    default_semantic_weight: float = 0.5
    default_keyword_weight: float = 0.5
    haystack_k1: float = 1.5
    haystack_b: float = 0.75
    query_expansion_enabled: bool = True

    @classmethod
    def from_env(cls) -> RetrievalConfig:
        return cls(
            top_k_default=int(os.getenv("RETRIEVAL_TOP_K_DEFAULT", "10")),
            top_k_max=int(os.getenv("RETRIEVAL_TOP_K_MAX", "100")),
            score_threshold_default=(
                float(v) if (v := os.getenv("RETRIEVAL_SCORE_THRESHOLD")) else None
            ),
            default_similarity=os.getenv("RETRIEVAL_SIMILARITY", "cosine"),
            enable_recency_boost=os.getenv("RETRIEVAL_RECENCY_BOOST", "1") == "1",
            enable_quality_boost=os.getenv("RETRIEVAL_QUALITY_BOOST", "1") == "1",
            enable_metadata_boost=os.getenv("RETRIEVAL_METADATA_BOOST", "1") == "1",
            enable_manual_boost=os.getenv("RETRIEVAL_MANUAL_BOOST", "1") == "1",
            recency_decay_hours=float(os.getenv("RETRIEVAL_RECENCY_DECAY_HOURS", "24")),
            quality_weight=float(os.getenv("RETRIEVAL_QUALITY_WEIGHT", "0.3")),
            metadata_boost_weight=float(os.getenv("RETRIEVAL_METADATA_BOOST_WEIGHT", "0.2")),
            manual_boost_weight=float(os.getenv("RETRIEVAL_MANUAL_BOOST_WEIGHT", "0.4")),
            track_statistics=os.getenv("RETRIEVAL_TRACK_STATISTICS", "1") == "1",
            log_queries=os.getenv("RETRIEVAL_LOG_QUERIES", "1") == "1",
            default_fusion=os.getenv("HYBRID_FUSION", "weighted_sum"),
            default_normalization=os.getenv("HYBRID_NORMALIZATION", "min_max"),
            default_semantic_weight=float(os.getenv("HYBRID_SEMANTIC_WEIGHT", "0.5")),
            default_keyword_weight=float(os.getenv("HYBRID_KEYWORD_WEIGHT", "0.5")),
            haystack_k1=float(os.getenv("BM25_K1", "1.5")),
            haystack_b=float(os.getenv("BM25_B", "0.75")),
            query_expansion_enabled=os.getenv("QUERY_EXPANSION_ENABLED", "1") == "1",
        )
