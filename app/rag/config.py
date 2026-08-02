from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RAGConfig:
    retrieval_top_k: int = 10
    rerank_top_k: int = 5
    context_token_budget: int = 2048
    context_chunk_separator: str = "\n---\n"
    max_history_turns: int = 6
    prompt_version: str = "v1"
    system_prompt_template: str = ""
    confidence_threshold: float = 0.3
    fallback_strategy: str = "reduce"
    enable_query_expansion: bool = True
    enable_language_detection: bool = True
    enable_intent_classification: bool = True
    cache_enabled: bool = True
    cache_ttl: int = 3600
    cache_max_size: int = 1000
    log_queries: bool = True
    track_metrics: bool = True
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout: int = 60
    max_retry: int = 3

    @classmethod
    def from_env(cls) -> RAGConfig:
        return cls(
            retrieval_top_k=int(os.getenv("RAG_RETRIEVAL_TOP_K", "10")),
            rerank_top_k=int(os.getenv("RAG_RERANK_TOP_K", "5")),
            context_token_budget=int(os.getenv("RAG_CONTEXT_TOKEN_BUDGET", "2048")),
            context_chunk_separator=os.getenv("RAG_CONTEXT_SEPARATOR", "\n---\n"),
            max_history_turns=int(os.getenv("RAG_MAX_HISTORY_TURNS", "6")),
            prompt_version=os.getenv("RAG_PROMPT_VERSION", "v1"),
            system_prompt_template=os.getenv("RAG_SYSTEM_PROMPT_TEMPLATE", ""),
            confidence_threshold=float(os.getenv("RAG_CONFIDENCE_THRESHOLD", "0.3")),
            fallback_strategy=os.getenv("RAG_FALLBACK_STRATEGY", "reduce"),
            enable_query_expansion=os.getenv("RAG_ENABLE_QUERY_EXPANSION", "1") == "1",
            enable_language_detection=os.getenv("RAG_ENABLE_LANGUAGE_DETECTION", "1") == "1",
            enable_intent_classification=os.getenv("RAG_ENABLE_INTENT_CLASSIFICATION", "1") == "1",
            cache_enabled=os.getenv("RAG_CACHE_ENABLED", "1") == "1",
            cache_ttl=int(os.getenv("RAG_CACHE_TTL", "3600")),
            cache_max_size=int(os.getenv("RAG_CACHE_MAX_SIZE", "1000")),
            log_queries=os.getenv("RAG_LOG_QUERIES", "1") == "1",
            track_metrics=os.getenv("RAG_TRACK_METRICS", "1") == "1",
            provider=os.getenv("RAG_LLM_PROVIDER", "openai"),
            model=os.getenv("RAG_LLM_MODEL", "gpt-4o-mini"),
            temperature=float(os.getenv("RAG_LLM_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv("RAG_LLM_MAX_TOKENS", "1024")),
            timeout=int(os.getenv("RAG_LLM_TIMEOUT", "60")),
            max_retry=int(os.getenv("RAG_LLM_MAX_RETRY", "3")),
        )
