from __future__ import annotations


class MCPIntegrationError(Exception):
    pass


class MCPIntegrationConnectionError(MCPIntegrationError):
    def __init__(self, msg: str = "MCP integration connection failed"):
        super().__init__(msg)


class MCPRetrieverError(MCPIntegrationError):
    def __init__(self, msg: str = "MCP retrieval failed"):
        super().__init__(msg)


class MCPMemoryAdapterError(MCPIntegrationError):
    def __init__(self, msg: str = "MCP memory adapter failed"):
        super().__init__(msg)


class MCPCitationResolverError(MCPIntegrationError):
    def __init__(self, msg: str = "MCP citation resolution failed"):
        super().__init__(msg)


class MCPIntegrationCoordinatorError(MCPIntegrationError):
    def __init__(self, msg: str = "MCP integration coordinator failed"):
        super().__init__(msg)
