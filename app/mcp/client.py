from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Callable

from app.mcp.auth import Authenticator, AuthFactory
from app.mcp.config import MCPConfig
from app.mcp.discovery import ServerDiscovery
from app.mcp.exceptions import (
    MCPConnectionError,
    MCPDisconnectedError,
    MCPError,
    MCPPromptError,
    MCPResourceError,
    MCPToolError,
)
from app.mcp.logging import MCPLogger
from app.mcp.models import (
    MCPCallResult,
    MCPConnectionHealth,
    MCPConnectionState,
    MCPPrompt,
    MCPRenderedPrompt,
    MCPResource,
    MCPStreamEvent,
    MCPServerInfo,
    MCPTool,
)
from app.mcp.protocol import JSONRPCRequest
from app.mcp.session import MCPSession
from app.mcp.statistics import MCPMetricsTracker
from app.mcp.transports import MCPTransport, TransportFactory


class MCPClient:
    """Async-first Model Context Protocol client.

    Composes a transport adapter, authentication strategy, session manager
    (heartbeat/reconnect/retry), capability discovery, and API surface for
    tools, resources, and prompts via dependency injection.
    """

    def __init__(
        self,
        config: MCPConfig | None = None,
        transport: MCPTransport | None = None,
        authenticator: Authenticator | None = None,
        session: MCPSession | None = None,
        discovery: ServerDiscovery | None = None,
        transport_factory: TransportFactory | None = None,
        logger: MCPLogger | None = None,
        metrics: MCPMetricsTracker | None = None,
    ):
        self._config = config or MCPConfig()
        self._transport_factory = transport_factory or TransportFactory()
        if authenticator is None:
            authenticator = AuthFactory().create(self._config.auth_type, self._config)
        self._auth = authenticator
        self._transport = transport or self._transport_factory.create(self._config, self._auth)
        self._logger = logger or MCPLogger()
        self._metrics = metrics or MCPMetricsTracker()
        self._on_event = self._handle_session_event
        self._session = session or MCPSession(
            self._transport, self._config, on_event=self._on_event
        )
        self._discovery = discovery or ServerDiscovery(
            self._session.request, self._config
        )
        self._notification_task: asyncio.Task | None = None
        self._watchers: dict[str, list[Callable[[str, dict[str, Any]], Any]]] = {}
        self._connected = False

    # ------------------------------------------------------------ properties

    @property
    def connected(self) -> bool:
        return self._connected and self._session.connected

    @property
    def state(self) -> MCPConnectionState:
        return self._session.state

    @property
    def server_info(self) -> MCPServerInfo | None:
        return self._discovery.server_info

    @property
    def transport(self) -> MCPTransport:
        return self._transport

    @property
    def session(self) -> MCPSession:
        return self._session

    # ------------------------------------------------------------ lifecycle

    async def connect(self) -> None:
        try:
            await self._session.connect()
            if self._config.discover_on_connect:
                await self._discovery.initialize()
            self._connected = True
            self._metrics.record_connection()
            self._logger.log_event("connected", transport=self._transport.name)
            self._start_notification_loop()
        except MCPError:
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MCPConnectionError(f"MCP connect failed: {e}") from e

    async def disconnect(self) -> None:
        self._connected = False
        if self._notification_task is not None:
            self._notification_task.cancel()
            try:
                await self._notification_task
            except (asyncio.CancelledError, Exception):
                pass
            self._notification_task = None
        self._watchers.clear()
        await self._session.disconnect()
        self._metrics.record_disconnection()
        self._logger.log_event("disconnected")

    async def initialize(self) -> MCPServerInfo:
        info = await self._discovery.initialize()
        self._logger.log_event("initialized", server=info.server_name,
                               protocol=info.protocol_version)
        return info

    async def ping(self, timeout: float | None = None) -> float:
        try:
            latency = await self._session.ping(timeout)
        except Exception as e:
            self._metrics.record_error()
            raise
        self._metrics.record_ping(latency)
        return latency

    async def shutdown(self) -> None:
        try:
            if self._session.connected:
                await self._session.request("shutdown", {}, retry=False)
                self._logger.log_event("shutdown_requested")
        except Exception:
            pass
        finally:
            await self.disconnect()

    # ------------------------------------------------------------ discovery

    async def discover(self) -> MCPServerInfo:
        return await self._discovery.discover()

    # ------------------------------------------------------------ tools

    async def list_tools(self) -> list[MCPTool]:
        raw = await self._discovery.list_tools()
        return [MCPTool.from_dict(t) for t in raw]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> MCPCallResult:
        t0 = time.perf_counter()
        try:
            result = await self._session.request(
                "tools/call",
                {"name": name, "arguments": arguments or {}},
                timeout=timeout,
            )
            if not isinstance(result, dict):
                raise MCPToolError(f"tools/call returned an unexpected payload for {name!r}")
            call_result = MCPCallResult(
                tool_name=name,
                content=list(result.get("content", [])),
                is_error=bool(result.get("isError", False)),
                structured_content=dict(result.get("structuredContent", {})),
            )
            latency = (time.perf_counter() - t0) * 1000
            self._metrics.record_tool_call(latency)
            self._logger.log_event(
                "tool_called", tool=name, is_error=call_result.is_error,
                latency_ms=round(latency, 4),
            )
            if call_result.is_error:
                self._metrics.record_error()
            return call_result
        except MCPError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MCPToolError(f"Tool call {name!r} failed: {e}") from e

    async def batch_call(
        self,
        calls: list[dict[str, Any]],
        timeout: float | None = None,
    ) -> list[MCPCallResult]:
        if not calls:
            return []
        results: list[MCPCallResult] = []
        try:
            for chunk in self._chunk(calls, self._config.max_batch_size):
                batch = [
                    asyncio.create_task(self.call_tool(
                        str(c.get("name", "")),
                        dict(c.get("arguments", {})),
                        timeout,
                    ))
                    for c in chunk
                ]
                results.extend(await asyncio.gather(*batch))
            self._metrics.record_batch_call(len(results))
        except MCPError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MCPToolError(f"Batch tool call failed: {e}") from e
        return results

    @staticmethod
    def _chunk(items: list[Any], size: int) -> list[list[Any]]:
        return [items[i : i + size] for i in range(0, len(items), size)]

    async def stream_call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> AsyncIterator[MCPStreamEvent]:
        if not self.connected:
            raise MCPDisconnectedError("Client is not connected")
        request = JSONRPCRequest("tools/call", {"name": name, "arguments": arguments or {}})
        try:
            self._metrics.record_stream_call()
            async for event in self._transport.stream(request):
                event.tool_name = event.tool_name or name
                yield event
                if event.is_final:
                    break
        except MCPError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MCPToolError(f"Stream call {name!r} failed: {e}") from e

    # ------------------------------------------------------------ resources

    async def list_resources(self) -> list[MCPResource]:
        raw = await self._discovery.list_resources()
        self._metrics.record_resources_listed()
        return [MCPResource.from_dict(r) for r in raw]

    async def read_resource(self, uri: str) -> MCPResource:
        try:
            result = await self._session.request("resources/read", {"uri": uri})
        except MCPError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MCPResourceError(f"Resource read failed: {e}") from e
        contents = result.get("contents", []) if isinstance(result, dict) else []
        if not contents:
            raise MCPResourceError(f"Resource {uri!r} returned no contents")
        resource = MCPResource.from_dict(dict(contents[0]))
        if not resource.uri:
            resource.uri = uri
        self._metrics.record_resource_read()
        return resource

    async def watch_resource(
        self,
        uri: str,
        callback: Callable[[str, dict[str, Any]], Any],
    ) -> None:
        try:
            await self._session.request("resources/subscribe", {"uri": uri})
        except Exception as e:
            self._metrics.record_error()
            raise MCPResourceError(f"Resource subscription failed: {e}") from e
        self._watchers.setdefault(uri, []).append(callback)
        self._metrics.record_resource_watched()
        self._logger.log_event("resource_watched", uri=uri)

    async def unwatch_resource(self, uri: str) -> None:
        self._watchers.pop(uri, None)
        try:
            await self._session.request("resources/unsubscribe", {"uri": uri})
        except Exception as e:
            self._metrics.record_error()
            raise MCPResourceError(f"Resource unsubscription failed: {e}") from e
        self._logger.log_event("resource_unwatched", uri=uri)

    def _start_notification_loop(self) -> None:
        if self._notification_task is None or self._notification_task.done():
            self._notification_task = asyncio.create_task(self._notification_loop())

    async def _notification_loop(self) -> None:
        try:
            async for message in self._transport.notifications():
                await self._dispatch_notification(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _dispatch_notification(self, message: dict[str, Any]) -> None:
        method = message.get("method", "")
        params = message.get("params", {}) or {}
        if method == "notifications/resources/updated":
            uri = str(params.get("uri", ""))
            for callback in list(self._watchers.get(uri, [])):
                try:
                    result = callback(uri, params)
                    if hasattr(result, "__await__"):
                        await result
                except Exception:
                    pass
            self._logger.log_event("resource_updated", uri=uri)

    # ------------------------------------------------------------ prompts

    async def list_prompts(self) -> list[MCPPrompt]:
        raw = await self._discovery.list_prompts()
        self._metrics.record_prompts_listed()
        return [MCPPrompt.from_dict(p) for p in raw]

    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPRenderedPrompt:
        try:
            result = await self._session.request(
                "prompts/get",
                {"name": name, "arguments": arguments or {}},
            )
        except MCPError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MCPPromptError(f"Prompt get failed: {e}") from e
        if not isinstance(result, dict):
            raise MCPPromptError(f"prompts/get returned an unexpected payload for {name!r}")
        prompt = MCPRenderedPrompt.from_dict(result)
        self._metrics.record_prompt_rendered()
        return prompt

    async def render_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        prompt = await self.get_prompt(name, arguments)
        return self._render_messages(prompt)

    @staticmethod
    def _render_messages(prompt: MCPRenderedPrompt) -> str:
        parts: list[str] = []
        for message in prompt.messages:
            content = message.content
            if isinstance(content, dict):
                if content.get("type") == "text":
                    parts.append(str(content.get("text", "")))
                elif "text" in content:
                    parts.append(str(content["text"]))
                else:
                    parts.append(str(content))
            else:
                parts.append(str(content))
        return "\n".join(parts)

    # ------------------------------------------------------------ health

    async def health(self) -> MCPConnectionHealth:
        latency = 0.0
        error = ""
        if self.connected:
            try:
                latency = await self.ping()
            except Exception as e:
                error = str(e)
        return MCPConnectionHealth(
            name=self._config.client_name,
            connected=self.connected,
            state=self.state,
            latency_ms=latency,
            last_error=error or self._session.last_error,
            tool_count=len(self._discovery.tools),
            resource_count=len(self._discovery.resources),
            prompt_count=len(self._discovery.prompts),
        )

    def get_metrics(self) -> Any:
        return self._metrics.get_metrics()

    # ------------------------------------------------------------ events

    def _handle_session_event(self, event: str, data: dict[str, Any]) -> None:
        if event == "heartbeat":
            self._metrics.record_heartbeat()
        elif event == "heartbeat_failed":
            self._metrics.record_heartbeat_failure()
        elif event == "reconnected":
            self._metrics.record_reconnect()
        elif event == "connected":
            self._connected = True
        elif event == "disconnected":
            self._connected = False
