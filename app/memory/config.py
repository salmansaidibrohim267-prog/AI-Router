from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class MemoryVectorConfig:
    collection_name: str = "memory"
    namespace: str = "memory"
    archive_namespace: str = "memory_archive"
    embedding_dimensions: int = 384
    default_top_k: int = 10
    similarity_weight: float = 0.4
    recency_weight: float = 0.2
    access_weight: float = 0.15
    importance_weight: float = 0.15
    confidence_weight: float = 0.1
    recency_halflife_days: float = 7.0
    min_score_threshold: float = 0.3
    enable_ttl: bool = True
    ttl_days: float = 30.0
    max_entries: int = 10000
    enable_pruning: bool = True
    prune_batch_size: int = 100
    enable_archival: bool = True
    archive_after_days: float = 90.0
    enable_gc: bool = True
    enable_compaction: bool = True
    compaction_similarity_threshold: float = 0.85
    dedup_similarity_threshold: float = 0.85
    summarize_max_entries: int = 50
    log_ops: bool = True
    track_metrics: bool = True

    @classmethod
    def from_env(cls) -> MemoryVectorConfig:
        return cls(
            collection_name=os.getenv("MEMORY_COLLECTION", "memory"),
            namespace=os.getenv("MEMORY_NAMESPACE", "memory"),
            archive_namespace=os.getenv("MEMORY_ARCHIVE_NAMESPACE", "memory_archive"),
            embedding_dimensions=int(os.getenv("MEMORY_EMBEDDING_DIMENSIONS", "384")),
            default_top_k=int(os.getenv("MEMORY_TOP_K", "10")),
            similarity_weight=float(os.getenv("MEMORY_SIMILARITY_WEIGHT", "0.4")),
            recency_weight=float(os.getenv("MEMORY_RECENCY_WEIGHT", "0.2")),
            access_weight=float(os.getenv("MEMORY_ACCESS_WEIGHT", "0.15")),
            importance_weight=float(os.getenv("MEMORY_IMPORTANCE_WEIGHT", "0.15")),
            confidence_weight=float(os.getenv("MEMORY_CONFIDENCE_WEIGHT", "0.1")),
            recency_halflife_days=float(os.getenv("MEMORY_RECENCY_HALFLIFE_DAYS", "7.0")),
            min_score_threshold=float(os.getenv("MEMORY_MIN_SCORE", "0.3")),
            enable_ttl=os.getenv("MEMORY_ENABLE_TTL", "1") == "1",
            ttl_days=float(os.getenv("MEMORY_TTL_DAYS", "30.0")),
            max_entries=int(os.getenv("MEMORY_MAX_ENTRIES", "10000")),
            enable_pruning=os.getenv("MEMORY_ENABLE_PRUNING", "1") == "1",
            prune_batch_size=int(os.getenv("MEMORY_PRUNE_BATCH", "100")),
            enable_archival=os.getenv("MEMORY_ENABLE_ARCHIVAL", "1") == "1",
            archive_after_days=float(os.getenv("MEMORY_ARCHIVE_AFTER_DAYS", "90.0")),
            enable_gc=os.getenv("MEMORY_ENABLE_GC", "1") == "1",
            enable_compaction=os.getenv("MEMORY_ENABLE_COMPACTION", "1") == "1",
            compaction_similarity_threshold=float(os.getenv("MEMORY_COMPACTION_THRESHOLD", "0.85")),
            dedup_similarity_threshold=float(os.getenv("MEMORY_DEDUP_THRESHOLD", "0.85")),
            summarize_max_entries=int(os.getenv("MEMORY_SUMMARIZE_MAX", "50")),
            log_ops=os.getenv("MEMORY_LOG_OPS", "1") == "1",
            track_metrics=os.getenv("MEMORY_TRACK_METRICS", "1") == "1",
        )


MEMORY_TYPE_TTL_DAYS: dict[str, float | None] = {
    "short_term": 1.0,
    "session": 1.0,
    "episodic": 30.0,
    "long_term": 90.0,
    "semantic": 180.0,
    "persistent": None,
}
