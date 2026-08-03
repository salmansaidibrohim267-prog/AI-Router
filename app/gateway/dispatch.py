"""Service dispatching for the API Gateway (Stage 10.4).

Supports REST, Server-Sent Events (SSE), WebSocket, and HTTP streaming
through a pluggable :class:`Transport` abstraction. Local handlers run
in-process; remote services use an async HTTP transport built on httpx.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, AsyncIterator

import httpx

from .exceptions import (
    GatewayTimeoutError,
    ServiceUnavailableError,
    UpstreamError,
    WebSocketUpgradeError,
)
from .models import GatewayRequest, GatewayResponse, Route, RouteProtocol, ServiceDescriptor, StreamEvent


class Transport:
    """Strategy interface for upstream communication."""

    protocol: RouteProtocol = RouteProtocol.HTTP

    async def request(self, service: ServiceDescriptor, request: GatewayRequest) -> GatewayResponse:
        raise NotImplementedError

    async def stream(self, service: ServiceDescriptor, request: GatewayRequest) -> AsyncIterator[bytes]:
        raise NotImplementedError

    async def websocket(self, service: ServiceDescriptor, request: GatewayRequest) -> AsyncIterator[StreamEvent]:
        raise NotImplementedError


class InMemoryTransport(Transport):
    """In-process transport that routes to a callable stored on the service.

    The service's ``metadata["handler"]`` may be an async callable receiving
    ``(request, service)``, or a dict of response fixtures.
    """

    protocol = RouteProtocol.HTTP

    async def request(self, service: ServiceDescriptor, request: GatewayRequest) -> GatewayResponse:
        handler = service.metadata.get("handler")
        if handler is None:
            fixtures = service.metadata.get("responses") or {}
            body = fixtures.get(request.path, {"status_code": 200, "body": {"ok": True}})
            return GatewayResponse(status_code=body.get("status_code", 200), body=body.get("body", {}))
        if asyncio.iscoroutinefunction(handler):
            return await handler(request, service)
        return handler(request, service)

    async def stream(self, service: ServiceDescriptor, request: GatewayRequest) -> AsyncIterator[bytes]:
        handler = service.metadata.get("stream_handler")
        if handler is None:
            raise ServiceUnavailableError(service.name)
        if inspect.isasyncgenfunction(handler):
            async for chunk in handler(request, service):
                yield chunk
        elif asyncio.iscoroutinefunction(handler):
            iterator = await handler(request, service)
            async for chunk in iterator:
                yield chunk
        else:
            for chunk in handler(request, service):
                yield chunk

    async def websocket(self, service: ServiceDescriptor, request: GatewayRequest) -> AsyncIterator[StreamEvent]:
        handler = service.metadata.get("ws_handler")
        if handler is None:
            raise ServiceUnavailableError(service.name)
        if inspect.isasyncgenfunction(handler):
            async for event in handler(request, service):
                yield event
        elif asyncio.iscoroutinefunction(handler):
            iterator = await handler(request, service)
            async for event in iterator:
                yield event
        else:
            for event in handler(request, service):
                yield event


class HttpTransport(Transport):
    """Async HTTP transport for remote upstream services (httpx)."""

    protocol = RouteProtocol.HTTP

    def __init__(self, timeout_seconds: float = 30.0, client_factory: Any | None = None):
        self._timeout = timeout_seconds
        self._client_factory = client_factory

    def _client(self) -> Any:
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))

    async def request(self, service: ServiceDescriptor, request: GatewayRequest) -> GatewayResponse:
        url = self._build_url(service, request)
        headers = {**service.headers, **request.headers}
        try:
            async with self._client() as client:
                response = await client.request(
                    request.method, url, headers=headers, params=request.query, content=request.body
                )  # noqa: E501
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(service.name, self._timeout) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(service.name, str(exc)) from exc
        return GatewayResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.text,
            content_type=response.headers.get("content-type", "application/json"),
        )

    async def stream(self, service: ServiceDescriptor, request: GatewayRequest) -> AsyncIterator[bytes]:
        url = self._build_url(service, request)
        headers = {**service.headers, **request.headers}
        try:
            async with self._client() as client:
                async with client.stream(
                    request.method, url, headers=headers, params=request.query, content=request.body
                ) as response:  # noqa: E501
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except httpx.TimeoutException as exc:
            raise GatewayTimeoutError(service.name, self._timeout) from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(service.name, str(exc)) from exc

    async def websocket(self, service: ServiceDescriptor, request: GatewayRequest) -> AsyncIterator[StreamEvent]:
        raise WebSocketUpgradeError("Remote websocket proxy not implemented in HttpTransport")

    def _build_url(self, service: ServiceDescriptor, request: GatewayRequest) -> str:
        base = service.base_url.rstrip("/")
        return base + request.path


class ServiceDispatcher:
    """Routes matched routes to the appropriate transport by protocol."""

    def __init__(self, transports: dict[str, Transport] | None = None):
        self._transports: dict[str, Transport] = dict(transports or {})
        self._services: dict[str, ServiceDescriptor] = {}

    @property
    def transports(self) -> dict[str, Transport]:
        return dict(self._transports)

    def register_transport(self, protocol: RouteProtocol | str, transport: Transport) -> None:
        name = protocol.value if isinstance(protocol, RouteProtocol) else protocol
        self._transports[name] = transport

    def register_service(self, descriptor: ServiceDescriptor) -> None:
        self._services[descriptor.name] = descriptor

    def unregister_service(self, name: str) -> bool:
        return self._services.pop(name, None) is not None

    def get_service(self, name: str) -> ServiceDescriptor | None:
        return self._services.get(name)

    def list_services(self) -> list[ServiceDescriptor]:
        return sorted(self._services.values(), key=lambda s: s.name)

    def _transport_for(self, protocol: RouteProtocol) -> Transport:
        transport = self._transports.get(protocol.value)
        if transport is None:
            raise ServiceUnavailableError(protocol.value)
        return transport

    async def dispatch(self, route: Route, request: GatewayRequest) -> GatewayResponse:
        transport = self._transport_for(route.protocol)
        service = self._service_for(route)
        if route.protocol == RouteProtocol.SSE:
            events = await self._collect_stream(transport, service, request)
            return self._sse_response(events)
        if route.protocol == RouteProtocol.STREAM:
            return GatewayResponse(
                status_code=200, body=transport.stream(service, request), content_type="application/octet-stream"
            )  # noqa: E501
        return await transport.request(service, request)

    async def _collect_stream(
        self, transport: Transport, service: ServiceDescriptor, request: GatewayRequest
    ) -> list[StreamEvent]:  # noqa: E501
        stream = transport.stream(service, request)
        events: list[StreamEvent] = []
        async for chunk in stream:
            data = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
            events.append(StreamEvent(data=data))
        return events

    def _sse_response(self, events: list[StreamEvent]) -> GatewayResponse:
        payload = "".join(event.serialize() for event in events)
        return GatewayResponse(status_code=200, body=payload, content_type="text/event-stream")

    def _service_for(self, route: Route) -> ServiceDescriptor:
        name = route.metadata.get("service", "")
        if not name:
            raise ServiceUnavailableError("no service configured for route")
        service = self._services.get(name)
        if service is None:
            raise ServiceUnavailableError(name)
        return service
