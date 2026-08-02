from __future__ import annotations

from typing import Any

from app.mcp.client import MCPClient
from app.mcp.config import MCPConfig
from app.mcp.exceptions import MCPManagerError
from app.mcp.logging import MCPLogger
from app.mcp.models import MCPConnectionHealth


class ConnectionManager:
    """Manages multiple named MCP server connections."""

    def __init__(
        self,
        logger: MCPLogger | None = None,
        client_factory: Any | None = None,
    ):
        self._clients: dict[str, MCPClient] = {}
        self._configs: dict[str, MCPConfig] = {}
        self._logger = logger or MCPLogger()
        self._client_factory = client_factory

    @property
    def clients(self) -> dict[str, MCPClient]:
        return dict(self._clients)

    @property
    def names(self) -> list[str]:
        return list(self._clients)

    def register(
        self,
        name: str,
        client: MCPClient | None = None,
        config: MCPConfig | None = None,
    ) -> MCPClient:
        if name in self._clients:
            raise MCPManagerError(f"Server {name!r} is already registered")
        if client is None:
            if self._client_factory is not None:
                client = self._client_factory(config)
            else:
                client = MCPClient(config or MCPConfig())
        self._clients[name] = client
        if config is not None:
            self._configs[name] = config
        self._logger.log_event("registered", server=name)
        return client

    def unregister(self, name: str) -> MCPClient:
        client = self._clients.pop(name, None)
        if client is None:
            raise MCPManagerError(f"Server {name!r} is not registered")
        self._configs.pop(name, None)
        self._logger.log_event("unregistered", server=name)
        return client

    def get(self, name: str) -> MCPClient:
        client = self._clients.get(name)
        if client is None:
            raise MCPManagerError(f"Server {name!r} is not registered")
        return client

    def has(self, name: str) -> bool:
        return name in self._clients

    async def connect_all(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, client in self._clients.items():
            try:
                await client.connect()
                results[name] = True
            except Exception as e:
                self._logger.log_error(e, context=f"connect_all:{name}")
                results[name] = False
        return results

    async def disconnect_all(self) -> None:
        for name, client in self._clients.items():
            try:
                await client.disconnect()
            except Exception as e:
                self._logger.log_error(e, context=f"disconnect_all:{name}")

    async def shutdown_all(self) -> None:
        for name, client in self._clients.items():
            try:
                await client.shutdown()
            except Exception as e:
                self._logger.log_error(e, context=f"shutdown_all:{name}")

    async def health(self) -> list[MCPConnectionHealth]:
        statuses: list[MCPConnectionHealth] = []
        for name, client in self._clients.items():
            health = await client.health()
            health.name = name
            statuses.append(health)
        return statuses

    def connected_count(self) -> int:
        return sum(1 for c in self._clients.values() if c.connected)

    def total_count(self) -> int:
        return len(self._clients)
