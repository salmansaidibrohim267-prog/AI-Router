"""APIGateway — the core facade of the gateway package (Stage 10.4).

Composes routing, versioning, rate limiting, quotas, caching, webhooks,
middleware chaining, and service dispatching into a single entry point that
integrates Authentication (10.2), Organizations (10.3), and Tenancy (10.1).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from ..auth import AuthenticationManager
from ..organization import OrganizationService
from ..tenancy import TenantManager
from .cache import ResponseCache, cache_key
from .config import GatewayConfig
from .dispatch import InMemoryTransport, ServiceDispatcher, Transport
from .exceptions import GatewayError, VersionDeprecatedError, VersionNotSupportedError
from .logging import GatewayLogger
from .middleware import (
    AuthMiddleware,
    CacheMiddleware,
    CorrelationMiddleware,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    Middleware,
    MiddlewareChain,
    OrgContextMiddleware,
    QuotaMiddleware,
    RateLimitMiddleware,
    TenantMiddleware,
    error_response,
)
from .models import (
    DispatchResult,
    GatewayRequest,
    GatewayResponse,
    Route,
    RouteMethod,
    RouteProtocol,
    RouteVisibility,
    ServiceDescriptor,
    StreamEvent,
    VersionInfo,
    Webhook,
    WebhookDelivery,
)
from .quota import QuotaManager
from .ratelimit import RateLimiter
from .routing import RouteRegistry, VersionNegotiator
from .statistics import GatewayMetricsTracker
from .webhooks import WebhookManager

LocalHandler = Callable[..., Awaitable[GatewayResponse] | GatewayResponse]


class APIGateway:
    """Production gateway exposing ``route``, ``dispatch``, ``register_route``,
    ``unregister_route``, and ``reload``."""

    def __init__(
        self,
        config: GatewayConfig | None = None,
        *,
        logger: GatewayLogger | None = None,
        metrics: GatewayMetricsTracker | None = None,
        authentication: AuthenticationManager | None = None,
        organizations: OrganizationService | None = None,
        tenants: TenantManager | None = None,
        limiter: RateLimiter | None = None,
        quotas: QuotaManager | None = None,
        cache: ResponseCache | None = None,
        webhooks: WebhookManager | None = None,
        dispatcher: ServiceDispatcher | None = None,
        middlewares: list[Middleware] | None = None,
        audit: Any | None = None,
    ):
        self._config = config or GatewayConfig()
        self._logger = logger or GatewayLogger(enabled=self._config.log_events)
        self._metrics = metrics or GatewayMetricsTracker(enabled=self._config.track_metrics)
        self._authentication = authentication
        self._organizations = organizations
        self._tenants = tenants
        self._limiter = limiter or RateLimiter(self._config)
        self._quotas = quotas or QuotaManager(self._config)
        self._cache = cache or ResponseCache(self._config, self._logger)
        self._webhooks = webhooks or WebhookManager(self._config, self._logger)
        self._dispatcher = dispatcher or ServiceDispatcher(
            transports={RouteProtocol.HTTP.value: InMemoryTransport(), RouteProtocol.SSE.value: InMemoryTransport(), RouteProtocol.STREAM.value: InMemoryTransport(), RouteProtocol.WEBSOCKET.value: InMemoryTransport()}
        )
        self._router = RouteRegistry(self._config, self._logger)
        self._negotiator = VersionNegotiator(self._config)
        self._audit = audit
        self._chain = MiddlewareChain()
        self._build_default_chain()
        if middlewares:
            for middleware in middlewares:
                self._chain.append(middleware)
        self._terminal = self._chain.build(self._invoke_route)

    @property
    def config(self) -> GatewayConfig:
        return self._config

    @property
    def logger(self) -> GatewayLogger:
        return self._logger

    @property
    def metrics(self) -> GatewayMetricsTracker:
        return self._metrics

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    @property
    def quotas(self) -> QuotaManager:
        return self._quotas

    @property
    def cache(self) -> ResponseCache:
        return self._cache

    @property
    def webhooks(self) -> WebhookManager:
        return self._webhooks

    @property
    def router(self) -> RouteRegistry:
        return self._router

    @property
    def dispatcher(self) -> ServiceDispatcher:
        return self._dispatcher

    @property
    def negotiator(self) -> VersionNegotiator:
        return self._negotiator

    @property
    def chain(self) -> MiddlewareChain:
        return self._chain

    # ------------------------------------------------------------ route mgmt

    def register_route(self, pattern: str, handler: LocalHandler | None = None, **route_kwargs: Any) -> Route:
        """Register a route with the given pattern and handler."""
        methods = route_kwargs.pop("methods", [RouteMethod.ANY.value])
        route = Route(pattern=pattern, handler=handler, methods=methods, **route_kwargs)  # type: ignore[arg-type]
        self._router.register(route)
        if self._audit is not None:
            self._audit.record("gateway.route_registered", resource=pattern, actor="system")
        return route

    def route(self, pattern: str, **route_kwargs: Any) -> Callable[[LocalHandler], Route]:
        """Decorator-based route registration."""

        def decorator(handler: LocalHandler) -> Route:
            return self.register_route(pattern, handler, **route_kwargs)

        return decorator

    def unregister_route(self, pattern: str) -> bool:
        removed = self._router.unregister(pattern)
        if removed and self._audit is not None:
            self._audit.record("gateway.route_unregistered", resource=pattern, actor="system")
        return removed

    def reload(self) -> int:
        """Recompile route patterns and return the new router revision."""
        revision = self._router.reload()
        self._terminal = self._chain.build(self._invoke_route)
        return revision

    # ------------------------------------------------------------ services

    def register_service(self, descriptor: ServiceDescriptor) -> None:
        self._dispatcher.register_service(descriptor)

    def register_transport(self, protocol: RouteProtocol | str, transport: Transport) -> None:
        self._dispatcher.register_transport(protocol, transport)

    # ------------------------------------------------------------ dispatch

    async def dispatch(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        body: Any = None,
        *,
        client_id: str = "",
        tenant_id: str = "",
        version: str = "",
    ) -> DispatchResult:
        """Route and process a request through the middleware chain."""
        started = time.time()
        headers = headers or {}
        query = query or {}
        client_id = client_id or headers.get("X-Client-ID", "")
        tenant_id = tenant_id or headers.get("X-Tenant-ID", "")

        request = GatewayRequest(
            method=method.upper(),
            path=path,
            headers=dict(headers),
            query=query,
            body=body,
            client_id=client_id,
            tenant_id=tenant_id,
        )

        info = VersionInfo(version=self._config.default_version, source="default")
        try:
            clean_path, url_version = self._negotiator.strip_version_prefix(path)
            info = self._negotiator.negotiate(clean_path, headers, url_version=url_version or version, query=query)
            request.path = clean_path
            request.version = info.version
            route, path_params = self._router.resolve(clean_path, request.method, info.version)
            request.path_params = path_params
            request.metadata["route"] = route
            response = await self._terminal(request)
        except GatewayError as exc:
            response = error_response(exc, request.correlation_id)

        if info.deprecated:
            response.headers.update(self._negotiator.deprecation_headers(info))
        response.headers.setdefault(self._config.correlation_header, request.correlation_id)

        duration = time.time() - started
        result = DispatchResult(
            request=request,
            response=response,
            route=request.metadata.get("route"),
            cache_hit=response.headers.get("X-Cache") == "HIT",
            duration_seconds=duration,
        )
        return result

    async def stream(self, method: str, path: str, headers: dict[str, str] | None = None, query: dict[str, Any] | None = None, body: Any = None, **kwargs: Any) -> DispatchResult:
        """Dispatch a request and return a streaming response body iterator."""
        result = await self.dispatch(method, path, headers, query, body, **kwargs)
        return result

    async def dispatch_websocket(self, path: str, headers: dict[str, str] | None = None, version: str = "", tenant_id: str = "") -> list[StreamEvent]:
        """Dispatch a websocket upgrade and collect the event stream."""
        started = time.time()
        headers = headers or {}
        clean_path, url_version = self._negotiator.strip_version_prefix(path)
        info = self._negotiator.negotiate(clean_path, headers, url_version=url_version or version)
        client_id = headers.get("X-Client-ID", "")

        request = GatewayRequest(
            method=RouteMethod.GET.value,
            path=clean_path,
            headers=dict(headers),
            version=info.version,
            tenant_id=tenant_id,
            metadata={"websocket": True},
        )
        route, path_params = self._router.resolve(clean_path, request.method, info.version)
        if route.protocol != RouteProtocol.WEBSOCKET:
            raise GatewayError(f"Route {route.pattern!r} is not a websocket route")
        request.path_params = path_params
        request.metadata["route"] = route
        transport = self._dispatcher.transports.get(RouteProtocol.WEBSOCKET.value)
        if transport is None:
            raise GatewayError("No websocket transport registered")
        service = route.metadata.get("service", "")
        descriptor = self._dispatcher.get_service(service) if service else None
        if descriptor is None:
            raise GatewayError("No service configured for websocket route")
        events: list[StreamEvent] = []
        async for event in transport.websocket(descriptor, request):
            events.append(event)
        self._metrics.record_request("WS", clean_path, 200, time.time() - started, version=info.version, protocol="websocket")
        return events

    # ------------------------------------------------------------ internals

    def _build_default_chain(self) -> None:
        self._chain.clear()
        self._chain.append(ErrorHandlingMiddleware())
        self._chain.append(CorrelationMiddleware(self._config))
        self._chain.append(LoggingMiddleware(self._logger, self._metrics))
        if self._authentication is not None:
            self._chain.append(AuthMiddleware(self._authentication))
        if self._tenants is not None:
            self._chain.append(TenantMiddleware(self._tenants))
        self._chain.append(OrgContextMiddleware(self._organizations))
        self._chain.append(RateLimitMiddleware(self._limiter, self._metrics))
        self._chain.append(QuotaMiddleware(self._quotas, self._metrics))
        self._chain.append(CacheMiddleware(self._cache))

    async def _invoke_route(self, request: GatewayRequest) -> GatewayResponse:
        route: Route | None = request.metadata.get("route")
        if route is None:
            from .exceptions import RouteNotFoundError

            raise RouteNotFoundError(request.path, request.method)
        if route.handler is not None:
            result = route.handler(request)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, GatewayResponse):
                return result
            return GatewayResponse(status_code=200, body=result)
        if route.protocol == RouteProtocol.WEBSOCKET:
            from .exceptions import WebSocketUpgradeError

            raise WebSocketUpgradeError("Websocket routes must be dispatched via dispatch_websocket")
        return await self._dispatcher.dispatch(route, request)

    # ------------------------------------------------------------ observability

    def get_metrics(self) -> dict[str, Any]:
        return self._metrics.get_metrics()

    def close(self) -> None:
        """Release resources; safe to call multiple times."""
        self._logger.clear()

    def openapi(self, format: str = "json") -> str:
        from .openapi import generate_openapi

        return generate_openapi(self, format=format)
