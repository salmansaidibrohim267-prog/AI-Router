from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Protocol

import httpx

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore[assignment]

from app.mcp.auth import Authenticator, NoAuth
from app.mcp.config import MCPConfig
from app.mcp.exceptions import (
    MCPConnectionError,
    MCPProtocolError,
    MCPRPCError,
    MCPTransportError,
)
from app.mcp.models import (
    MCPStreamEvent,
    MCPTransportType,
)
from app.mcp.protocol import JSONRPCRequest, JSONRPCResponse, parse_message


class MCPTransport(Protocol):
    name: str
    transport_type: MCPTransportType

    @property
    def connected(self) -> bool:  # pragma: no cover
        ...

    async def connect(self) -> None:  # pragma: no cover
        ...

    async def disconnect(self) -> None:  # pragma: no cover
        ...

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:  # pragma: no cover
        ...

    async def send_batch(self, requests: list[JSONRPCRequest]) -> list[JSONRPCResponse]:  # pragma: no cover
        ...

    def stream(self, request: JSONRPCRequest) -> AsyncIterator[MCPStreamEvent]:  # pragma: no cover
        ...

    def notifications(self) -> AsyncIterator[dict[str, Any]]:  # pragma: no cover
        ...


class BaseTransport:
    def __init__(
        self,
        config: MCPConfig | None = None,
        authenticator: Authenticator | None = None,
    ):
        self._config = config or MCPConfig()
        self._auth = authenticator or NoAuth()
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def _headers(self) -> dict[str, str]:
        return self._auth.apply_headers(
            {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        )

    async def send_batch(self, requests: list[JSONRPCRequest]) -> list[JSONRPCResponse]:
        return [await self.send(r) for r in requests]


class StdioTransport(BaseTransport):
    name = "stdio"
    transport_type = MCPTransportType.STDIO

    def __init__(
        self,
        config: MCPConfig | None = None,
        authenticator: Authenticator | None = None,
        process: Any | None = None,
    ):
        super().__init__(config, authenticator)
        self._process = process
        self._owns_process = process is None

    async def connect(self) -> None:
        if self._connected:
            return
        if self._process is None:
            if not self._config.command:
                raise MCPConnectionError("Stdio transport requires a command")
            env = None
            if self._config.env:
                env = {**self._auth_headers_as_env(), **self._config.env}
            self._process = await asyncio.create_subprocess_exec(
                self._config.command,
                *self._config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise MCPConnectionError("Stdio process did not provide stdio pipes")
        self._connected = True

    def _auth_headers_as_env(self) -> dict[str, str]:
        return {k: v for k, v in self._headers().items() if k not in ("Content-Type", "Accept")}

    async def disconnect(self) -> None:
        if not self._connected and self._process is None:
            return
        if self._process is not None:
            try:
                self._process.stdin.close()  # type: ignore[union-attr]
            except Exception:
                pass
            if self._owns_process:
                try:
                    self._process.terminate()
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except (asyncio.TimeoutError, ProcessLookupError):
                    try:
                        self._process.kill()
                    except Exception:
                        pass
        self._connected = False

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._connected or self._process is None:
            raise MCPConnectionError("Stdio transport is not connected")
        try:
            self._process.stdin.write((request.to_json() + "\n").encode())  # type: ignore[union-attr]
            await self._process.stdin.drain()  # type: ignore[union-attr]
            raw = await self._process.stdout.readline()  # type: ignore[union-attr]
        except Exception as e:
            raise MCPTransportError(f"Stdio send failed: {e}") from e
        if not raw:
            raise MCPTransportError("Stdio transport closed by server")
        response = parse_message(raw)
        if response.id != request.id:
            raise MCPProtocolError(f"Response id {response.id} does not match request id {request.id}")
        return response

    async def stream(self, request: JSONRPCRequest) -> AsyncIterator[MCPStreamEvent]:
        response = await self.send(request)
        if response.ok:
            yield MCPStreamEvent(
                event_type="result",
                data={"result": response.result, "text": json.dumps(response.result)},
                is_final=True,
            )
        else:
            yield MCPStreamEvent(
                event_type="error",
                data={"error": response.error},
                is_final=True,
            )

    async def notifications(self) -> AsyncIterator[dict[str, Any]]:
        return
        yield {}  # pragma: no cover


class HTTPTransport(BaseTransport):
    name = "http"
    transport_type = MCPTransportType.HTTP

    def __init__(
        self,
        config: MCPConfig | None = None,
        authenticator: Authenticator | None = None,
        client: Any | None = None,
    ):
        super().__init__(config, authenticator)
        self._client = client

    async def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._config.request_timeout)
        return self._client

    async def connect(self) -> None:
        if self._connected:
            return
        if not self._config.url:
            raise MCPConnectionError("HTTP transport requires a URL")
        await self._ensure_client()
        self._connected = True

    async def disconnect(self) -> None:
        if self._client is not None and getattr(self._client, "is_closed", True) is False:
            try:
                await self._client.aclose()
            except Exception:
                pass
        self._client = None
        self._connected = False

    async def _post(self, payload: dict[str, Any]) -> Any:
        client = await self._ensure_client()
        try:
            response = await client.post(self._config.url, json=payload, headers=self._headers())
        except Exception as e:
            raise MCPTransportError(f"HTTP request failed: {e}") from e
        if response.status_code >= 400:
            raise MCPRPCError(
                code=response.status_code,
                message=f"HTTP {response.status_code}: {response.text[:200]}",
            )
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return response
        try:
            return response.json()
        except Exception as e:
            raise MCPProtocolError(f"Invalid JSON in HTTP response: {e}") from e

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._connected:
            raise MCPConnectionError("HTTP transport is not connected")
        body = await self._post(request.to_dict())
        if isinstance(body, dict):
            return parse_message(body)
        lines = [line async for line in body.aiter_lines()]
        parsed = await self._parse_sse(lines)
        if not parsed:
            raise MCPProtocolError("Empty SSE response from HTTP transport")
        return parsed[0]

    async def _parse_sse(self, lines: list[str]) -> list[JSONRPCResponse]:
        responses: list[JSONRPCResponse] = []
        data_lines: list[str] = []
        for line in lines:
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line.strip() == "" and data_lines:
                payload = "\n".join(data_lines)
                data_lines = []
                if payload == "[DONE]":
                    break
                try:
                    responses.append(parse_message(json.loads(payload)))
                except (json.JSONDecodeError, MCPProtocolError):
                    continue
        return responses

    async def stream(self, request: JSONRPCRequest) -> AsyncIterator[MCPStreamEvent]:
        body = await self._post(request.to_dict())
        if isinstance(body, dict):
            response = parse_message(body)
            if response.ok:
                yield MCPStreamEvent(
                    event_type="result",
                    data={"result": response.result, "text": json.dumps(response.result)},
                    is_final=True,
                )
            else:
                yield MCPStreamEvent(event_type="error", data={"error": response.error}, is_final=True)
            return
        lines = [line async for line in body.aiter_lines()]
        responses = await self._parse_sse(lines)
        for response in responses:
            if response.ok:
                yield MCPStreamEvent(
                    event_type="result",
                    data={"result": response.result, "text": json.dumps(response.result)},
                    is_final=True,
                )
            else:
                yield MCPStreamEvent(event_type="error", data={"error": response.error}, is_final=True)
        if not responses:
            yield MCPStreamEvent(event_type="error", data={"error": {"message": "No SSE events"}}, is_final=True)

    async def notifications(self) -> AsyncIterator[dict[str, Any]]:
        return
        yield {}  # pragma: no cover


class WebSocketTransport(BaseTransport):
    name = "websocket"
    transport_type = MCPTransportType.WEBSOCKET

    def __init__(
        self,
        config: MCPConfig | None = None,
        authenticator: Authenticator | None = None,
        websocket: Any | None = None,
    ):
        super().__init__(config, authenticator)
        self._ws = websocket
        self._owns_ws = True

    async def connect(self) -> None:
        if self._connected:
            return
        if self._ws is None:
            if not self._config.url:
                raise MCPConnectionError("WebSocket transport requires a URL")
            if websockets is None:
                raise MCPConnectionError(
                    "WebSocket transport requires the 'websockets' package or an injected websocket"
                )
            try:
                self._ws = await websockets.connect(
                    self._config.url,
                    additional_headers=self._headers(),
                )
            except Exception as e:
                raise MCPConnectionError(f"WebSocket connect failed: {e}") from e
        self._connected = True

    async def disconnect(self) -> None:
        if self._ws is not None and self._owns_ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        self._connected = False

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._connected or self._ws is None:
            raise MCPConnectionError("WebSocket transport is not connected")
        try:
            await self._ws.send(request.to_json())
            raw = await self._ws.recv()
        except Exception as e:
            raise MCPTransportError(f"WebSocket send failed: {e}") from e
        response = parse_message(raw)
        if response.id != request.id:
            raise MCPProtocolError(f"Response id {response.id} does not match request id {request.id}")
        return response

    async def stream(self, request: JSONRPCRequest) -> AsyncIterator[MCPStreamEvent]:
        if not self._connected or self._ws is None:
            raise MCPConnectionError("WebSocket transport is not connected")
        try:
            await self._ws.send(request.to_json())
            while True:
                raw = await self._ws.recv()
                message = parse_message(raw)
                if message.id != request.id:
                    if message.ok and isinstance(message.result, dict):
                        yield MCPStreamEvent(
                            event_type="delta",
                            tool_name=str(message.result.get("tool", "")),
                            data=message.result,
                        )
                    continue
                if message.ok:
                    yield MCPStreamEvent(
                        event_type="result",
                        data={"result": message.result, "text": json.dumps(message.result)},
                        is_final=True,
                    )
                else:
                    yield MCPStreamEvent(event_type="error", data={"error": message.error}, is_final=True)
                return
        except Exception as e:
            raise MCPTransportError(f"WebSocket stream failed: {e}") from e

    async def notifications(self) -> AsyncIterator[dict[str, Any]]:
        if not self._connected or self._ws is None:
            return
        while True:
            try:
                raw = await self._ws.recv()
            except Exception:
                return
            try:
                message = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(message, dict) and message.get("jsonrpc") == "2.0" and "method" in message:
                yield message
            elif isinstance(message, dict) and "id" in message:
                continue


class SSETransport(BaseTransport):
    name = "sse"
    transport_type = MCPTransportType.SSE

    def __init__(
        self,
        config: MCPConfig | None = None,
        authenticator: Authenticator | None = None,
        client: Any | None = None,
    ):
        super().__init__(config, authenticator)
        self._client = client
        self._notification_stream: Any | None = None

    async def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._config.request_timeout)
        return self._client

    async def connect(self) -> None:
        if self._connected:
            return
        if not self._config.url:
            raise MCPConnectionError("SSE transport requires a URL")
        await self._ensure_client()
        self._connected = True

    async def disconnect(self) -> None:
        if self._client is not None and getattr(self._client, "is_closed", True) is False:
            try:
                await self._client.aclose()
            except Exception:
                pass
        self._client = None
        self._notification_stream = None
        self._connected = False

    async def _post(self, payload: dict[str, Any]) -> Any:
        client = await self._ensure_client()
        try:
            response = await client.post(self._config.url, json=payload, headers=self._headers())
        except Exception as e:
            raise MCPTransportError(f"SSE request failed: {e}") from e
        if response.status_code >= 400:
            raise MCPRPCError(
                code=response.status_code,
                message=f"HTTP {response.status_code}: {response.text[:200]}",
            )
        return response

    async def _parse_sse_lines(self, lines: list[str]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        data_lines: list[str] = []
        for line in lines:
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line.strip() == "" and data_lines:
                payload = "\n".join(data_lines)
                data_lines = []
                if payload == "[DONE]":
                    break
                try:
                    events.append(json.loads(payload))
                except json.JSONDecodeError:
                    continue
        return events

    async def send(self, request: JSONRPCRequest) -> JSONRPCResponse:
        if not self._connected:
            raise MCPConnectionError("SSE transport is not connected")
        response = await self._post(request.to_dict())
        lines = [line async for line in response.aiter_lines()]
        events = await self._parse_sse_lines(lines)
        for event in events:
            if event.get("id") == request.id:
                return parse_message(event)
        raise MCPProtocolError("SSE response did not contain a matching message id")

    async def stream(self, request: JSONRPCRequest) -> AsyncIterator[MCPStreamEvent]:
        response = await self._post(request.to_dict())
        lines = [line async for line in response.aiter_lines()]
        events = await self._parse_sse_lines(lines)
        for event in events:
            if event.get("id") != request.id:
                continue
            message = parse_message(event)
            if message.ok:
                yield MCPStreamEvent(
                    event_type="result",
                    data={"result": message.result, "text": json.dumps(message.result)},
                    is_final=True,
                )
            else:
                yield MCPStreamEvent(event_type="error", data={"error": message.error}, is_final=True)
            return
        yield MCPStreamEvent(event_type="error", data={"error": {"message": "No SSE events"}}, is_final=True)

    async def notifications(self) -> AsyncIterator[dict[str, Any]]:
        client = await self._ensure_client()
        try:
            async with client.stream("GET", self._config.url, headers=self._headers()) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        try:
                            message = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(message, dict) and message.get("method"):
                            yield message
        except Exception:
            return


class TransportFactory:
    def create(
        self,
        config: MCPConfig | None = None,
        authenticator: Authenticator | None = None,
        **kwargs: Any,
    ) -> MCPTransport:
        config = config or MCPConfig()
        transport = config.transport
        if transport == MCPTransportType.STDIO.value or transport == "stdio":
            return StdioTransport(config, authenticator, **kwargs)
        if transport == MCPTransportType.HTTP.value or transport == "http":
            return HTTPTransport(config, authenticator, **kwargs)
        if transport == MCPTransportType.WEBSOCKET.value or transport == "websocket":
            return WebSocketTransport(config, authenticator, **kwargs)
        if transport == MCPTransportType.SSE.value or transport == "sse":
            return SSETransport(config, authenticator, **kwargs)
        raise MCPTransportError(f"Unsupported transport: {transport}")

    def names(self) -> list[str]:
        return [t.value for t in MCPTransportType]
