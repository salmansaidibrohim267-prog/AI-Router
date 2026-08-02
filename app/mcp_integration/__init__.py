from __future__ import annotations

from typing import Any

from .citations import MCPCitationResolver
from .config import MCPIntegrationConfig
from .coordinator import MCPIntegrationCoordinator
from .exceptions import (
    MCPCitationResolverError,
    MCPIntegrationConnectionError,
    MCPIntegrationCoordinatorError,
    MCPIntegrationError,
    MCPMemoryAdapterError,
    MCPRetrieverError,
)
from .logging import MCPIntegrationLogger
from .memory_adapter import MCPMemoryAdapter
from .models import MCPIntegrationMetrics, MCPRAGIntegrationResult, MCPRetrievalResult
from .retriever import MCPRetriever
from .statistics import MCPIntegrationMetricsTracker

__all__ = [
    "MCPIntegrationConfig",
    "MCPIntegrationLogger",
    "MCPIntegrationMetrics",
    "MCPIntegrationMetricsTracker",
    "MCPRetriever",
    "MCPMemoryAdapter",
    "MCPCitationResolver",
    "MCPIntegrationCoordinator",
    "MCPRAGIntegrationResult",
    "MCPRetrievalResult",
    "MCPIntegrationError",
    "MCPIntegrationConnectionError",
    "MCPRetrieverError",
    "MCPMemoryAdapterError",
    "MCPCitationResolverError",
    "MCPIntegrationCoordinatorError",
    "create_mcp_retriever",
    "create_mcp_memory_adapter",
    "create_mcp_citation_resolver",
    "create_mcp_integration",
]


def create_mcp_retriever(
    client: Any,
    config: MCPIntegrationConfig | None = None,
    logger: MCPIntegrationLogger | None = None,
    metrics: MCPIntegrationMetricsTracker | None = None,
) -> MCPRetriever:
    return MCPRetriever(client=client, config=config, logger=logger, metrics=metrics)


def create_mcp_memory_adapter(
    client: Any,
    config: MCPIntegrationConfig | None = None,
    logger: MCPIntegrationLogger | None = None,
    metrics: MCPIntegrationMetricsTracker | None = None,
) -> MCPMemoryAdapter:
    return MCPMemoryAdapter(client=client, config=config, logger=logger, metrics=metrics)


def create_mcp_citation_resolver(
    client: Any,
    config: MCPIntegrationConfig | None = None,
    logger: MCPIntegrationLogger | None = None,
    metrics: MCPIntegrationMetricsTracker | None = None,
    engine: Any | None = None,
) -> MCPCitationResolver:
    return MCPCitationResolver(
        client=client,
        config=config,
        logger=logger,
        metrics=metrics,
        engine=engine,
    )


def create_mcp_integration(
    client: Any,
    config: MCPIntegrationConfig | None = None,
    logger: MCPIntegrationLogger | None = None,
    metrics: MCPIntegrationMetricsTracker | None = None,
    retriever: Any | None = None,
    memory_adapter: Any | None = None,
    citation_resolver: Any | None = None,
) -> MCPIntegrationCoordinator:
    return MCPIntegrationCoordinator(
        client=client,
        retriever=retriever,
        memory_adapter=memory_adapter,
        citation_resolver=citation_resolver,
        config=config,
        logger=logger,
        metrics=metrics,
    )
