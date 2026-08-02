from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from app.mcp.config import MCPConfig
from app.mcp.exceptions import (
    MCPConnectionError,
    MCPTimeoutError,
    MCPTransportError,
)
from app.mcp.models import MCPConnectionState
from app.mcp.protocol import JSONRPCRequest, JSONRPCResponse, IDGenerator


class MCPSession:
    def __init__(
        self,
        transport: Any,
        config: MCPConfig | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self._transport = transport
        self._config = config or MCPConfig()
        self._state = MCPConnectionState.DISCONNECTED
        self._ids = IDGenerator()
        self._heartbeat_task: asyncio.Task | None = None
        self._on_event = on_event
        self._last_error = ""
        self._lock = asyncio.Lock()

    @property
    def state(self) -> MCPConnectionState:
        return self._state

    @property
    def connected(self) -> bool:
        return self._state in (MCPConnectionState.CONNECTED, MCPConnectionState.RECONNECTING)

    @property
    def last_error(self) -> str:
        return self._last_error

    def _emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event, data or {})
            except Exception:
                pass

    async def connect(self) -> None:
        if self._state == MCPConnectionState.CONNECTED:
            return
        self._state = MCPConnectionState.CONNECTING
        try:
            await asyncio.wait_for(
                self._transport.connect(),
                timeout=self._config.connect_timeout,
            )
        except asyncio.TimeoutError as e:
            self._last_error = "connect timeout"
            self._state = MCPConnectionState.ERROR
            raise MCPTimeoutError("MCP connect timed out") from e
        except Exception as e:
            self._last_error = str(e)
            self._state = MCPConnectionState.ERROR
            raise MCPConnectionError(f"MCP connect failed: {e}") from e
        self._state = MCPConnectionState.CONNECTED
        self._emit("connected")
        self._start_heartbeat()

    def _start_heartbeat(self) -> None:
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def disconnect(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            self._heartbeat_task = None
        if self._state != MCPConnectionState.DISCONNECTED:
            self._state = MCPConnectionState.DISCONNECTING
            try:
                await self._transport.disconnect()
            except Exception:
                pass
        self._state = MCPConnectionState.DISCONNECTED
        self._emit("disconnected")

    async def ping(self, timeout: float | None = None) -> float:
        t0 = time.perf_counter()
        await self.request("ping", {}, timeout=timeout, retry=False)
        return (time.perf_counter() - t0) * 1000

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        retry: bool = True,
    ) -> Any:
        if not self.connected:
            raise MCPConnectionError("MCP session is not connected")
        timeout = timeout or self._config.request_timeout
        attempt = 0
        while True:
            try:
                request = JSONRPCRequest(
                    method,
                    params or {},
                    request_id=self._ids.next(),
                )
                response = await asyncio.wait_for(
                    self._transport.send(request),
                    timeout=timeout,
                )
                return response.raise_for_error()
            except MCPTimeoutError:
                raise
            except Exception as e:
                if (
                    retry
                    and self._config.retry_enabled
                    and attempt < self._config.retry_max_attempts - 1
                    and self._is_retryable(e)
                ):
                    attempt += 1
                    await asyncio.sleep(
                        self._config.retry_base_delay * (2 ** (attempt - 1))
                    )
                    continue
                raise

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        return isinstance(error, (MCPConnectionError, MCPTransportError))

    async def reconnect(self) -> bool:
        if not self._config.reconnect_enabled:
            return False
        self._state = MCPConnectionState.RECONNECTING
        self._emit("reconnecting")
        attempt = 0
        delay = self._config.reconnect_base_delay
        while attempt < self._config.reconnect_max_attempts:
            attempt += 1
            try:
                await self._transport.disconnect()
                await asyncio.wait_for(
                    self._transport.connect(),
                    timeout=self._config.connect_timeout,
                )
                self._state = MCPConnectionState.CONNECTED
                self._last_error = ""
                self._emit("reconnected", {"attempt": attempt})
                self._start_heartbeat()
                return True
            except Exception as e:
                self._last_error = str(e)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._config.reconnect_max_delay)
        self._state = MCPConnectionState.ERROR
        return False

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self._config.heartbeat_interval)
            if self._state != MCPConnectionState.CONNECTED:
                continue
            try:
                await asyncio.wait_for(
                    self.request("ping", {}, timeout=self._config.heartbeat_timeout, retry=False),
                    timeout=self._config.heartbeat_timeout + 1.0,
                )
                self._emit("heartbeat")
            except Exception as e:
                self._last_error = str(e)
                self._emit("heartbeat_failed", {"error": str(e)})
                if self._config.reconnect_enabled:
                    await self.reconnect()

    async def close(self) -> None:
        await self.disconnect()
