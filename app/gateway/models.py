"""Data models for the API Gateway (Stage 10.4)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable


class RouteMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    ANY = "ANY"


class RouteProtocol(str, Enum):
    HTTP = "http"
    SSE = "sse"
    WEBSOCKET = "websocket"
    STREAM = "stream"


class RouteVisibility(str, Enum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    PRIVATE = "private"


Handler = Callable[..., Any]
AsyncHandler = Callable[..., Awaitable[Any]]


@dataclass
class GatewayRequest:
    """Normalized incoming request."""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    version: str = ""
    client_id: str = ""
    principal: Any = None
    tenant_id: str = ""
    organization_id: str = ""
    workspace_id: str = ""
    path_params: dict[str, str] = field(default_factory=dict)
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)
    stream: Any = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GatewayRequest:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in payload.items() if k in known}
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "headers": dict(self.headers),
            "query": dict(self.query),
            "version": self.version,
            "client_id": self.client_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "correlation_id": self.correlation_id,
        }


@dataclass
class GatewayResponse:
    """Normalized outgoing response."""

    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    content_type: str = "application/json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "headers": dict(self.headers),
            "body": self.body,
            "content_type": self.content_type,
        }


@dataclass
class Route:
    """A registered gateway route."""

    pattern: str
    handler: AsyncHandler
    methods: list[str] = field(default_factory=lambda: [RouteMethod.ANY.value])
    version: str = "v1"
    protocol: RouteProtocol = RouteProtocol.HTTP
    visibility: RouteVisibility = RouteVisibility.PUBLIC
    deprecated: bool = False
    deprecated_since: str = ""
    sunset: str = ""
    cacheable: bool = False
    cache_ttl_seconds: float = 0.0
    rate_limit_key: str = ""
    quota_bucket: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def matches(self, method: str, version: str = "") -> bool:
        method_ok = RouteMethod.ANY.value in self.methods or method in self.methods
        version_ok = not version or self.version == version
        return method_ok and version_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "methods": list(self.methods),
            "version": self.version,
            "protocol": self.protocol.value,
            "visibility": self.visibility.value,
            "deprecated": self.deprecated,
            "deprecated_since": self.deprecated_since,
            "sunset": self.sunset,
            "cacheable": self.cacheable,
            "rate_limit_key": self.rate_limit_key,
            "quota_bucket": self.quota_bucket,
            "description": self.description,
            "tags": list(self.tags),
        }


@dataclass
class ServiceDescriptor:
    """Registered upstream service."""

    name: str
    base_url: str = ""
    version: str = "v1"
    protocol: RouteProtocol = RouteProtocol.HTTP
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "version": self.version,
            "protocol": self.protocol.value,
            "headers": dict(self.headers),
            "metadata": dict(self.metadata),
        }


@dataclass
class VersionInfo:
    """Version negotiation result."""

    version: str
    source: str
    deprecated: bool = False
    sunset: str = ""


@dataclass
class RateLimitDecision:
    """Result of a rate limit check."""

    allowed: bool
    strategy: str = ""
    key: str = ""
    limit: int = 0
    remaining: int = 0
    retry_after: float = 0.0
    reset_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "strategy": self.strategy,
            "key": self.key,
            "limit": self.limit,
            "remaining": self.remaining,
            "retry_after": self.retry_after,
            "reset_at": self.reset_at,
        }


@dataclass
class Webhook:
    """Registered webhook subscription."""

    url: str
    events: list[str] = field(default_factory=list)
    secret: str = ""
    active: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "url": self.url, "events": list(self.events), "active": self.active}


@dataclass
class WebhookDelivery:
    """Record of a single webhook delivery attempt."""

    webhook_id: str
    url: str
    event: str
    payload: dict[str, Any]
    status_code: int
    attempts: int = 1
    error: str = ""
    delivered_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "webhook_id": self.webhook_id,
            "url": self.url,
            "event": self.event,
            "status_code": self.status_code,
            "attempts": self.attempts,
            "error": self.error,
            "delivered_at": self.delivered_at,
        }


@dataclass
class CacheEntry:
    """Cached gateway response."""

    key: str
    response: GatewayResponse
    stored_at: float = field(default_factory=time.time)
    ttl_seconds: float = 60.0

    def is_expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) - self.stored_at > self.ttl_seconds


@dataclass
class DispatchResult:
    """Result of a gateway dispatch."""

    request: GatewayRequest
    response: GatewayResponse
    route: Route | None = None
    cache_hit: bool = False
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.response.status_code,
            "cache_hit": self.cache_hit,
            "duration_seconds": self.duration_seconds,
            "route": self.route.pattern if self.route else None,
            "errors": list(self.errors),
        }


@dataclass
class QuotaConsumption:
    """Current quota usage for one bucket."""

    bucket: str
    used: int
    limit: int
    remaining: int

    def to_dict(self) -> dict[str, Any]:
        return {"bucket": self.bucket, "used": self.used, "limit": self.limit, "remaining": self.remaining}


@dataclass
class StreamEvent:
    """A single chunk of an SSE or streaming response."""

    data: Any
    event: str = "message"
    id: str = ""

    def serialize(self) -> str:
        lines: list[str] = []
        if self.event:
            lines.append(f"event: {self.event}")
        if self.id:
            lines.append(f"id: {self.id}")
        payload = self.data if isinstance(self.data, str) else __import__("json").dumps(self.data)
        for line in payload.splitlines():
            lines.append(f"data: {line}")
        return "\n".join(lines) + "\n\n"
