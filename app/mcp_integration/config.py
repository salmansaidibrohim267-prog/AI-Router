from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class MCPIntegrationConfig:
    retriever_tool: str = "search_knowledge"
    retrieval_param_name: str = "query"
    retrieval_limit_param: str = "limit"
    resource_prefix: str = "mcp://"
    allow_resource_fallback: bool = True
    timeout: float = 30.0
    max_retry: int = 3
    memory_store_tool: str = "memory_save"
    memory_search_tool: str = "memory_search"
    memory_delete_tool: str = "memory_delete"
    memory_scope_param: str = "scope"
    memory_top_k: int = 5
    include_memory_in_rag: bool = True
    citation_enabled: bool = True
    citation_format: str = "numeric"
    citation_resource_prefix: str = "mcp://"
    auto_store_turns: bool = True
    context_token_budget: int = 2048
    log_events: bool = True
    track_metrics: bool = True

    @classmethod
    def from_env(cls) -> MCPIntegrationConfig:
        return cls(
            retriever_tool=os.getenv("MCPI_RETRIEVER_TOOL", "search_knowledge"),
            retrieval_param_name=os.getenv("MCPI_RETRIEVAL_PARAM", "query"),
            retrieval_limit_param=os.getenv("MCPI_RETRIEVAL_LIMIT_PARAM", "limit"),
            resource_prefix=os.getenv("MCPI_RESOURCE_PREFIX", "mcp://"),
            allow_resource_fallback=os.getenv("MCPI_RESOURCE_FALLBACK", "1") == "1",
            timeout=float(os.getenv("MCPI_TIMEOUT", "30")),
            max_retry=int(os.getenv("MCPI_MAX_RETRY", "3")),
            memory_store_tool=os.getenv("MCPI_MEMORY_STORE_TOOL", "memory_save"),
            memory_search_tool=os.getenv("MCPI_MEMORY_SEARCH_TOOL", "memory_search"),
            memory_delete_tool=os.getenv("MCPI_MEMORY_DELETE_TOOL", "memory_delete"),
            memory_scope_param=os.getenv("MCPI_MEMORY_SCOPE_PARAM", "scope"),
            memory_top_k=int(os.getenv("MCPI_MEMORY_TOP_K", "5")),
            include_memory_in_rag=os.getenv("MCPI_INCLUDE_MEMORY_IN_RAG", "1") == "1",
            citation_enabled=os.getenv("MCPI_CITATION_ENABLED", "1") == "1",
            citation_format=os.getenv("MCPI_CITATION_FORMAT", "numeric"),
            citation_resource_prefix=os.getenv("MCPI_CITATION_RESOURCE_PREFIX", "mcp://"),
            auto_store_turns=os.getenv("MCPI_AUTO_STORE_TURNS", "1") == "1",
            context_token_budget=int(os.getenv("MCPI_CONTEXT_TOKEN_BUDGET", "2048")),
            log_events=os.getenv("MCPI_LOG_EVENTS", "1") == "1",
            track_metrics=os.getenv("MCPI_TRACK_METRICS", "1") == "1",
        )
