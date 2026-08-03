from app.mcp.auth import AuthFactory
from app.mcp.client import MCPClient
from app.mcp.config import MCPConfig
from app.mcp.manager import ConnectionManager
from app.mcp.models import (
    MCPAuthType,
    MCPCallResult,
    MCPCapabilities,
    MCPConnectionHealth,
    MCPConnectionState,
    MCPEventType,
    MCPMetrics,
    MCPPrompt,
    MCPRenderedPrompt,
    MCPResource,
    MCPServerInfo,
    MCPStreamEvent,
    MCPTool,
    MCPTransportType,
)
from app.mcp.transports import (
    HTTPTransport,
    SSETransport,
    StdioTransport,
    TransportFactory,
    WebSocketTransport,
)


def create_mcp_client(
    config: MCPConfig | None = None,
    **kwargs,
) -> MCPClient:
    if config is None:
        config = MCPConfig.from_env()
    return MCPClient(config=config, **kwargs)


def create_connection_manager(
    logger=None,
    client_factory=None,
) -> ConnectionManager:
    return ConnectionManager(logger=logger, client_factory=client_factory)


__all__ = [
    "MCPConfig",
    "MCPClient",
    "ConnectionManager",
    "MCPTool",
    "MCPResource",
    "MCPPrompt",
    "MCPRenderedPrompt",
    "MCPCallResult",
    "MCPStreamEvent",
    "MCPServerInfo",
    "MCPCapabilities",
    "MCPConnectionHealth",
    "MCPConnectionState",
    "MCPMetrics",
    "MCPEventType",
    "MCPTransportType",
    "MCPAuthType",
    "AuthFactory",
    "TransportFactory",
    "StdioTransport",
    "HTTPTransport",
    "WebSocketTransport",
    "SSETransport",
    "create_mcp_client",
    "create_connection_manager",
]
