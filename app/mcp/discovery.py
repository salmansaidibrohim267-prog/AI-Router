from __future__ import annotations

import time
from typing import Any, Callable

from app.mcp.config import MCPConfig
from app.mcp.exceptions import MCPProtocolError
from app.mcp.models import (
    MCPCapabilities,
    MCPServerInfo,
)


class ServerDiscovery:
    """Discovers server identity, capabilities, and protocol version.

    The `request` callable is injected (typically the session's request method),
    keeping discovery transport-agnostic and unit-testable.
    """

    def __init__(
        self,
        request: Callable[..., Any],
        config: MCPConfig | None = None,
    ):
        self._request = request
        self._config = config or MCPConfig()
        self._server_info: MCPServerInfo | None = None
        self._tools: list[Any] = []
        self._resources: list[Any] = []
        self._prompts: list[Any] = []

    @property
    def server_info(self) -> MCPServerInfo | None:
        return self._server_info

    @property
    def tools(self) -> list[Any]:
        return list(self._tools)

    @property
    def resources(self) -> list[Any]:
        return list(self._resources)

    @property
    def prompts(self) -> list[Any]:
        return list(self._prompts)

    async def initialize(self) -> MCPServerInfo:
        result = await self._request(
            "initialize",
            {
                "protocolVersion": self._config.protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": self._config.client_name,
                    "version": self._config.client_version,
                },
            },
            retry=False,
        )
        if not isinstance(result, dict):
            raise MCPProtocolError("Initialize response must be an object")
        raw_capabilities = result.get("capabilities") or {}
        self._server_info = MCPServerInfo(
            server_name=str(result.get("serverInfo", {}).get("name", "")),
            server_version=str(result.get("serverInfo", {}).get("version", "")),
            protocol_version=str(result.get("protocolVersion", "")),
            capabilities=MCPCapabilities.from_dict(raw_capabilities),
            instructions=str(result.get("instructions", "")),
            discovered_at=time.time(),
        )
        return self._server_info

    async def discover(self) -> MCPServerInfo:
        if self._server_info is None:
            await self.initialize()
        if self._server_info is None:
            raise MCPProtocolError("Discovery requires initialize first")
        return self._server_info

    async def list_tools(self, cursor: str | None = None) -> list[Any]:
        result = await self._request("tools/list", {"cursor": cursor} if cursor else {})
        raw = result.get("tools", []) if isinstance(result, dict) else []
        self._tools = [dict(t) for t in raw]
        return list(self._tools)

    async def list_resources(self, cursor: str | None = None) -> list[Any]:
        result = await self._request("resources/list", {"cursor": cursor} if cursor else {})
        raw = result.get("resources", []) if isinstance(result, dict) else []
        self._resources = [dict(r) for r in raw]
        return list(self._resources)

    async def list_prompts(self, cursor: str | None = None) -> list[Any]:
        result = await self._request("prompts/list", {"cursor": cursor} if cursor else {})
        raw = result.get("prompts", []) if isinstance(result, dict) else []
        self._prompts = [dict(p) for p in raw]
        return list(self._prompts)

    def clear(self) -> None:
        self._server_info = None
        self._tools = []
        self._resources = []
        self._prompts = []
