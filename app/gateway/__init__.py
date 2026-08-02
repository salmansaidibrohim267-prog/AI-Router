"""API Gateway package (Stage 10.4).

Production-grade gateway with routing, versioning, rate limiting, quotas,
caching, webhooks, middleware chaining, service dispatching, and OpenAPI
generation. Integrates with Authentication (10.2), Organizations (10.3),
and the Multi-Tenant Foundation (10.1).
"""

from __future__ import annotations

from typing import Any

from ..auth import AuthenticationManager
from ..organization import OrganizationService
from ..tenancy import TenantManager
from .cache import ResponseCache, cache_key
from .config import GatewayConfig
from .dispatch import HttpTransport, InMemoryTransport, ServiceDispatcher, Transport
from .exceptions import (
    AuthenticationFailedError,
    CacheError,
    ForbiddenError,
    GatewayError,
    GatewayTimeoutError,
    MethodNotAllowedError,
    QuotaExceededError,
    RateLimitExceededError,
    RequestBodyTooLargeError,
    RouteNotFoundError,
    ServiceUnavailableError,
    TenantIsolationError,
    UnsupportedMediaTypeError,
    UpstreamError,
    ValidationError,
    VersionDeprecatedError,
    VersionNotSupportedError,
    WebSocketUpgradeError,
    WebhookDeliveryError,
    WebhookError,
)
from .gateway import APIGateway
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
    CacheEntry,
    DispatchResult,
    GatewayRequest,
    GatewayResponse,
    QuotaConsumption,
    RateLimitDecision,
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
from .openapi import generate_openapi, generate_openapi_spec
from .quota import BUCKET_KEYS, QUOTA_BUCKET_NAMES, QuotaManager
from .ratelimit import (
    FixedWindowLimiter,
    LeakyBucketLimiter,
    RateLimiter,
    RateLimitStrategy,
    SlidingWindowLimiter,
    TokenBucketLimiter,
    create_rate_limit_strategy,
)
from .routing import RouteRegistry, VersionNegotiator, compile_pattern
from .statistics import GatewayMetricsTracker
from .webhooks import WebhookManager

__all__ = [
    "APIGateway",
    "GatewayConfig",
    "GatewayLogger",
    "GatewayMetricsTracker",
    "GatewayError",
    "RouteNotFoundError",
    "MethodNotAllowedError",
    "VersionNotSupportedError",
    "VersionDeprecatedError",
    "RateLimitExceededError",
    "QuotaExceededError",
    "ValidationError",
    "UpstreamError",
    "ServiceUnavailableError",
    "GatewayTimeoutError",
    "UnsupportedMediaTypeError",
    "RequestBodyTooLargeError",
    "CacheError",
    "WebhookError",
    "WebhookDeliveryError",
    "WebSocketUpgradeError",
    "AuthenticationFailedError",
    "ForbiddenError",
    "TenantIsolationError",
    "GatewayRequest",
    "GatewayResponse",
    "Route",
    "RouteMethod",
    "RouteProtocol",
    "RouteVisibility",
    "VersionInfo",
    "RateLimitDecision",
    "Webhook",
    "WebhookDelivery",
    "CacheEntry",
    "DispatchResult",
    "QuotaConsumption",
    "StreamEvent",
    "ServiceDescriptor",
    "RouteRegistry",
    "VersionNegotiator",
    "compile_pattern",
    "RateLimiter",
    "RateLimitStrategy",
    "TokenBucketLimiter",
    "LeakyBucketLimiter",
    "SlidingWindowLimiter",
    "FixedWindowLimiter",
    "create_rate_limit_strategy",
    "QuotaManager",
    "QUOTA_BUCKET_NAMES",
    "BUCKET_KEYS",
    "ResponseCache",
    "cache_key",
    "WebhookManager",
    "Transport",
    "InMemoryTransport",
    "HttpTransport",
    "ServiceDispatcher",
    "Middleware",
    "MiddlewareChain",
    "AuthMiddleware",
    "TenantMiddleware",
    "OrgContextMiddleware",
    "RateLimitMiddleware",
    "QuotaMiddleware",
    "CacheMiddleware",
    "CorrelationMiddleware",
    "LoggingMiddleware",
    "ErrorHandlingMiddleware",
    "error_response",
    "generate_openapi",
    "generate_openapi_spec",
]


def create_gateway(
    config: GatewayConfig | None = None,
    *,
    authentication: AuthenticationManager | None = None,
    organizations: OrganizationService | None = None,
    tenants: TenantManager | None = None,
    limiter: RateLimiter | None = None,
    quotas: QuotaManager | None = None,
    cache: ResponseCache | None = None,
    webhooks: WebhookManager | None = None,
    dispatcher: ServiceDispatcher | None = None,
    middlewares: list[Middleware] | None = None,
    logger: GatewayLogger | None = None,
    metrics: GatewayMetricsTracker | None = None,
    audit: Any | None = None,
) -> APIGateway:
    """Dependency-injected factory for :class:`APIGateway`."""
    return APIGateway(
        config=config,
        logger=logger,
        metrics=metrics,
        authentication=authentication,
        organizations=organizations,
        tenants=tenants,
        limiter=limiter,
        quotas=quotas,
        cache=cache,
        webhooks=webhooks,
        dispatcher=dispatcher,
        middlewares=middlewares,
        audit=audit,
    )
