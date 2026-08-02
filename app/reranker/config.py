from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RerankerConfig:
    provider: str = "rule_based"
    model: str = ""
    top_k_retrieve: int = 50
    top_k_rerank: int = 10
    top_k_return: int = 10
    batch_size: int = 32
    max_length: int = 512
    cache_enabled: bool = True
    cache_ttl: int = 3600
    cache_max_size: int = 10000
    calibration: str = "min_max"
    ensemble_weights: str = ""
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    openai_model: str = "text-embedding-3-small"
    cohere_model: str = "rerank-english-v3.0"
    jina_model: str = "jina-reranker-v2-base-multilingual"
    bge_model: str = "BAAI/bge-reranker-v2-m3"
    timeout: int = 30
    max_retry: int = 3
    log_queries: bool = True
    track_metrics: bool = True

    @classmethod
    def from_env(cls) -> RerankerConfig:
        return cls(
            provider=os.getenv("RERANKER_PROVIDER", "rule_based"),
            model=os.getenv("RERANKER_MODEL", ""),
            top_k_retrieve=int(os.getenv("RERANKER_TOP_K_RETRIEVE", "50")),
            top_k_rerank=int(os.getenv("RERANKER_TOP_K_RERANK", "10")),
            top_k_return=int(os.getenv("RERANKER_TOP_K_RETURN", "10")),
            batch_size=int(os.getenv("RERANKER_BATCH_SIZE", "32")),
            max_length=int(os.getenv("RERANKER_MAX_LENGTH", "512")),
            cache_enabled=os.getenv("RERANKER_CACHE_ENABLED", "1") == "1",
            cache_ttl=int(os.getenv("RERANKER_CACHE_TTL", "3600")),
            cache_max_size=int(os.getenv("RERANKER_CACHE_MAX_SIZE", "10000")),
            calibration=os.getenv("RERANKER_CALIBRATION", "min_max"),
            ensemble_weights=os.getenv("RERANKER_ENSEMBLE_WEIGHTS", ""),
            cross_encoder_model=os.getenv("RERANKER_CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
            openai_model=os.getenv("RERANKER_OPENAI_MODEL", "text-embedding-3-small"),
            cohere_model=os.getenv("RERANKER_COHERE_MODEL", "rerank-english-v3.0"),
            jina_model=os.getenv("RERANKER_JINA_MODEL", "jina-reranker-v2-base-multilingual"),
            bge_model=os.getenv("RERANKER_BGE_MODEL", "BAAI/bge-reranker-v2-m3"),
            timeout=int(os.getenv("RERANKER_TIMEOUT", "30")),
            max_retry=int(os.getenv("RERANKER_MAX_RETRY", "3")),
            log_queries=os.getenv("RERANKER_LOG_QUERIES", "1") == "1",
            track_metrics=os.getenv("RERANKER_TRACK_METRICS", "1") == "1",
        )
