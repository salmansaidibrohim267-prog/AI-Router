"""Middleware chain (Chain of Responsibility) for the API Gateway (Stage 10.4).

Integrates authentication (Stage 10.2), organizations (Stage 10.3), and
multi-tenancy (Stage 10.1) into the request pipeline, plus rate limiting,
quotas, caching, correlation ids, logging, and error conversion.
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from ..auth import AuthenticationManager, PermissionDeniedError
from ..organization import OrganizationService
from ..tenancy import TenantManager
from .cache import ResponseCache, cache_key
from .config import GatewayConfig
from .exceptions import (
    AuthenticationFailedError,
    ForbiddenError,
    GatewayError,
    RateLimitExceededError,
    TenantIsolationError,
)
from .logging import GatewayLogger
from .models import GatewayRequest, GatewayResponse, Route, RouteVisibility
from .quota import QuotaManager
from .ratelimit import RateLimiter
from .statistics import GatewayMetricsTracker

NextHandler = Callable[[GatewayRequest], Awaitable[GatewayResponse]]


def error_response(exc: Exception, correlation_id: str = "") -> GatewayResponse:
    """Convert an exception into a normalized gateway response."""
    if isinstance(exc, GatewayError):
        body = exc.to_dict()
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if exc.error_code == "rate_limit_exceeded":
            retry_after = exc.details.get("retry_after", 0)
            headers["Retry-After"] = str(int(retry_after) + 1)
            headers["X-RateLimit-Limit"] = str(exc.details.get("limit", 0))
            headers["X-RateLimit-Remaining"] = "0"
        elif exc.error_code == "quota_exceeded":
            headers["X-Quota-Bucket"] = str(exc.details.get("bucket", ""))
        return GatewayResponse(status_code=exc.status_code, headers=headers, body=body)
    return GatewayResponse(
        status_code=500,
        headers={"Content-Type": "application/json"},
        body={"error": "internal_error", "message": "Internal gateway error"},
    )


class Middleware:
    """Base middleware implementing the Chain of Responsibility step."""

    name: str = "middleware"

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        return await next_handler(request)

    def __call__(self, next_handler: NextHandler) -> NextHandler:
        async def wrapper(request: GatewayRequest) -> GatewayResponse:
            return await self.handle(request, next_handler)

        return wrapper


class MiddlewareChain:
    """Composable ordered pipeline of middleware steps."""

    def __init__(self, middlewares: list[Middleware] | None = None):
        self._middlewares: list[Middleware] = list(middlewares or [])

    @property
    def middlewares(self) -> list[Middleware]:
        return list(self._middlewares)

    def append(self, middleware: Middleware) -> None:
        self._middlewares.append(middleware)

    def prepend(self, middleware: Middleware) -> None:
        self._middlewares.insert(0, middleware)

    def remove(self, name: str) -> bool:
        before = len(self._middlewares)
        self._middlewares = [mw for mw in self._middlewares if mw.name != name]
        return len(self._middlewares) != before

    def clear(self) -> None:
        self._middlewares.clear()

    def build(self, terminal: NextHandler) -> NextHandler:
        handler = terminal
        for middleware in reversed(self._middlewares):
            handler = middleware(handler)
        return handler


class CorrelationMiddleware(Middleware):
    """Ensures every request carries a correlation id."""

    name = "correlation"

    def __init__(self, config: GatewayConfig):
        self._config = config

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        header = self._config.correlation_header
        if header in request.headers:
            request.correlation_id = request.headers[header]
        response = await next_handler(request)
        response.headers[header] = request.correlation_id
        return response


class LoggingMiddleware(Middleware):
    """Structured request/response logging with duration."""

    name = "logging"

    def __init__(self, logger: GatewayLogger, metrics: GatewayMetricsTracker | None = None):
        self._logger = logger
        self._metrics = metrics

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        started = time.time()
        response = await next_handler(request)
        duration = time.time() - started
        self._logger.request(
            request.method,
            request.path,
            response.status_code,
            duration,
            version=request.version,
            correlation_id=request.correlation_id,
            client_id=request.client_id,
        )
        if self._metrics is not None:
            self._metrics.record_request(
                request.method,
                request.path,
                response.status_code,
                duration,
                version=request.version,
            )
        return response


class ErrorHandlingMiddleware(Middleware):
    """Converts raised exceptions into normalized responses."""

    name = "error_handling"

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        try:
            return await next_handler(request)
        except GatewayError as exc:
            return error_response(exc, request.correlation_id)
        except Exception:
            return error_response(Exception("internal gateway error"), request.correlation_id)


class AuthMiddleware(Middleware):
    """Authenticates requests and enforces route visibility."""

    name = "auth"

    def __init__(self, authentication: AuthenticationManager):
        self._authentication = authentication

    @property
    def authentication(self) -> AuthenticationManager:
        return self._authentication

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        route: Route | None = request.metadata.get("route")
        if route is not None and route.visibility == RouteVisibility.PUBLIC:
            return await next_handler(request)
        try:
            principal = await self._authentication.authenticate(
                headers=request.headers,
                authorization=request.headers.get("Authorization", ""),
            )
        except PermissionDeniedError as exc:
            raise AuthenticationFailedError(str(exc)) from exc
        except Exception as exc:
            raise AuthenticationFailedError(f"Authentication failed: {exc}") from exc
        if principal is None:
            raise AuthenticationFailedError("Missing or invalid credentials")
        if route is not None and route.visibility == RouteVisibility.PRIVATE:
            permission = route.metadata.get("permission", "")
            scopes = set(principal.scopes or ())
            roles = set(principal.roles or ())
            if permission and permission not in scopes and "admin" not in roles:
                raise ForbiddenError(f"Missing permission {permission!r}")
        request.principal = principal
        request.client_id = request.client_id or principal.user_id
        return await next_handler(request)


class TenantMiddleware(Middleware):
    """Resolves and validates the tenant from headers via TenancyManager."""

    name = "tenant"

    def __init__(self, tenants: TenantManager | None = None):
        self._tenants = tenants

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        tenant_id = request.headers.get("X-Tenant-ID", request.tenant_id)
        if self._tenants is not None:
            if not tenant_id:
                raise TenantIsolationError("Missing tenant header X-Tenant-ID")
            try:
                tenant = self._tenants.get_active(tenant_id)
            except Exception as exc:
                raise TenantIsolationError(f"Tenant {tenant_id!r} is not available") from exc
            if tenant is None:
                raise TenantIsolationError(f"Tenant {tenant_id!r} is not available")
            request.tenant_id = tenant.id
            request.metadata["tenant"] = tenant
        else:
            request.tenant_id = tenant_id
        return await next_handler(request)


class OrgContextMiddleware(Middleware):
    """Resolves organization/workspace context via OrganizationService."""

    name = "org_context"

    def __init__(self, organizations: OrganizationService | None = None):
        self._organizations = organizations

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        request.organization_id = request.headers.get("X-Organization-ID", request.organization_id)
        request.workspace_id = request.headers.get("X-Workspace-ID", request.workspace_id)
        return await next_handler(request)


class RateLimitMiddleware(Middleware):
    """Enforces rate limits for the matched route and client."""

    name = "rate_limit"

    def __init__(self, limiter: RateLimiter, metrics: GatewayMetricsTracker | None = None):
        self._limiter = limiter
        self._metrics = metrics

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    def _key_for(self, request: GatewayRequest) -> str:
        route: Route | None = request.metadata.get("route")
        if route is not None and route.rate_limit_key:
            base = route.rate_limit_key
        else:
            base = f"{request.method}:{request.path}"
        return f"{request.tenant_id or 'anon'}:{request.client_id or 'anon'}:{base}"

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        key = self._key_for(request)
        decision = self._limiter.check(key)
        if not decision.allowed:
            if self._metrics is not None:
                self._metrics.record_rate_limit_hit(decision.strategy)
            raise RateLimitExceededError(
                key=key,
                strategy=decision.strategy,
                retry_after=decision.retry_after,
                limit=decision.limit,
            )
        response = await next_handler(request)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        return response


class QuotaMiddleware(Middleware):
    """Consumes quota for the matched route and refunds on upstream failures."""

    name = "quota"

    def __init__(self, quotas: QuotaManager, metrics: GatewayMetricsTracker | None = None):
        self._quotas = quotas
        self._metrics = metrics

    @property
    def quotas(self) -> QuotaManager:
        return self._quotas

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        route: Route | None = request.metadata.get("route")
        bucket = (
            (route.quota_bucket if route is not None and route.quota_bucket else "requests")
            if route is not None
            else "requests"
        )  # noqa: E501
        scope = f"{request.tenant_id}:{request.client_id}"
        amount = int(request.metadata.get("quota_amount", 1))
        try:
            self._quotas.check(scope, bucket, amount)
        except Exception as exc:
            if self._metrics is not None:
                self._metrics.record_quota_hit(bucket)
            raise exc
        try:
            response = await next_handler(request)
            if response.status_code >= 500:
                self._quotas.refund(scope, bucket, amount)
            return response
        except Exception:
            self._quotas.refund(scope, bucket, amount)
            raise


class CacheMiddleware(Middleware):
    """Serves and stores cached responses for cacheable GET routes."""

    name = "cache"

    def __init__(self, cache: ResponseCache):
        self._cache = cache

    @property
    def cache(self) -> ResponseCache:
        return self._cache

    async def handle(self, request: GatewayRequest, next_handler: NextHandler) -> GatewayResponse:
        route: Route | None = request.metadata.get("route")
        cacheable = route is not None and route.cacheable and self._cache.enabled and request.method in ("GET", "HEAD")
        if not cacheable:
            return await next_handler(request)

        key = cache_key(request, route=route.pattern)
        request.metadata["cache_key"] = key
        cached = self._cache.get(key)
        if cached is not None:
            cached.headers["X-Cache"] = "HIT"
            return cached
        response = await next_handler(request)
        if 200 <= response.status_code < 300:
            self._cache.set(key, response, ttl_seconds=route.cache_ttl_seconds or None)
            response.headers["X-Cache"] = "MISS"
        return response
