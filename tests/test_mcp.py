from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp import (
    ConnectionManager,
    MCPClient,
    MCPConfig,
    create_connection_manager,
    create_mcp_client,
)
from app.mcp.auth import (
    APIKeyAuth,
    AuthFactory,
    BearerTokenAuth,
    CustomHeadersAuth,
    NoAuth,
    OAuth2Auth,
)
from app.mcp.client import MCPClient as ClientCls
from app.mcp.discovery import ServerDiscovery
from app.mcp.exceptions import (
    MCPAuthError,
    MCPConnectionError,
    MCPDisconnectedError,
    MCPError,
    MCPManagerError,
    MCPPromptError,
    MCPProtocolError,
    MCPRPCError,
    MCPResourceError,
    MCPTimeoutError,
    MCPToolError,
    MCPTransportError,
)
from app.mcp.logging import MCPLogger
from app.mcp.manager import ConnectionManager as ManagerCls
from app.mcp.models import (
    MCPAuthType,
    MCPCallResult,
    MCPCapabilities,
    MCPConnectionHealth,
    MCPConnectionState,
    MCPEventType,
    MCPMetrics,
    MCPPrompt,
    MCPPromptMessage,
    MCPRenderedPrompt,
    MCPResource,
    MCPStreamEvent,
    MCPServerInfo,
    MCPTool,
    MCPTransportType,
)
from app.mcp.protocol import (
    IDGenerator,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    build_request,
    parse_message,
)
from app.mcp.session import MCPSession
from app.mcp.statistics import MCPMetricsTracker
from app.mcp.transports import (
    BaseTransport,
    HTTPTransport,
    SSETransport,
    StdioTransport,
    TransportFactory,
    WebSocketTransport,
)


def make_config(**kw) -> MCPConfig:
    defaults = dict(command="fake-server", url="http://localhost:8080/mcp")
    defaults.update(kw)
    return MCPConfig(**defaults)


def make_client(transport=None, config=None, **kw) -> MCPClient:
    return MCPClient(transport=transport or FakeTransport(), config=config or make_config(), **kw)


class FakeTransport:
    name = "fake"
    transport_type = MCPTransportType.STDIO

    def __init__(self):
        self._connected = False
        self.requests: list[JSONRPCRequest] = []
        self.responses: dict[str, JSONRPCResponse] = {}
        self.notification_messages: list[dict] = []
        self.stream_events: list[MCPStreamEvent] = []

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self):
        self._connected = True

    async def disconnect(self):
        self._connected = False

    def on(self, method: str, result, error=None):
        self.responses[method] = JSONRPCResponse(1, result, error)
        return self

    def default_response(self):
        return JSONRPCResponse(1, {})

    async def send(self, req: JSONRPCRequest) -> JSONRPCResponse:
        self.requests.append(req)
        resp = self.responses.get(req.method, self.default_response())
        resp.id = req.id
        return resp

    async def send_batch(self, reqs):
        return [await self.send(r) for r in reqs]

    async def stream(self, req):
        for event in self.stream_events:
            yield event

    async def notifications(self):
        for message in self.notification_messages:
            yield message


# ============================================================
# Config
# ============================================================
class TestConfig:
    def test_defaults(self):
        c = MCPConfig()
        assert c.transport == "stdio"
        assert c.timeout == 30.0
        assert c.args == []
        assert c.env == {}
        assert c.custom_headers == {}
        assert c.protocol_version == "2025-03-26"
        assert c.reconnect_enabled is True
        assert c.retry_enabled is True

    def test_from_env(self):
        os.environ["MCP_TRANSPORT"] = "http"
        os.environ["MCP_URL"] = "http://x"
        os.environ["MCP_ARGS"] = "a,b,c"
        os.environ["MCP_AUTH_TYPE"] = "bearer"
        os.environ["MCP_BEARER_TOKEN"] = "tok"
        os.environ["MCP_CUSTOM_HEADER_X_EXTRA"] = "1"
        os.environ["MCP_RECONNECT_ENABLED"] = "0"
        try:
            c = MCPConfig.from_env()
            assert c.transport == "http"
            assert c.args == ["a", "b", "c"]
            assert c.auth_type == "bearer"
            assert c.bearer_token == "tok"
            assert c.custom_headers == {"X-Extra": "1"}
            assert c.reconnect_enabled is False
        finally:
            for k in ("MCP_TRANSPORT", "MCP_URL", "MCP_ARGS", "MCP_AUTH_TYPE",
                      "MCP_BEARER_TOKEN", "MCP_CUSTOM_HEADER_X_EXTRA", "MCP_RECONNECT_ENABLED"):
                os.environ.pop(k, None)


# ============================================================
# Protocol
# ============================================================
class TestProtocol:
    def test_request_build(self):
        r = build_request("tools/list", {"a": 1}, request_id=7)
        assert r.to_dict() == {"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {"a": 1}}
        assert r.to_json() == json.dumps(r.to_dict())

    def test_request_default_id(self):
        r = JSONRPCRequest("ping")
        assert r.id == 1
        assert r.params == {}

    def test_response_ok(self):
        r = JSONRPCResponse(1, {"x": 1})
        assert r.ok is True
        assert r.raise_for_error() == {"x": 1}
        assert r.to_dict() == {"jsonrpc": "2.0", "id": 1, "result": {"x": 1}}

    def test_response_error(self):
        r = JSONRPCResponse(1, error={"code": -32601, "message": "nope"})
        assert r.ok is False
        with pytest.raises(MCPRPCError) as exc:
            r.raise_for_error()
        assert exc.value.code == -32601
        assert "nope" in str(exc.value)
        assert exc.value.data == {}

    def test_response_error_data(self):
        r = JSONRPCResponse(1, error={"code": 1, "message": "x", "data": {"k": "v"}})
        assert r.to_dict()["error"]["data"] == {"k": "v"}
        with pytest.raises(MCPRPCError):
            r.raise_for_error()

    def test_response_from_dict_from_json(self):
        r = JSONRPCResponse.from_dict({"id": 2, "result": 1, "jsonrpc": "2.0"})
        assert r.id == 2 and r.result == 1
        r2 = JSONRPCResponse.from_json('{"id":3,"result":null,"jsonrpc":"2.0"}')
        assert r2.id == 3

    def test_parse_invalid_json(self):
        with pytest.raises(MCPProtocolError):
            JSONRPCResponse.from_json("not json")

    def test_parse_wrong_version(self):
        with pytest.raises(MCPProtocolError):
            JSONRPCResponse.from_json('{"jsonrpc":"1.0","id":1,"result":1}')

    def test_parse_message_types(self):
        assert parse_message(b'{"jsonrpc":"2.0","id":1,"result":1}').result == 1
        assert parse_message({"id": 1, "result": 2, "jsonrpc": "2.0"}).result == 2
        with pytest.raises(MCPProtocolError):
            parse_message(42)

    def test_notification(self):
        n = JSONRPCNotification("notifications/updated", {"u": 1})
        assert n.to_dict() == {"jsonrpc": "2.0", "method": "notifications/updated", "params": {"u": 1}}
        assert n.to_json()

    def test_id_generator(self):
        g = IDGenerator(10)
        assert [g.next() for _ in range(3)] == [10, 11, 12]
        assert IDGenerator().next() == 1


# ============================================================
# Models
# ============================================================
class TestModels:
    def test_tool_roundtrip(self):
        t = MCPTool.from_dict({"name": "sum", "description": "d",
                               "inputSchema": {"type": "object"}, "annotations": {"a": 1}})
        assert t.name == "sum"
        assert t.input_schema == {"type": "object"}
        d = t.to_dict()
        assert d["name"] == "sum"

    def test_tool_from_dict_snake_case(self):
        t = MCPTool.from_dict({"name": "x", "input_schema": {"t": "o"}})
        assert t.input_schema == {"t": "o"}

    def test_resource_roundtrip(self):
        r = MCPResource.from_dict({"uri": "doc://1", "name": "n",
                                   "mimeType": "text/markdown", "text": "body", "metadata": {"a": 1}})
        assert r.uri == "doc://1"
        assert r.mime_type == "text/markdown"
        assert r.to_dict()["text"] == "body"
        assert r.to_dict()["mime_type"] == "text/markdown"

    def test_resource_defaults(self):
        r = MCPResource.from_dict({})
        assert r.mime_type == "text/plain"
        assert r.text == ""

    def test_prompt_roundtrip(self):
        p = MCPPrompt.from_dict({"name": "greet", "description": "d",
                                 "arguments": [{"name": "who"}]})
        assert p.name == "greet"
        assert p.arguments == [{"name": "who"}]
        assert p.to_dict()["name"] == "greet"

    def test_rendered_prompt_roundtrip(self):
        rp = MCPRenderedPrompt.from_dict({
            "name": "greet",
            "messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}],
        })
        assert len(rp.messages) == 1
        assert rp.messages[0].role == "user"
        assert rp.to_dict()["messages"][0]["role"] == "user"

    def test_prompt_message(self):
        m = MCPPromptMessage()
        assert m.role == "user"
        assert m.to_dict() == {"role": "user", "content": {}}

    def test_capabilities(self):
        c = MCPCapabilities.from_dict({"tools": 1, "streaming": True})
        assert c.tools is True
        assert c.streaming is True
        assert c.resources is False
        assert c.to_dict()["logging"] is False

    def test_server_info_to_dict(self):
        info = MCPServerInfo(server_name="s", capabilities=MCPCapabilities(tools=True))
        d = info.to_dict()
        assert d["server_name"] == "s"
        assert d["capabilities"]["tools"] is True

    def test_call_result_text(self):
        r = MCPCallResult(tool_name="t", content=[
            {"type": "text", "text": "hello"},
            {"text": " world"},
            "plain",
            {"type": "image", "data": "x"},
        ])
        assert r.text == "hello world\nplain"
        assert r.to_dict()["tool_name"] == "t"

    def test_call_result_empty(self):
        assert MCPCallResult(tool_name="t").text == ""

    def test_stream_event_text(self):
        e = MCPStreamEvent(event_type="delta", data={"text": "abc"})
        assert e.text == "abc"
        assert MCPStreamEvent(event_type="x").text == ""

    def test_health_to_dict(self):
        h = MCPConnectionHealth(name="s", connected=True, tool_count=2)
        d = h.to_dict()
        assert d["connected"] is True
        assert d["state"] == "disconnected"
        assert d["tool_count"] == 2

    def test_metrics_to_dict(self):
        m = MCPMetrics(total_pings=3)
        d = m.to_dict()
        assert d["total_pings"] == 3
        assert "heartbeat_failures" in d


# ============================================================
# Auth
# ============================================================
class TestAuth:
    def test_no_auth(self):
        a = NoAuth()
        assert a.apply_headers({"a": "1"}) == {"a": "1"}
        assert a.apply_request({"m": 1}) == {"m": 1}
        assert a.name == "none"

    def test_api_key(self):
        a = APIKeyAuth("k123", "X-Key")
        headers = a.apply_headers({})
        assert headers["X-Key"] == "k123"
        assert a.apply_request({"m": 1}) == {"m": 1}

    def test_bearer(self):
        a = BearerTokenAuth("tok")
        assert a.apply_headers({})["Authorization"] == "Bearer tok"
        assert a.apply_request({"m": 1}) == {"m": 1}

    def test_custom_headers(self):
        a = CustomHeadersAuth({"X-1": "a", "X-2": "b"})
        headers = a.apply_headers({"X-0": "z"})
        assert headers == {"X-0": "z", "X-1": "a", "X-2": "b"}
        assert a.apply_request({"m": 1}) == {"m": 1}

    def test_oauth2_static_token(self):
        a = OAuth2Auth(token="static")
        assert a.apply_headers({})["Authorization"] == "Bearer static"
        assert a.apply_request({"m": 1}) == {"m": 1}
        assert asyncio.run(a.acquire_token()) == "static"

    def test_oauth2_acquire_no_token_url(self):
        a = OAuth2Auth()
        with pytest.raises(MCPAuthError):
            asyncio.run(a.acquire_token())

    def test_oauth2_acquire_http_error(self):
        a = OAuth2Auth(client_id="c", client_secret="s", token_url="https://t")
        client = MagicMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=MagicMock(status_code=401))
        with patch("app.mcp.auth.httpx.AsyncClient", return_value=client):
            with pytest.raises(MCPAuthError):
                asyncio.run(a.acquire_token())

    def test_oauth2_acquire_missing_token(self):
        a = OAuth2Auth(client_id="c", client_secret="s", token_url="https://t")
        client = MagicMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=MagicMock(status_code=200, json=lambda: {}))
        with patch("app.mcp.auth.httpx.AsyncClient", return_value=client):
            with pytest.raises(MCPAuthError):
                asyncio.run(a.acquire_token())

    def test_oauth2_acquire_success(self):
        a = OAuth2Auth(client_id="c", client_secret="s", token_url="https://t")
        client = MagicMock()
        client.__aenter__.return_value = client
        client.post = AsyncMock(return_value=MagicMock(status_code=200,
                                                       json=lambda: {"access_token": "t1"}))
        with patch("app.mcp.auth.httpx.AsyncClient", return_value=client):
            assert asyncio.run(a.acquire_token()) == "t1"

    def test_factory_all_types(self):
        f = AuthFactory()
        cfg = make_config(auth_type="api_key", api_key="k", bearer_token="b",
                          oauth2_token="o", custom_headers={"H": "v"})
        assert isinstance(f.create("none"), NoAuth)
        assert isinstance(f.create(MCPAuthType.API_KEY, cfg), APIKeyAuth)
        assert isinstance(f.create("bearer", cfg), BearerTokenAuth)
        assert isinstance(f.create("oauth2", cfg), OAuth2Auth)
        assert isinstance(f.create("custom_headers", cfg), CustomHeadersAuth)
        with pytest.raises(MCPAuthError):
            f.create("bogus")

    def test_factory_names(self):
        assert set(AuthFactory().names()) == {t.value for t in MCPAuthType}

    def test_auth_factory_uses_config(self):
        f = AuthFactory()
        a = f.create("api_key", make_config(api_key="abc"))
        assert a.apply_headers({})["X-API-Key"] == "abc"


# ============================================================
# Transports
# ============================================================
class TestStdioTransport:
    def test_connect_requires_command(self):
        t = StdioTransport(make_config(command=""))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.connect())

    def test_send_not_connected(self):
        t = StdioTransport(make_config(command="x"))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.send(JSONRPCRequest("ping")))

    def test_stream_not_connected(self):
        t = StdioTransport(make_config(command="x"))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.stream(JSONRPCRequest("ping")).__anext__())

    def test_connect_injected_process(self):
        proc = MagicMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        assert t.connected is True

    def test_connect_idempotent(self):
        proc = MagicMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        asyncio.run(t.connect())
        assert t.connected is True

    def test_disconnect_no_process(self):
        t = StdioTransport(make_config(command="x"))
        asyncio.run(t.disconnect())

    def test_send_with_injected_process(self):
        proc = MagicMock()
        reader = MagicMock()
        reader.readline = AsyncMock(return_value=b'{"jsonrpc":"2.0","id":1,"result":{}}\n')
        proc.stdout = reader
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        resp = asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))
        assert resp.ok is True
        proc.stdin.write.assert_called_once()

    def test_send_closed_pipe(self):
        proc = MagicMock()
        reader = MagicMock()
        reader.readline = AsyncMock(return_value=b"")
        proc.stdout = reader
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        with pytest.raises(MCPTransportError):
            asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))

    def test_send_write_error(self):
        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.readline = AsyncMock(return_value=b"{}")
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock(side_effect=RuntimeError("pipe broken"))
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        with pytest.raises(MCPTransportError):
            asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))

    def test_send_id_mismatch(self):
        proc = MagicMock()
        reader = MagicMock()
        reader.readline = AsyncMock(return_value=b'{"jsonrpc":"2.0","id":999,"result":{}}\n')
        proc.stdout = reader
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        with pytest.raises(MCPProtocolError):
            asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))

    def test_send_malformed_line(self):
        proc = MagicMock()
        reader = MagicMock()
        reader.readline = AsyncMock(return_value=b"garbage\n")
        proc.stdout = reader
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        with pytest.raises(MCPProtocolError):
            asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))

    def test_stream_ok(self):
        proc = MagicMock()
        reader = MagicMock()
        reader.readline = AsyncMock(return_value=b'{"jsonrpc":"2.0","id":1,"result":{"r":1}}\n')
        proc.stdout = reader
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())

        async def run():
            events = []
            async for e in t.stream(JSONRPCRequest("tools/call", request_id=1)):
                events.append(e)
            return events

        events = asyncio.run(run())
        assert events[0].is_final is True
        assert events[0].event_type == "result"

    def test_stream_error(self):
        proc = MagicMock()
        reader = MagicMock()
        reader.readline = AsyncMock(return_value=b'{"jsonrpc":"2.0","id":1,"error":{"code":1,"message":"e"}}\n')
        proc.stdout = reader
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        assert asyncio.run(run())[0].event_type == "error"

    def test_notifications_empty(self):
        t = StdioTransport(make_config(command="x"))

        async def run():
            return [m async for m in t.notifications()]

        assert asyncio.run(run()) == []

    def test_disconnect_injected_process(self):
        proc = MagicMock()
        proc.stdin = MagicMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())
        assert t.connected is False

    def test_disconnect_owns_process(self):
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        t = StdioTransport(make_config(command="x"), process=proc, owns_process=True) if False else None
        t = StdioTransport(make_config(command="x"), process=proc)
        t._owns_process = True
        asyncio.run(t.disconnect())
        assert t.connected is False

    def test_batch(self):
        proc = MagicMock()
        reader = MagicMock()
        reader.readline = AsyncMock(return_value=b'{"jsonrpc":"2.0","id":1,"result":{}}\n')
        proc.stdout = reader
        proc.stdin = MagicMock()
        proc.stdin.drain = AsyncMock()
        t = StdioTransport(make_config(command="x"), process=proc)
        asyncio.run(t.connect())
        resp = asyncio.run(t.send_batch([JSONRPCRequest("ping", request_id=1)]))
        assert len(resp) == 1

    def test_send_batch_not_connected(self):
        t = StdioTransport(make_config(command="x"))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.send_batch([JSONRPCRequest("ping")]))

    def test_auth_headers(self):
        t = StdioTransport(make_config(command="x"), authenticator=APIKeyAuth("k"))
        assert t._headers()["X-API-Key"] == "k"


class TestHTTPTransport:
    def make_transport(self, response=None, client=None, config=None,
                       status=200, content_type="application/json"):
        client = client or self.fake_client(response, status=status, content_type=content_type)
        return HTTPTransport(config or make_config(url="http://x"), client=client)

    def fake_client(self, response=None, status=200, content_type="application/json"):
        client = MagicMock()
        response = response if response is not None else {"jsonrpc": "2.0", "id": 1, "result": {"ok": 1}}
        resp = MagicMock()
        resp.status_code = status
        resp.headers = {"content-type": content_type}
        if isinstance(response, dict):
            resp.json.return_value = response
        else:
            resp.json.return_value = response
        resp.aiter_lines.return_value = _alist(response)
        resp.text = json.dumps(response)
        client.post = AsyncMock(return_value=resp)
        return client

    @staticmethod
    async def _noop(*args, **kwargs):
        return None

    def test_connect_requires_url(self):
        t = HTTPTransport(make_config(url=""))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.connect())

    def test_connect_success(self):
        t = HTTPTransport(make_config(url="http://x"), client=MagicMock())
        asyncio.run(t.connect())
        assert t.connected is True

    def test_send_not_connected(self):
        t = HTTPTransport(make_config(url="http://x"), client=MagicMock())
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.send(JSONRPCRequest("ping")))

    def test_send_ok(self):
        t = self.make_transport()
        asyncio.run(t.connect())
        resp = asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))
        assert resp.result == {"ok": 1}

    def test_send_http_error(self):
        t = self.make_transport(status=500)
        asyncio.run(t.connect())
        with pytest.raises(MCPRPCError):
            asyncio.run(t.send(JSONRPCRequest("ping")))

    def test_send_transport_failure(self):
        client = MagicMock()
        client.post = AsyncMock(side_effect=RuntimeError("conn refused"))
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        with pytest.raises(MCPTransportError):
            asyncio.run(t.send(JSONRPCRequest("ping")))

    def test_send_sse_response(self):
        sse_payload = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"r":1}}\n\n'
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/event-stream"}
        resp.aiter_lines.return_value = _alist(sse_payload.splitlines())
        client.post = AsyncMock(return_value=resp)
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        out = asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))
        assert out.result == {"r": 1}

    def test_send_sse_empty(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/event-stream"}
        resp.aiter_lines.return_value = _alist([])
        client.post = AsyncMock(return_value=resp)
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        with pytest.raises(MCPProtocolError):
            asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))

    def test_send_sse_done(self):
        lines = ['data: {"jsonrpc":"2.0","id":1,"result":{"r":1}}', "", "data: [DONE]", ""]
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/event-stream"}
        resp.aiter_lines.return_value = _alist(lines)
        client.post = AsyncMock(return_value=resp)
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        out = asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))
        assert out.result == {"r": 1}

    def test_send_sse_skips_bad_json(self):
        lines = ['data: notjson', "",
                 'data: {"jsonrpc":"2.0","id":1,"result":{"r":1}}', ""]
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/event-stream"}
        resp.aiter_lines.return_value = _alist(lines)
        client.post = AsyncMock(return_value=resp)
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        out = asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))
        assert out.result == {"r": 1}

    def test_send_invalid_json(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        resp.json.side_effect = ValueError("bad json")
        resp.text = "bad"
        client.post = AsyncMock(return_value=resp)
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        with pytest.raises(MCPProtocolError):
            asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))

    def test_stream_json_response(self):
        t = self.make_transport()
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        events = asyncio.run(run())
        assert events[0].event_type == "result" and events[0].is_final

    def test_stream_sse_multiple(self):
        lines = [
            'data: {"jsonrpc":"2.0","id":1,"result":{"a":1}}', "",
            'data: {"jsonrpc":"2.0","id":1,"result":{"b":2}}', "",
        ]
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/event-stream"}
        resp.aiter_lines.return_value = _alist(lines)
        client.post = AsyncMock(return_value=resp)
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        events = asyncio.run(run())
        assert len(events) == 2

    def test_stream_sse_none(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/event-stream"}
        resp.aiter_lines.return_value = _alist([])
        client.post = AsyncMock(return_value=resp)
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        assert asyncio.run(run())[0].event_type == "error"

    def test_stream_sse_error_event(self):
        lines = ['data: {"jsonrpc":"2.0","id":1,"error":{"code":1,"message":"e"}}', ""]
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "text/event-stream"}
        resp.aiter_lines.return_value = _alist(lines)
        client.post = AsyncMock(return_value=resp)
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        events = asyncio.run(run())
        assert events[0].event_type == "error"
        assert events[0].is_final

    def test_disconnect(self):
        client = MagicMock()
        client.is_closed = False
        client.aclose = AsyncMock()
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())
        client.aclose.assert_awaited_once()

    def test_disconnect_already_closed(self):
        client = MagicMock()
        client.is_closed = True
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())

    def test_disconnect_aclose_error(self):
        client = MagicMock()
        client.is_closed = False
        client.aclose = AsyncMock(side_effect=RuntimeError("boom"))
        t = HTTPTransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())
        assert t.connected is False

    def test_notifications_empty(self):
        t = HTTPTransport(make_config(url="http://x"), client=MagicMock())

        async def run():
            return [m async for m in t.notifications()]

        assert asyncio.run(run()) == []

    def test_ensure_client_creates(self):
        t = HTTPTransport(make_config(url="http://x"))
        with patch("app.mcp.transports.httpx.AsyncClient") as mc:
            asyncio.run(t._ensure_client())
            mc.assert_called_once()


class TestWebSocketTransport:
    def make_ws(self, replies):
        ws = MagicMock()
        ws.send = AsyncMock()
        replies = list(replies)
        ws.recv = AsyncMock(side_effect=replies)
        return ws

    def test_connect_requires_url(self):
        t = WebSocketTransport(make_config(url=""))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.connect())

    def test_connect_no_websockets_lib(self):
        t = WebSocketTransport(make_config(url="ws://x"))
        with patch("app.mcp.transports.websockets", None):
            with pytest.raises(MCPConnectionError):
                asyncio.run(t.connect())

    def test_connect_import_error(self):
        t = WebSocketTransport(make_config(url="ws://x"))
        with patch("app.mcp.transports.websockets", None):
            with pytest.raises(MCPConnectionError):
                asyncio.run(t.connect())

    def test_connect_success_injected(self):
        t = WebSocketTransport(make_config(url="ws://x"), websocket=MagicMock())
        asyncio.run(t.connect())
        assert t.connected

    def test_send_not_connected(self):
        t = WebSocketTransport(make_config(url="ws://x"))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.send(JSONRPCRequest("ping")))

    def test_send_ok(self):
        ws = self.make_ws(['{"jsonrpc":"2.0","id":1,"result":{"ok":1}}'])
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())
        resp = asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))
        assert resp.result == {"ok": 1}
        ws.send.assert_awaited_once()

    def test_send_id_mismatch(self):
        ws = self.make_ws(['{"jsonrpc":"2.0","id":7,"result":{}}'])
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())
        with pytest.raises(MCPProtocolError):
            asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))

    def test_send_failure(self):
        ws = MagicMock()
        ws.send = AsyncMock(side_effect=RuntimeError("socket closed"))
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())
        with pytest.raises(MCPTransportError):
            asyncio.run(t.send(JSONRPCRequest("ping")))

    def test_stream_delta_then_result(self):
        ws = self.make_ws([
            '{"jsonrpc":"2.0","id":99,"result":{"text":"delta1"}}',
            '{"jsonrpc":"2.0","id":1,"result":{"final":1}}',
        ])
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        events = asyncio.run(run())
        assert [e.event_type for e in events] == ["delta", "result"]
        assert events[1].is_final

    def test_stream_error(self):
        ws = self.make_ws(['{"jsonrpc":"2.0","id":1,"error":{"code":1,"message":"e"}}'])
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        assert asyncio.run(run())[0].event_type == "error"

    def test_stream_failure(self):
        ws = MagicMock()
        ws.send = AsyncMock(side_effect=RuntimeError("boom"))
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())
        with pytest.raises(MCPTransportError):
            asyncio.run(t.stream(JSONRPCRequest("tools/call")).__anext__())

    def test_notifications(self):
        ws = self.make_ws([
            '{"jsonrpc":"2.0","method":"notifications/resources/updated","params":{"uri":"u"}}',
            '{"jsonrpc":"2.0","id":1,"result":{}}',
            "garbage",
            '{"jsonrpc":"2.0","method":"another"}',
        ])
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())

        async def run():
            return [m async for m in t.notifications()]

        msgs = asyncio.run(run())
        assert len(msgs) == 2
        assert msgs[0]["method"] == "notifications/resources/updated"

    def test_notifications_not_connected(self):
        t = WebSocketTransport(make_config(url="ws://x"))

        async def run():
            return [m async for m in t.notifications()]

        assert asyncio.run(run()) == []

    def test_notifications_recv_error(self):
        ws = MagicMock()
        ws.recv = AsyncMock(side_effect=RuntimeError("closed"))
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())

        async def run():
            return [m async for m in t.notifications()]

        assert asyncio.run(run()) == []

    def test_disconnect_owned(self):
        ws = MagicMock()
        ws.close = AsyncMock()
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())
        ws.close.assert_awaited_once()

    def test_disconnect_close_error(self):
        ws = MagicMock()
        ws.close = AsyncMock(side_effect=RuntimeError("boom"))
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())
        assert t.connected is False

    def test_disconnect_injected(self):
        ws = MagicMock()
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        t._owns_ws = False
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())


class TestSSETransport:
    def test_connect_requires_url(self):
        t = SSETransport(make_config(url=""))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.connect())

    def test_send_not_connected(self):
        t = SSETransport(make_config(url="http://x"))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.send(JSONRPCRequest("ping")))

    def test_send_ok(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.aiter_lines.return_value = _alist(
            ['data: {"jsonrpc":"2.0","id":1,"result":{"ok":1}}', ""]
        )
        client.post = AsyncMock(return_value=resp)
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        out = asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))
        assert out.result == {"ok": 1}

    def test_send_no_matching_id(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.aiter_lines.return_value = _alist(
            ['data: {"jsonrpc":"2.0","id":9,"result":{"ok":1}}', ""]
        )
        client.post = AsyncMock(return_value=resp)
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        with pytest.raises(MCPProtocolError):
            asyncio.run(t.send(JSONRPCRequest("ping", request_id=1)))

    def test_send_http_error(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 404
        resp.text = "nope"
        client.post = AsyncMock(return_value=resp)
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        with pytest.raises(MCPRPCError):
            asyncio.run(t.send(JSONRPCRequest("ping")))

    def test_stream(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.aiter_lines.return_value = _alist(
            ['data: {"jsonrpc":"2.0","id":1,"result":{"ok":1}}', ""]
        )
        client.post = AsyncMock(return_value=resp)
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        events = asyncio.run(run())
        assert events[0].event_type == "result" and events[0].is_final

    def test_stream_none(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.aiter_lines.return_value = _alist([])
        client.post = AsyncMock(return_value=resp)
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        assert asyncio.run(run())[0].event_type == "error"

    def test_notifications(self):
        client = MagicMock()
        ctx = MagicMock()
        ctx.aiter_lines.return_value = _alist([
            'data: {"jsonrpc":"2.0","method":"notifications/resources/updated","params":{"uri":"u"}}',
            "data: [DONE]",
            "data: garbage",
        ])
        client.stream.return_value.__aenter__.return_value = ctx
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [m async for m in t.notifications()]

        msgs = asyncio.run(run())
        assert len(msgs) == 1
        assert msgs[0]["method"] == "notifications/resources/updated"

    def test_notifications_error(self):
        client = MagicMock()
        client.stream.side_effect = RuntimeError("boom")
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [m async for m in t.notifications()]

        assert asyncio.run(run()) == []

    def test_parse_sse_skip_bad_json(self):
        t = SSETransport(make_config(url="http://x"))
        events = asyncio.run(t._parse_sse_lines(["data: notjson", "", "data: {}", ""]))
        assert len(events) == 1

    def test_parse_sse_done(self):
        t = SSETransport(make_config(url="http://x"))
        events = asyncio.run(t._parse_sse_lines(
            ['data: {"a": 1}', "", "data: [DONE]", "", 'data: {"b": 2}', ""]
        ))
        assert events == [{"a": 1}]

    def test_disconnect(self):
        client = MagicMock()
        client.is_closed = False
        client.aclose = AsyncMock()
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())
        client.aclose.assert_awaited_once()

    def test_disconnect_aclose_error(self):
        client = MagicMock()
        client.is_closed = False
        client.aclose = AsyncMock(side_effect=RuntimeError("boom"))
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())
        assert t.connected is False

    def test_send_failure(self):
        client = MagicMock()
        client.post = AsyncMock(side_effect=RuntimeError("conn refused"))
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())
        with pytest.raises(MCPTransportError):
            asyncio.run(t.send(JSONRPCRequest("ping")))


class TestTransportFactory:
    def test_create_all(self):
        f = TransportFactory()
        assert isinstance(f.create(make_config(transport="stdio", command="x")), StdioTransport)
        assert isinstance(f.create(make_config(transport="http", url="http://x")), HTTPTransport)
        assert isinstance(f.create(make_config(transport="websocket", url="ws://x")), WebSocketTransport)
        assert isinstance(f.create(make_config(transport="sse", url="http://x")), SSETransport)

    def test_create_enum_value(self):
        f = TransportFactory()
        cfg = make_config(transport=MCPTransportType.HTTP.value, url="http://x")
        assert isinstance(f.create(cfg), HTTPTransport)

    def test_create_unknown(self):
        with pytest.raises(MCPTransportError):
            TransportFactory().create(make_config(transport="carrier-pigeon"))

    def test_names(self):
        assert set(TransportFactory().names()) == {t.value for t in MCPTransportType}

    def test_base_headers_with_auth(self):
        t = BaseTransport(make_config(), authenticator=APIKeyAuth("k"))
        headers = t._headers()
        assert headers["X-API-Key"] == "k"
        assert headers["Content-Type"] == "application/json"


def _alist(items):
    async def gen():
        for item in items:
            yield item

    return gen()


# ============================================================
# Discovery
# ============================================================
class TestDiscovery:
    def test_initialize(self):
        async def req(method, params, retry=True, timeout=None):
            return {
                "protocolVersion": "2025-03-26",
                "serverInfo": {"name": "srv", "version": "1.2.3"},
                "capabilities": {"tools": True, "logging": True},
                "instructions": "hi",
            }

        d = ServerDiscovery(req)
        info = asyncio.run(d.initialize())
        assert info.server_name == "srv"
        assert info.server_version == "1.2.3"
        assert info.protocol_version == "2025-03-26"
        assert info.capabilities.tools is True
        assert info.capabilities.logging is True
        assert info.instructions == "hi"
        assert info.discovered_at > 0
        assert d.server_info is info

    def test_initialize_params(self):
        seen = {}

        async def req(method, params, retry=True, timeout=None):
            seen.update(params=params, retry=retry)
            return {}

        d = ServerDiscovery(req, make_config(
            protocol_version="2025-04-12", client_name="mycli", client_version="9.9"
        ))
        asyncio.run(d.initialize())
        assert seen["params"]["protocolVersion"] == "2025-04-12"
        assert seen["params"]["clientInfo"] == {"name": "mycli", "version": "9.9"}
        assert seen["params"]["capabilities"] == {}
        assert seen["retry"] is False

    def test_initialize_non_dict(self):
        async def req(method, params, retry=True, timeout=None):
            return "nope"

        d = ServerDiscovery(req)
        with pytest.raises(MCPProtocolError):
            asyncio.run(d.initialize())

    def test_discover_caches(self):
        calls = {"n": 0}

        async def req(method, params, retry=True, timeout=None):
            calls["n"] += 1
            return {"serverInfo": {"name": "s"}}

        d = ServerDiscovery(req)
        a = asyncio.run(d.discover())
        b = asyncio.run(d.discover())
        assert a is b
        assert calls["n"] == 1
        assert a.server_name == "s"

    def test_discover_requires_initialize(self):
        d = ServerDiscovery(lambda *a, **k: {})

        async def noop():
            pass

        d.initialize = noop  # type: ignore[method-assign]
        with pytest.raises(MCPProtocolError):
            asyncio.run(d.discover())

    def test_list_tools(self):
        seen = {}

        async def req(method, params, retry=True, timeout=None):
            seen[method] = params
            return {"tools": [{"name": "a"}, {"name": "b"}]}

        d = ServerDiscovery(req)
        tools = asyncio.run(d.list_tools("cur"))
        assert [t["name"] for t in tools] == ["a", "b"]
        assert seen["tools/list"] == {"cursor": "cur"}
        assert d.tools == tools
        asyncio.run(d.list_tools())
        assert seen["tools/list"] == {}
        assert asyncio.run(d.list_tools()) is not d.tools

    def test_list_tools_non_dict(self):
        async def req(method, params, retry=True, timeout=None):
            return "nope"

        d = ServerDiscovery(req)
        assert asyncio.run(d.list_tools()) == []

    def test_list_resources(self):
        seen = {}

        async def req(method, params, retry=True, timeout=None):
            seen[method] = params
            return {"resources": [{"uri": "doc://1", "name": "r"}]}

        d = ServerDiscovery(req)
        resources = asyncio.run(d.list_resources("c"))
        assert resources[0]["uri"] == "doc://1"
        assert seen["resources/list"] == {"cursor": "c"}
        assert d.resources == resources
        asyncio.run(d.list_resources())
        assert seen["resources/list"] == {}

    def test_list_prompts(self):
        seen = {}

        async def req(method, params, retry=True, timeout=None):
            seen[method] = params
            return {"prompts": [{"name": "p"}]}

        d = ServerDiscovery(req)
        prompts = asyncio.run(d.list_prompts("c"))
        assert prompts[0]["name"] == "p"
        assert seen["prompts/list"] == {"cursor": "c"}
        assert d.prompts == prompts
        asyncio.run(d.list_prompts())
        assert seen["prompts/list"] == {}

    def test_clear(self):
        async def req(method, params, retry=True, timeout=None):
            return {
                "serverInfo": {"name": "s"},
                "tools": [{"name": "a"}],
                "resources": [{"uri": "u"}],
                "prompts": [{"name": "p"}],
            }

        d = ServerDiscovery(req)
        asyncio.run(d.initialize())
        asyncio.run(d.list_tools())
        asyncio.run(d.list_resources())
        asyncio.run(d.list_prompts())
        d.clear()
        assert d.server_info is None
        assert d.tools == []
        assert d.resources == []
        assert d.prompts == []


# ============================================================
# Session
# ============================================================
class CountingTransport(FakeTransport):
    def __init__(self):
        super().__init__()
        self.connect_calls = 0
        self.disconnect_calls = 0

    async def connect(self):
        self.connect_calls += 1
        await super().connect()

    async def disconnect(self):
        self.disconnect_calls += 1
        await super().disconnect()


class TestSession:
    def test_initial_state(self):
        s = MCPSession(FakeTransport())
        assert s.state == MCPConnectionState.DISCONNECTED
        assert s.connected is False
        assert s.last_error == ""

    def test_connect_success(self):
        events = []
        s = MCPSession(FakeTransport(), make_config(), lambda e, d: events.append(e))
        asyncio.run(s.connect())
        assert s.state == MCPConnectionState.CONNECTED
        assert s.connected is True
        assert "connected" in events

    def test_connect_timeout(self):
        class SlowTransport(FakeTransport):
            async def connect(self):
                await asyncio.sleep(10)

        s = MCPSession(SlowTransport(), make_config(connect_timeout=0.01))
        with pytest.raises(MCPTimeoutError):
            asyncio.run(s.connect())
        assert s.state == MCPConnectionState.ERROR
        assert s.last_error == "connect timeout"

    def test_connect_error(self):
        class BoomTransport(FakeTransport):
            async def connect(self):
                raise RuntimeError("boom")

        s = MCPSession(BoomTransport(), make_config())
        with pytest.raises(MCPConnectionError):
            asyncio.run(s.connect())
        assert s.state == MCPConnectionState.ERROR
        assert "boom" in s.last_error

    def test_connect_idempotent(self):
        t = CountingTransport()
        s = MCPSession(t, make_config())

        async def scenario():
            await s.connect()
            await s.connect()

        asyncio.run(scenario())
        assert t.connect_calls == 1

    def test_disconnect(self):
        t = CountingTransport()
        s = MCPSession(t, make_config())
        asyncio.run(s.connect())
        asyncio.run(s.disconnect())
        assert t.disconnect_calls == 1
        assert s.state == MCPConnectionState.DISCONNECTED
        assert s.connected is False

    def test_disconnect_not_connected(self):
        t = CountingTransport()
        s = MCPSession(t, make_config())
        asyncio.run(s.disconnect())
        assert t.disconnect_calls == 0
        assert s.state == MCPConnectionState.DISCONNECTED

    def test_disconnect_transport_error(self):
        class BadDisconnectTransport(FakeTransport):
            async def disconnect(self):
                raise RuntimeError("boom")

        s = MCPSession(BadDisconnectTransport(), make_config())
        asyncio.run(s.connect())
        asyncio.run(s.disconnect())
        assert s.state == MCPConnectionState.DISCONNECTED

    def test_ping(self):
        s = MCPSession(FakeTransport(), make_config())
        asyncio.run(s.connect())
        latency = asyncio.run(s.ping())
        assert isinstance(latency, float)
        assert latency >= 0
        asyncio.run(s.disconnect())

    def test_request_not_connected(self):
        s = MCPSession(FakeTransport(), make_config())
        with pytest.raises(MCPConnectionError):
            asyncio.run(s.request("ping"))

    def test_request_success(self):
        ft = FakeTransport().on("ping", {"ok": 1})
        s = MCPSession(ft, make_config())
        asyncio.run(s.connect())
        assert asyncio.run(s.request("ping")) == {"ok": 1}

    def test_request_rpc_error(self):
        ft = FakeTransport().on("ping", None, {"code": -32001, "message": "no"})
        s = MCPSession(ft, make_config())
        asyncio.run(s.connect())
        with pytest.raises(MCPRPCError):
            asyncio.run(s.request("ping"))

    def test_request_retry_then_success(self):
        ft = FakeTransport()
        s = MCPSession(ft, make_config(retry_enabled=True, retry_max_attempts=3,
                                       retry_base_delay=0))
        calls = {"n": 0}
        original = ft.send

        async def flaky(req):
            calls["n"] += 1
            if calls["n"] == 1:
                raise MCPTransportError("boom")
            return await original(req)

        ft.send = flaky  # type: ignore[method-assign]
        asyncio.run(s.connect())
        assert asyncio.run(s.request("ping")) == {}
        assert calls["n"] == 2

    def test_request_retry_disabled(self):
        ft = FakeTransport()
        calls = {"n": 0}
        original = ft.send

        async def flaky(req):
            calls["n"] += 1
            raise MCPTransportError("boom")

        ft.send = flaky  # type: ignore[method-assign]
        s = MCPSession(ft, make_config(retry_enabled=False))
        asyncio.run(s.connect())
        with pytest.raises(MCPTransportError):
            asyncio.run(s.request("ping"))
        assert calls["n"] == 1

    def test_request_non_retryable(self):
        ft = FakeTransport()
        calls = {"n": 0}

        async def flaky(req):
            calls["n"] += 1
            raise RuntimeError("hard")

        ft.send = flaky  # type: ignore[method-assign]
        s = MCPSession(ft, make_config(retry_enabled=True))
        asyncio.run(s.connect())
        with pytest.raises(RuntimeError):
            asyncio.run(s.request("ping"))
        assert calls["n"] == 1

    def test_request_timeout(self):
        class HangingTransport(FakeTransport):
            async def send(self, req):
                await asyncio.sleep(10)

        s = MCPSession(HangingTransport(), make_config())
        asyncio.run(s.connect())
        with pytest.raises(TimeoutError):
            asyncio.run(s.request("ping", timeout=0.01))

    def test_request_mcp_timeout_passthrough(self):
        ft = FakeTransport()
        calls = {"n": 0}

        async def flaky(req):
            calls["n"] += 1
            raise MCPTimeoutError("slow")

        ft.send = flaky  # type: ignore[method-assign]
        s = MCPSession(ft, make_config(retry_enabled=True, retry_max_attempts=3))
        asyncio.run(s.connect())
        with pytest.raises(MCPTimeoutError):
            asyncio.run(s.request("ping"))
        assert calls["n"] == 1

    def test_reconnect_disabled(self):
        s = MCPSession(FakeTransport(), make_config(reconnect_enabled=False))
        assert asyncio.run(s.reconnect()) is False

    def test_reconnect_success(self):
        class FlakyConnectTransport(FakeTransport):
            def __init__(self):
                super().__init__()
                self.connect_calls = 0

            async def connect(self):
                self.connect_calls += 1
                if self.connect_calls < 2:
                    raise MCPConnectionError("down")
                await super().connect()

        t = FlakyConnectTransport()
        events = []
        s = MCPSession(t, make_config(reconnect_enabled=True, reconnect_max_attempts=3,
                                      reconnect_base_delay=0, reconnect_max_delay=0))
        s._on_event = lambda e, d: events.append(e)  # type: ignore[method-assign]
        assert asyncio.run(s.reconnect()) is True
        assert s.state == MCPConnectionState.CONNECTED
        assert s.last_error == ""
        assert "reconnecting" in events
        assert "reconnected" in events

    def test_reconnect_failure(self):
        class AlwaysDownTransport(FakeTransport):
            async def connect(self):
                raise MCPConnectionError("down")

        s = MCPSession(AlwaysDownTransport(), make_config(
            reconnect_enabled=True, reconnect_max_attempts=2,
            reconnect_base_delay=0, reconnect_max_delay=0,
        ))
        assert asyncio.run(s.reconnect()) is False
        assert s.state == MCPConnectionState.ERROR

    def test_heartbeat_ok(self):
        async def scenario():
            events = []
            s = MCPSession(FakeTransport(), make_config(
                heartbeat_interval=0.01, heartbeat_timeout=0.1, reconnect_enabled=False,
            ), lambda e, d: events.append(e))
            await s.connect()
            await asyncio.sleep(0.05)
            assert "heartbeat" in events
            assert "heartbeat_failed" not in events
            await s.disconnect()

        asyncio.run(scenario())

    def test_heartbeat_failure_no_reconnect(self):
        async def scenario():
            ft = FakeTransport().on("ping", None, {"code": -1, "message": "down"})
            events = []
            s = MCPSession(ft, make_config(
                heartbeat_interval=0.01, heartbeat_timeout=0.1, reconnect_enabled=False,
            ), lambda e, d: events.append(e))
            await s.connect()
            await asyncio.sleep(0.05)
            assert "heartbeat_failed" in events
            await s.disconnect()

        asyncio.run(scenario())

    def test_heartbeat_failure_with_reconnect(self):
        async def scenario():
            ft = FakeTransport().on("ping", None, {"code": -1, "message": "down"})
            events = []
            s = MCPSession(ft, make_config(
                heartbeat_interval=0.01, heartbeat_timeout=0.1, reconnect_enabled=True,
                reconnect_max_attempts=2, reconnect_base_delay=0.01, reconnect_max_delay=0.02,
            ), lambda e, d: events.append(e))
            await s.connect()
            await asyncio.sleep(0.08)
            assert "heartbeat_failed" in events
            assert "reconnected" in events
            await s.disconnect()

        asyncio.run(scenario())

    def test_heartbeat_loop_skips_when_not_connected(self):
        async def scenario():
            s = MCPSession(FakeTransport(), make_config(
                heartbeat_interval=0.01, reconnect_enabled=False,
            ))
            await s.connect()
            s._state = MCPConnectionState.RECONNECTING
            await asyncio.sleep(0.03)
            assert s.state == MCPConnectionState.RECONNECTING
            await s.disconnect()

        asyncio.run(scenario())

    def test_on_event_errors_swallowed(self):
        def boom(event, data):
            raise RuntimeError("bad listener")

        s = MCPSession(FakeTransport(), make_config(), boom)
        asyncio.run(s.connect())
        assert s.state == MCPConnectionState.CONNECTED

    def test_close(self):
        t = CountingTransport()
        s = MCPSession(t, make_config())
        asyncio.run(s.connect())
        asyncio.run(s.close())
        assert s.state == MCPConnectionState.DISCONNECTED
        assert t.disconnect_calls == 1


# ============================================================
# Client
# ============================================================
class TestClient:
    def test_init_defaults(self):
        c = ClientCls(make_config())
        assert c.connected is False
        assert c.state == MCPConnectionState.DISCONNECTED
        assert isinstance(c.transport, StdioTransport)
        assert c.server_info is None

    def test_init_injected(self):
        ft = FakeTransport()
        c = make_client(transport=ft)
        assert c.transport is ft
        assert c.session is c._session

    def test_session_property(self):
        c = make_client()
        assert isinstance(c.session, MCPSession)

    def test_connect_success(self):
        c = make_client()
        asyncio.run(c.connect())
        assert c.connected is True
        assert c.state == MCPConnectionState.CONNECTED
        assert c.server_info is not None
        assert c.get_metrics().total_connections == 1
        asyncio.run(c.disconnect())

    def test_connect_no_discovery(self):
        c = make_client(config=make_config(discover_on_connect=False))
        asyncio.run(c.connect())
        assert c.connected is True
        assert c._discovery.server_info is None
        asyncio.run(c.disconnect())

    def test_connect_error_wrapped(self):
        ft = FakeTransport()

        async def flaky(req):
            raise RuntimeError("boom")

        ft.send = flaky  # type: ignore[method-assign]
        c = make_client(transport=ft)
        with pytest.raises(MCPConnectionError):
            asyncio.run(c.connect())
        assert c.get_metrics().total_errors == 1

    def test_connect_mcp_error_passthrough(self):
        class ErrTransport(FakeTransport):
            async def connect(self):
                raise MCPConnectionError("nope")

        c = make_client(transport=ErrTransport())
        with pytest.raises(MCPConnectionError):
            asyncio.run(c.connect())

    def test_disconnect(self):
        c = make_client()
        asyncio.run(c.connect())
        asyncio.run(c.disconnect())
        assert c.connected is False
        assert c.get_metrics().total_disconnections == 1
        assert c._watchers == {}

    def test_disconnect_cancels_notification_task(self):
        class LongNotificationsTransport(FakeTransport):
            async def notifications(self):
                yield {"jsonrpc": "2.0", "method": "notifications/other", "params": {}}
                while True:
                    await asyncio.sleep(10)

        async def scenario():
            c = make_client(transport=LongNotificationsTransport())
            await c.connect()
            await asyncio.sleep(0.01)
            assert c._notification_task is not None
            c._notification_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await c._notification_task
            await c.disconnect()
            assert c._notification_task is None

        asyncio.run(scenario())

    def test_initialize(self):
        c = make_client()
        asyncio.run(c.connect())
        info = asyncio.run(c.initialize())
        assert isinstance(info, MCPServerInfo)

    def test_ping(self):
        c = make_client()
        asyncio.run(c.connect())
        latency = asyncio.run(c.ping())
        assert isinstance(latency, float)
        assert c.get_metrics().total_pings == 1
        asyncio.run(c.disconnect())

    def test_ping_error(self):
        ft = FakeTransport().on("ping", None, {"code": -1, "message": "x"})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPRPCError):
            asyncio.run(c.ping())
        assert c.get_metrics().total_errors == 1

    def test_shutdown(self):
        ft = FakeTransport()
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        asyncio.run(c.shutdown())
        assert any(r.method == "shutdown" for r in ft.requests)
        assert c.connected is False

    def test_shutdown_error_swallowed(self):
        ft = FakeTransport().on("shutdown", None, {"code": -1, "message": "x"})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        asyncio.run(c.shutdown())
        assert c.connected is False

    def test_shutdown_not_connected(self):
        c = make_client()
        asyncio.run(c.shutdown())
        assert c.connected is False

    def test_discover(self):
        c = make_client()
        asyncio.run(c.connect())
        info = asyncio.run(c.discover())
        assert isinstance(info, MCPServerInfo)
        assert asyncio.run(c.discover()) is info

    def test_list_tools(self):
        ft = FakeTransport().on("tools/list", {"tools": [
            {"name": "sum", "description": "d", "inputSchema": {"type": "object"}},
        ]})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        tools = asyncio.run(c.list_tools())
        assert len(tools) == 1
        assert tools[0].name == "sum"
        asyncio.run(c.disconnect())

    def test_call_tool(self):
        ft = FakeTransport().on("tools/call", {
            "content": [{"type": "text", "text": "42"}],
            "structuredContent": {"value": 42},
            "isError": False,
        })
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        result = asyncio.run(c.call_tool("sum", {"a": 1}))
        assert isinstance(result, MCPCallResult)
        assert result.text == "42"
        assert result.structured_content == {"value": 42}
        assert result.tool_name == "sum"
        assert result.is_error is False
        assert c.get_metrics().total_tool_calls == 1
        asyncio.run(c.disconnect())

    def test_call_tool_error_result(self):
        ft = FakeTransport().on("tools/call", {
            "content": [{"type": "text", "text": "boom"}],
            "isError": True,
        })
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        result = asyncio.run(c.call_tool("t"))
        assert result.is_error is True
        assert c.get_metrics().total_errors == 1

    def test_call_tool_non_dict_result(self):
        ft = FakeTransport().on("tools/call", "plain")
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPToolError):
            asyncio.run(c.call_tool("t"))

    def test_call_tool_rpc_error(self):
        ft = FakeTransport().on("tools/call", None, {"code": -1, "message": "nope"})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPRPCError):
            asyncio.run(c.call_tool("t"))
        assert c.get_metrics().total_errors == 1

    def test_call_tool_unexpected_error(self):
        ft = FakeTransport()
        original = ft.send

        async def flaky(req):
            if req.method != "tools/call":
                return await original(req)
            raise RuntimeError("boom")

        ft.send = flaky  # type: ignore[method-assign]
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPToolError):
            asyncio.run(c.call_tool("t"))

    def test_batch_call(self):
        ft = FakeTransport().on("tools/call", {"content": [{"type": "text", "text": "ok"}]})
        c = make_client(transport=ft, config=make_config(max_batch_size=2))
        asyncio.run(c.connect())
        calls = [{"name": "t", "arguments": {"i": i}} for i in range(5)]
        results = asyncio.run(c.batch_call(calls))
        assert len(results) == 5
        assert len([r for r in ft.requests if r.method == "tools/call"]) == 5
        assert c.get_metrics().total_batch_calls == 1
        asyncio.run(c.disconnect())

    def test_batch_call_empty(self):
        c = make_client()
        assert asyncio.run(c.batch_call([])) == []

    def test_batch_call_malformed_item(self):
        c = make_client()
        asyncio.run(c.connect())
        with pytest.raises(MCPToolError):
            asyncio.run(c.batch_call([["bad"]]))

    def test_notification_loop_error_swallowed(self):
        class FailingNotificationsTransport(FakeTransport):
            async def notifications(self):
                yield {"jsonrpc": "2.0", "method": "notifications/other", "params": {}}
                raise RuntimeError("stream died")

        async def scenario():
            c = make_client(transport=FailingNotificationsTransport())
            await c.connect()
            await asyncio.sleep(0.05)
            assert c._notification_task.done()
            assert c.connected is True
            await c.disconnect()

        asyncio.run(scenario())

    def test_batch_call_error(self):
        ft = FakeTransport().on("tools/call", None, {"code": -1, "message": "nope"})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPRPCError):
            asyncio.run(c.batch_call([{"name": "t"}]))

    def test_chunk(self):
        assert MCPClient._chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
        assert MCPClient._chunk([], 2) == []

    def test_stream_call(self):
        ft = FakeTransport()
        ft.stream_events = [
            MCPStreamEvent(event_type="delta", data={"text": "a"}),
            MCPStreamEvent(event_type="result", data={"text": "b"}, is_final=True),
            MCPStreamEvent(event_type="delta", data={"text": "never"}),
        ]
        c = make_client(transport=ft)
        asyncio.run(c.connect())

        async def run():
            return [e async for e in c.stream_call("t")]

        events = asyncio.run(run())
        assert [e.event_type for e in events] == ["delta", "result"]
        assert events[0].tool_name == "t"
        assert c.get_metrics().total_stream_calls == 1
        asyncio.run(c.disconnect())

    def test_stream_call_not_connected(self):
        c = make_client()
        with pytest.raises(MCPDisconnectedError):
            asyncio.run(c.stream_call("t").__anext__())

    def test_stream_call_error(self):
        class BoomStreamTransport(FakeTransport):
            async def stream(self, req):
                yield MCPStreamEvent(event_type="delta", data={})
                raise RuntimeError("boom")

        c = make_client(transport=BoomStreamTransport())
        asyncio.run(c.connect())

        async def run():
            events = []
            with pytest.raises(MCPToolError):
                async for e in c.stream_call("t"):
                    events.append(e)
            return events

        events = asyncio.run(run())
        assert len(events) == 1

    def test_stream_call_mcp_error(self):
        class ErrStreamTransport(FakeTransport):
            async def stream(self, req):
                yield MCPStreamEvent(event_type="delta", data={})
                raise MCPConnectionError("gone")

        c = make_client(transport=ErrStreamTransport())
        asyncio.run(c.connect())

        async def run():
            events = []
            with pytest.raises(MCPConnectionError):
                async for e in c.stream_call("t"):
                    events.append(e)
            return events

        asyncio.run(run())

    def test_list_resources(self):
        ft = FakeTransport().on("resources/list", {
            "resources": [{"uri": "doc://1", "name": "r", "mimeType": "text/plain"}],
        })
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        resources = asyncio.run(c.list_resources())
        assert len(resources) == 1
        assert resources[0].uri == "doc://1"
        assert c.get_metrics().total_resources_listed == 1
        asyncio.run(c.disconnect())

    def test_read_resource(self):
        ft = FakeTransport().on("resources/read", {
            "contents": [{"uri": "doc://1", "text": "body"}],
        })
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        resource = asyncio.run(c.read_resource("doc://1"))
        assert resource.uri == "doc://1"
        assert resource.text == "body"
        assert c.get_metrics().total_resources_read == 1
        asyncio.run(c.disconnect())

    def test_read_resource_fills_uri(self):
        ft = FakeTransport().on("resources/read", {"contents": [{"text": "x"}]})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        resource = asyncio.run(c.read_resource("doc://9"))
        assert resource.uri == "doc://9"
        asyncio.run(c.disconnect())

    def test_read_resource_no_contents(self):
        ft = FakeTransport().on("resources/read", {"contents": []})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPResourceError):
            asyncio.run(c.read_resource("doc://1"))

    def test_read_resource_error(self):
        ft = FakeTransport().on("resources/read", None, {"code": -1, "message": "x"})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPRPCError):
            asyncio.run(c.read_resource("doc://1"))
        assert c.get_metrics().total_errors == 1

    def test_read_resource_unexpected_error(self):
        ft = FakeTransport()
        original = ft.send

        async def flaky(req):
            if req.method != "resources/read":
                return await original(req)
            raise RuntimeError("boom")

        ft.send = flaky  # type: ignore[method-assign]
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPResourceError):
            asyncio.run(c.read_resource("doc://1"))

    def test_watch_and_unwatch(self):
        ft = FakeTransport()
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        callback = lambda uri, params: None
        asyncio.run(c.watch_resource("doc://1", callback))
        assert len(c._watchers["doc://1"]) == 1
        assert c.get_metrics().total_resources_watched == 1
        asyncio.run(c.watch_resource("doc://1", callback))
        assert len(c._watchers["doc://1"]) == 2
        asyncio.run(c.unwatch_resource("doc://1"))
        assert "doc://1" not in c._watchers
        asyncio.run(c.disconnect())

    def test_watch_error(self):
        ft = FakeTransport()
        original = ft.send

        async def flaky(req):
            if req.method != "resources/subscribe":
                return await original(req)
            raise RuntimeError("boom")

        ft.send = flaky  # type: ignore[method-assign]
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPResourceError):
            asyncio.run(c.watch_resource("doc://1", lambda u, p: None))

    def test_unwatch_error(self):
        ft = FakeTransport()
        original = ft.send

        async def flaky(req):
            if req.method != "resources/unsubscribe":
                return await original(req)
            raise RuntimeError("boom")

        ft.send = flaky  # type: ignore[method-assign]
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        asyncio.run(c.watch_resource("doc://1", lambda u, p: None))
        with pytest.raises(MCPResourceError):
            asyncio.run(c.unwatch_resource("doc://1"))
        assert "doc://1" not in c._watchers

    def test_notification_dispatch(self):
        async def scenario():
            ft = FakeTransport()
            ft.notification_messages = [{
                "jsonrpc": "2.0",
                "method": "notifications/resources/updated",
                "params": {"uri": "doc://1"},
            }]
            c = make_client(transport=ft)
            await c.connect()
            calls = []
            await c.watch_resource("doc://1", lambda uri, params: calls.append(uri))
            await asyncio.sleep(0.02)
            assert calls == ["doc://1"]
            await c.disconnect()

        asyncio.run(scenario())

    def test_notification_dispatch_async_callback(self):
        async def scenario():
            ft = FakeTransport()
            ft.notification_messages = [{
                "jsonrpc": "2.0",
                "method": "notifications/resources/updated",
                "params": {"uri": "doc://2"},
            }]
            c = make_client(transport=ft)
            await c.connect()
            calls = []

            async def cb(uri, params):
                await asyncio.sleep(0)
                calls.append(uri)

            await c.watch_resource("doc://2", cb)
            await asyncio.sleep(0.02)
            assert calls == ["doc://2"]
            await c.disconnect()

        asyncio.run(scenario())

    def test_notification_dispatch_ignores_unknown(self):
        async def scenario():
            ft = FakeTransport()
            ft.notification_messages = [
                {"jsonrpc": "2.0", "method": "notifications/other", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/resources/updated"},
            ]
            c = make_client(transport=ft)
            await c.connect()
            calls = []
            await c.watch_resource("", lambda uri, params: calls.append(uri))
            await asyncio.sleep(0.02)
            assert calls == [""]
            await c.disconnect()

        asyncio.run(scenario())

    def test_notification_callback_error_swallowed(self):
        async def scenario():
            ft = FakeTransport()
            ft.notification_messages = [{
                "jsonrpc": "2.0",
                "method": "notifications/resources/updated",
                "params": {"uri": "doc://3"},
            }]
            c = make_client(transport=ft)
            await c.connect()
            calls = []

            def boom(uri, params):
                calls.append(uri)
                raise RuntimeError("bad callback")

            await c.watch_resource("doc://3", boom)
            await asyncio.sleep(0.02)
            assert calls == ["doc://3"]
            await c.disconnect()

        asyncio.run(scenario())

    def test_list_prompts(self):
        ft = FakeTransport().on("prompts/list", {"prompts": [{"name": "p"}]})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        prompts = asyncio.run(c.list_prompts())
        assert prompts[0].name == "p"
        assert c.get_metrics().total_prompts_listed == 1
        asyncio.run(c.disconnect())

    def test_get_prompt(self):
        ft = FakeTransport().on("prompts/get", {
            "name": "greet",
            "messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}],
        })
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        prompt = asyncio.run(c.get_prompt("greet", {"who": "x"}))
        assert isinstance(prompt, MCPRenderedPrompt)
        assert prompt.messages[0].role == "user"
        assert c.get_metrics().total_prompts_rendered == 1
        asyncio.run(c.disconnect())

    def test_get_prompt_non_dict(self):
        ft = FakeTransport().on("prompts/get", "nope")
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPPromptError):
            asyncio.run(c.get_prompt("greet"))

    def test_get_prompt_error(self):
        ft = FakeTransport().on("prompts/get", None, {"code": -1, "message": "x"})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPRPCError):
            asyncio.run(c.get_prompt("greet"))

    def test_get_prompt_unexpected_error(self):
        ft = FakeTransport()
        original = ft.send

        async def flaky(req):
            if req.method != "prompts/get":
                return await original(req)
            raise RuntimeError("boom")

        ft.send = flaky  # type: ignore[method-assign]
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        with pytest.raises(MCPPromptError):
            asyncio.run(c.get_prompt("greet"))

    def test_render_prompt(self):
        ft = FakeTransport().on("prompts/get", {
            "name": "greet",
            "messages": [{"role": "user", "content": {"type": "text", "text": "hi there"}}],
        })
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        assert asyncio.run(c.render_prompt("greet")) == "hi there"
        asyncio.run(c.disconnect())

    def test_render_messages(self):
        rp = MCPRenderedPrompt(name="p", messages=[
            MCPPromptMessage(content={"type": "text", "text": "a"}),
            MCPPromptMessage(content={"text": "b"}),
            MCPPromptMessage(content="c"),
            MCPPromptMessage(content={"type": "image", "data": "x"}),
        ])
        assert MCPClient._render_messages(rp) == "a\nb\nc\n{'type': 'image', 'data': 'x'}"

    def test_health_connected(self):
        c = make_client()
        asyncio.run(c.connect())
        h = asyncio.run(c.health())
        assert h.connected is True
        assert h.name == "ai-router"
        assert h.state == MCPConnectionState.CONNECTED
        assert h.latency_ms >= 0
        asyncio.run(c.disconnect())

    def test_health_disconnected(self):
        c = make_client()
        h = asyncio.run(c.health())
        assert h.connected is False
        assert h.latency_ms == 0.0
        assert h.last_error == ""

    def test_health_ping_error(self):
        ft = FakeTransport().on("ping", None, {"code": -1, "message": "ping down"})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        h = asyncio.run(c.health())
        assert "ping down" in h.last_error
        asyncio.run(c.disconnect())

    def test_health_counts(self):
        ft = FakeTransport().on("tools/list", {"tools": [{"name": "a"}]})
        c = make_client(transport=ft)
        asyncio.run(c.connect())
        asyncio.run(c.list_tools())
        h = asyncio.run(c.health())
        assert h.tool_count == 1
        asyncio.run(c.disconnect())

    def test_session_event_handlers(self):
        c = make_client()
        c._handle_session_event("heartbeat", {})
        c._handle_session_event("heartbeat_failed", {})
        c._handle_session_event("reconnected", {})
        c._handle_session_event("connected", {})
        c._handle_session_event("disconnected", {})
        c._handle_session_event("unknown", {})
        m = c.get_metrics()
        assert m.heartbeats == 1
        assert m.heartbeat_failures == 1
        assert m.total_reconnects == 1
        assert c._connected is False


# ============================================================
# Manager
# ============================================================
class TestManager:
    def test_register_and_properties(self):
        m = ManagerCls()
        client = m.register("s1", client=make_client())
        assert m.get("s1") is client
        assert m.has("s1") is True
        assert m.names == ["s1"]
        assert m.clients == {"s1": client}
        assert m.total_count() == 1

    def test_register_with_config(self):
        m = ManagerCls()
        cfg = make_config()
        client = m.register("s1", config=cfg)
        assert isinstance(client, MCPClient)
        assert m._configs["s1"] is cfg

    def test_register_default(self):
        m = ManagerCls()
        client = m.register("s1")
        assert isinstance(client, MCPClient)

    def test_register_duplicate(self):
        m = ManagerCls()
        m.register("s1", client=make_client())
        with pytest.raises(MCPManagerError):
            m.register("s1", client=make_client())

    def test_register_with_factory(self):
        seen = []

        def factory(config):
            seen.append(config)
            return make_client(config=config)

        m = ManagerCls(client_factory=factory)
        cfg = make_config()
        client = m.register("s1", config=cfg)
        assert seen == [cfg]
        assert m.get("s1") is client

    def test_unregister(self):
        m = ManagerCls()
        client = m.register("s1", client=make_client())
        assert m.unregister("s1") is client
        assert m.has("s1") is False
        assert m.total_count() == 0

    def test_unregister_missing(self):
        m = ManagerCls()
        with pytest.raises(MCPManagerError):
            m.unregister("nope")

    def test_get_missing(self):
        m = ManagerCls()
        with pytest.raises(MCPManagerError):
            m.get("nope")

    def test_connect_all(self):
        m = ManagerCls()
        m.register("ok", client=make_client())
        failing = MagicMock()
        failing.connect = AsyncMock(side_effect=RuntimeError("boom"))
        m.register("bad", client=failing)
        results = asyncio.run(m.connect_all())
        assert results == {"bad": False, "ok": True}

    def test_disconnect_all(self):
        m = ManagerCls()
        bad = MagicMock()
        bad.disconnect = AsyncMock(side_effect=RuntimeError("boom"))
        m.register("bad", client=bad)
        m.register("ok", client=make_client())
        asyncio.run(m.disconnect_all())
        bad.disconnect.assert_awaited_once()

    def test_shutdown_all(self):
        m = ManagerCls()
        bad = MagicMock()
        bad.shutdown = AsyncMock(side_effect=RuntimeError("boom"))
        m.register("bad", client=bad)
        m.register("ok", client=make_client())
        asyncio.run(m.shutdown_all())
        bad.shutdown.assert_awaited_once()

    def test_health(self):
        m = ManagerCls()
        m.register("s1", client=make_client())
        statuses = asyncio.run(m.health())
        assert len(statuses) == 1
        assert statuses[0].name == "s1"
        assert isinstance(statuses[0], MCPConnectionHealth)

    def test_connected_count(self):
        m = ManagerCls()
        connected = MagicMock()
        connected.connected = True
        m.register("a", client=connected)
        m.register("b", client=MagicMock())
        m.register("c", client=make_client())
        assert m.connected_count() == 2


# ============================================================
# Metrics / Logging / Exceptions / Factories
# ============================================================
class TestMetricsTracker:
    def test_all_records(self):
        tr = MCPMetricsTracker()
        tr.record_connection()
        tr.record_disconnection()
        tr.record_reconnect()
        tr.record_ping(5.0)
        tr.record_tool_call(2.0)
        tr.record_batch_call(3)
        tr.record_stream_call()
        tr.record_resources_listed()
        tr.record_resource_read()
        tr.record_resource_watched()
        tr.record_prompts_listed()
        tr.record_prompt_rendered()
        tr.record_heartbeat()
        tr.record_heartbeat_failure()
        tr.record_error()
        m = tr.get_metrics()
        assert isinstance(m, MCPMetrics)
        assert m.total_connections == 1
        assert m.total_disconnections == 1
        assert m.total_reconnects == 1
        assert m.total_pings == 1
        assert m.total_latency_ms == 7.0
        assert m.total_tool_calls == 4
        assert m.total_batch_calls == 1
        assert m.total_stream_calls == 1
        assert m.total_resources_listed == 1
        assert m.total_resources_read == 1
        assert m.total_resources_watched == 1
        assert m.total_prompts_listed == 1
        assert m.total_prompts_rendered == 1
        assert m.heartbeats == 1
        assert m.heartbeat_failures == 1
        assert m.total_errors == 1

    def test_get_metrics_returns_same(self):
        tr = MCPMetricsTracker()
        assert tr.get_metrics() is tr._metrics


class TestLogging:
    def test_log_event(self, caplog):
        import logging

        lg = MCPLogger("test_mcp_logger")
        with caplog.at_level(logging.INFO, logger="test_mcp_logger"):
            lg.log_event("connected", transport="fake")
        assert '"event": "mcp_connected"' in caplog.text
        assert '"transport": "fake"' in caplog.text

    def test_log_event_disabled(self, caplog):
        import logging

        lg = MCPLogger("test_mcp_logger")
        with caplog.at_level(logging.ERROR, logger="test_mcp_logger"):
            lg.log_event("connected")
        assert caplog.records == []

    def test_log_error(self, caplog):
        import logging

        lg = MCPLogger("test_mcp_logger")
        with caplog.at_level(logging.ERROR, logger="test_mcp_logger"):
            lg.log_error(ValueError("bad"), context="ctx")
        assert '"event": "mcp_error"' in caplog.text
        assert '"error": "bad"' in caplog.text
        assert '"error_type": "ValueError"' in caplog.text
        assert '"context": "ctx"' in caplog.text


class TestExceptions:
    def test_default_messages(self):
        assert MCPError("m").args == ("m",)
        assert MCPConnectionError().args == ("MCP connection failed",)
        assert MCPDisconnectedError().args == ("MCP client is not connected",)
        assert MCPTimeoutError().args == ("MCP request timed out",)
        assert MCPProtocolError().args == ("MCP protocol error",)
        assert MCPToolError().args == ("MCP tool call failed",)
        assert MCPResourceError().args == ("MCP resource operation failed",)
        assert MCPPromptError().args == ("MCP prompt operation failed",)
        assert MCPAuthError().args == ("MCP authentication failed",)
        assert MCPTransportError().args == ("MCP transport failed",)
        assert MCPManagerError().args == ("MCP connection manager failed",)

    def test_rpc_error(self):
        e = MCPRPCError(code=1, message="m", data={"a": 1})
        assert e.code == 1
        assert e.message == "m"
        assert e.data == {"a": 1}
        assert "m" in str(e)
        default = MCPRPCError()
        assert default.code == -32000
        assert default.data == {}
        assert str(default).startswith("MCP RPC error")


class TestFactories:
    def test_create_mcp_client(self):
        assert isinstance(create_mcp_client(config=make_config()), MCPClient)

    def test_create_mcp_client_from_env(self, monkeypatch):
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        monkeypatch.setenv("MCP_URL", "http://x")
        c = create_mcp_client()
        assert isinstance(c, MCPClient)
        assert c.transport.name == "http"

    def test_create_mcp_client_env_reset(self, monkeypatch):
        monkeypatch.delenv("MCP_TRANSPORT", raising=False)
        monkeypatch.delenv("MCP_URL", raising=False)
        c = create_mcp_client()
        assert c.transport.name == "stdio"

    def test_create_connection_manager(self):
        m = create_connection_manager()
        assert isinstance(m, ConnectionManager)
        m2 = create_connection_manager(logger=MCPLogger(), client_factory=lambda c: make_client(c))
        assert isinstance(m2, ConnectionManager)


# ============================================================
# Transport edge cases
# ============================================================
class TestTransportEdgeCases:
    def test_http_connect_idempotent(self):
        t = HTTPTransport(make_config(url="http://x"), client=MagicMock())
        asyncio.run(t.connect())
        asyncio.run(t.connect())
        assert t.connected is True

    def test_http_connect_creates_client(self):
        with patch("app.mcp.transports.httpx.AsyncClient") as mc:
            t = HTTPTransport(make_config(url="http://x"))
            asyncio.run(t.connect())
        mc.assert_called_once()
        assert t.connected is True

    def test_http_disconnect_no_client(self):
        t = HTTPTransport(make_config(url="http://x"))
        asyncio.run(t.disconnect())
        assert t.connected is False

    def test_http_stream_json_error(self):
        t = HTTPTransport(make_config(url="http://x"), client=self._err_client(1))
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        events = asyncio.run(run())
        assert events[0].event_type == "error"
        assert events[0].is_final

    @staticmethod
    def _err_client(request_id):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        resp.json.return_value = {
            "jsonrpc": "2.0", "id": request_id,
            "error": {"code": -1, "message": "nope"},
        }
        client.post = AsyncMock(return_value=resp)
        return client

    def test_ws_connect_idempotent(self):
        ws = MagicMock()
        t = WebSocketTransport(make_config(url="ws://x"), websocket=ws)
        asyncio.run(t.connect())
        asyncio.run(t.connect())
        assert t.connected is True

    def test_ws_connect_lib_success(self):
        fake = MagicMock()
        fake.connect = AsyncMock(return_value=MagicMock())
        with patch("app.mcp.transports.websockets", fake):
            t = WebSocketTransport(make_config(url="ws://x"))
            asyncio.run(t.connect())
        assert t.connected is True
        fake.connect.assert_awaited_once()

    def test_ws_connect_lib_failure(self):
        fake = MagicMock()
        fake.connect = AsyncMock(side_effect=RuntimeError("refused"))
        with patch("app.mcp.transports.websockets", fake):
            t = WebSocketTransport(make_config(url="ws://x"))
            with pytest.raises(MCPConnectionError):
                asyncio.run(t.connect())

    def test_ws_disconnect_not_connected(self):
        t = WebSocketTransport(make_config(url="ws://x"))
        asyncio.run(t.disconnect())
        assert t.connected is False

    def test_ws_stream_not_connected(self):
        t = WebSocketTransport(make_config(url="ws://x"))
        with pytest.raises(MCPConnectionError):
            asyncio.run(t.stream(JSONRPCRequest("x")).__anext__())

    def test_sse_connect_idempotent(self):
        t = SSETransport(make_config(url="http://x"), client=MagicMock())
        asyncio.run(t.connect())
        asyncio.run(t.connect())
        assert t.connected is True

    def test_sse_connect_creates_client(self):
        with patch("app.mcp.transports.httpx.AsyncClient") as mc:
            t = SSETransport(make_config(url="http://x"))
            asyncio.run(t.connect())
        mc.assert_called_once()
        assert t.connected is True

    def test_sse_disconnect_no_client(self):
        t = SSETransport(make_config(url="http://x"))
        asyncio.run(t.disconnect())
        assert t.connected is False

    def test_sse_stream_error_event(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.aiter_lines.return_value = _alist([
            'data: {"jsonrpc":"2.0","id":1,"error":{"code":1,"message":"e"}}', ""
        ])
        client.post = AsyncMock(return_value=resp)
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        events = asyncio.run(run())
        assert events[0].event_type == "error"
        assert events[0].is_final

    def test_sse_stream_skips_other_ids(self):
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.aiter_lines.return_value = _alist([
            'data: {"jsonrpc":"2.0","id":9,"result":{"r":9}}', "",
            'data: {"jsonrpc":"2.0","id":1,"result":{"r":1}}', "",
        ])
        client.post = AsyncMock(return_value=resp)
        t = SSETransport(make_config(url="http://x"), client=client)
        asyncio.run(t.connect())

        async def run():
            return [e async for e in t.stream(JSONRPCRequest("tools/call", request_id=1))]

        events = asyncio.run(run())
        assert events[0].data["result"] == {"r": 1}

    def test_stdio_spawns_process_with_env(self):
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout = MagicMock()
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)) as spawn:
            t = StdioTransport(
                make_config(command="mycmd", args=["a"], env={"K": "v"}),
                authenticator=APIKeyAuth("k"),
            )
            asyncio.run(t.connect())
        spawn.assert_awaited_once()
        assert spawn.call_args.args[0] == "mycmd"
        assert spawn.call_args.args[1] == "a"
        assert spawn.call_args.kwargs["env"]["K"] == "v"
        assert spawn.call_args.kwargs["env"]["X-API-Key"] == "k"

    def test_stdio_spawn_no_pipes(self):
        proc = MagicMock()
        proc.stdin = None
        proc.stdout = None
        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
            t = StdioTransport(make_config(command="x"))
            with pytest.raises(MCPConnectionError):
                asyncio.run(t.connect())

    def test_stdio_disconnect_close_error(self):
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdin.close.side_effect = RuntimeError("boom")
        proc.terminate = MagicMock(side_effect=ProcessLookupError())
        proc.kill = MagicMock(side_effect=RuntimeError("kill failed"))
        t = StdioTransport(make_config(command="x"), process=proc)
        t._owns_process = True
        asyncio.run(t.connect())
        asyncio.run(t.disconnect())
        assert t.connected is False
        proc.kill.assert_called_once()
