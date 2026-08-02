from __future__ import annotations


class MCPError(Exception):
    pass


class MCPConnectionError(MCPError):
    def __init__(self, msg: str = "MCP connection failed"):
        super().__init__(msg)


class MCPDisconnectedError(MCPError):
    def __init__(self, msg: str = "MCP client is not connected"):
        super().__init__(msg)


class MCPTimeoutError(MCPError):
    def __init__(self, msg: str = "MCP request timed out"):
        super().__init__(msg)


class MCPProtocolError(MCPError):
    def __init__(self, msg: str = "MCP protocol error"):
        super().__init__(msg)


class MCPRPCError(MCPError):
    def __init__(self, code: int = -32000, message: str = "RPC error", data: dict | None = None):
        super().__init__(f"MCP RPC error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data or {}


class MCPToolError(MCPError):
    def __init__(self, msg: str = "MCP tool call failed"):
        super().__init__(msg)


class MCPResourceError(MCPError):
    def __init__(self, msg: str = "MCP resource operation failed"):
        super().__init__(msg)


class MCPPromptError(MCPError):
    def __init__(self, msg: str = "MCP prompt operation failed"):
        super().__init__(msg)


class MCPAuthError(MCPError):
    def __init__(self, msg: str = "MCP authentication failed"):
        super().__init__(msg)


class MCPTransportError(MCPError):
    def __init__(self, msg: str = "MCP transport failed"):
        super().__init__(msg)


class MCPManagerError(MCPError):
    def __init__(self, msg: str = "MCP connection manager failed"):
        super().__init__(msg)
