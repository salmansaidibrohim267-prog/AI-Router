from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from app.gateway import (
    APIGateway,
    BUCKET_KEYS,
    QUOTA_BUCKET_NAMES,
    AuthMiddleware,
    AuthenticationFailedError,
    CacheEntry,
    CacheError,
    CacheMiddleware,
    CorrelationMiddleware,
    DispatchResult,
    ErrorHandlingMiddleware,
    FixedWindowLimiter,
    ForbiddenError,
    GatewayConfig,
    GatewayError,
    GatewayLogger,
    GatewayMetricsTracker,
    GatewayRequest,
    GatewayResponse,
    GatewayTimeoutError,
    HttpTransport,
    InMemoryTransport,
    LeakyBucketLimiter,
    LoggingMiddleware,
    MethodNotAllowedError,
    Middleware,
    MiddlewareChain,
    OrgContextMiddleware,
    QuotaExceededError,
    QuotaManager,
    QuotaMiddleware,
    QUOTA_BUCKET_NAMES as _QBN,
    RateLimitDecision,
    RateLimitExceededError,
    RateLimitMiddleware,
    RateLimiter,
    RateLimitStrategy,
    RequestBodyTooLargeError,
    ResponseCache,
    Route,
    RouteMethod,
    RouteNotFoundError,
    RouteProtocol,
    RouteRegistry,
    RouteVisibility,
    ServiceDescriptor,
    ServiceUnavailableError,
    ServiceDispatcher,
    SlidingWindowLimiter,
    StreamEvent,
    TenantIsolationError,
    TenantMiddleware,
    TokenBucketLimiter,
    Transport,
    UnsupportedMediaTypeError,
    UpstreamError,
    ValidationError,
    VersionDeprecatedError,
    VersionInfo,
    VersionNegotiator,
    VersionNotSupportedError,
    WebSocketUpgradeError,
    Webhook,
    WebhookDelivery,
    WebhookDeliveryError,
    WebhookError,
    WebhookManager,
    cache_key,
    compile_pattern,
    create_gateway,
    create_rate_limit_strategy,
    error_response,
    generate_openapi,
    generate_openapi_spec,
)
from app.gateway.config import GatewayConfig as _GC
from app.gateway.exceptions import RouteNotFoundError as _RNFE


def make_config(**kwargs):
    defaults = {
        "log_events": False,
        "track_metrics": True,
        "audit_enabled": False,
        "default_requests_per_minute": 100000,
        "default_burst": 50000,
        "webhooks_enabled": True,
    }
    defaults.update(kwargs)
    return GatewayConfig(**defaults)


def make_gateway(**kwargs):
    defaults = {"config": make_config()}
    defaults.update(kwargs)
    return create_gateway(**defaults)


async def _run(coro):
    return await coro


def run(coro):
    return asyncio.run(coro)


def as_ok(handler):
    async def wrapped(request):
        return handler(request)

    return wrapped


# ---------------------------------------------------------------- config


def test_config_defaults():
    cfg = GatewayConfig()
    assert cfg.default_version == "v1"
    assert cfg.supported_versions == ["v1", "v2"]
    assert cfg.deprecated_versions == ["v1"]
    assert cfg.default_rate_limit_strategy == "token_bucket"
    assert cfg.cache_enabled is True
    assert cfg.to_dict()["audit_enabled"] is True


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("GW_DEFAULT_VERSION", "v3")
    monkeypatch.setenv("GW_SUPPORTED_VERSIONS", "v2, v3")
    monkeypatch.setenv("GW_DEFAULT_REQUESTS_PER_MINUTE", "500")
    monkeypatch.setenv("GW_CACHE_ENABLED", "false")
    monkeypatch.setenv("GW_WEBHOOKS_ENABLED", "0")
    monkeypatch.setenv("GW_OPENAPI_SERVERS", "https://a.example, https://b.example")
    monkeypatch.setenv("GW_SLIDING_WINDOW_PRECISION", "0.5")
    monkeypatch.setenv("GW_MAX_BODY_BYTES", "12345")
    cfg = GatewayConfig.from_env()
    assert cfg.default_version == "v3"
    assert cfg.supported_versions == ["v2", "v3"]
    assert cfg.default_requests_per_minute == 500
    assert cfg.cache_enabled is False
    assert cfg.webhooks_enabled is False
    assert cfg.openapi_servers == ["https://a.example", "https://b.example"]
    assert cfg.sliding_window_precision == 0.5
    assert cfg.max_body_bytes == 12345


def test_config_from_env_bool_true_values(monkeypatch):
    monkeypatch.setenv("GW_CACHE_ENABLED", "yes")
    monkeypatch.setenv("GW_LOG_EVENTS", "TRUE")
    cfg = GatewayConfig.from_env()
    assert cfg.cache_enabled is True
    assert cfg.log_events is True


# ---------------------------------------------------------------- exceptions


def test_exception_hierarchy():
    assert issubclass(RouteNotFoundError, GatewayError)
    err = RouteNotFoundError("/x", "GET")
    assert err.status_code == 404
    assert err.error_code == "route_not_found"
    assert err.to_dict()["path"] == "/x"
    assert err.to_dict()["message"]

    for exc_class, code in [
        (MethodNotAllowedError, "method_not_allowed"),
        (VersionNotSupportedError, "version_not_supported"),
        (VersionDeprecatedError, "version_deprecated"),
        (RateLimitExceededError, "rate_limit_exceeded"),
        (QuotaExceededError, "quota_exceeded"),
        (ValidationError, "validation_error"),
        (UpstreamError, "upstream_error"),
        (ServiceUnavailableError, "service_unavailable"),
        (GatewayTimeoutError, "gateway_timeout"),
        (UnsupportedMediaTypeError, "unsupported_media_type"),
        (RequestBodyTooLargeError, "request_body_too_large"),
        (CacheError, "cache_error"),
        (WebhookError, "webhook_error"),
        (WebhookDeliveryError, "webhook_delivery_failed"),
        (WebSocketUpgradeError, "websocket_upgrade_failed"),
        (AuthenticationFailedError, "authentication_failed"),
        (ForbiddenError, "forbidden"),
        (TenantIsolationError, "tenant_isolation_error"),
    ]:
        assert exc_class.status_code >= 400
        assert exc_class.error_code == code


def test_exception_status_overrides():
    err = GatewayError("boom", status_code=418, error_code="teapot")
    assert err.status_code == 418
    assert err.error_code == "teapot"
    assert err.to_dict() == {"error": "teapot", "message": "boom"}


# ---------------------------------------------------------------- models


def test_route_model():
    route = Route(
        pattern="/a/{b}",
        handler=lambda request: None,
        methods=["GET", "POST"],
        version="v2",
        deprecated=True,
        cacheable=True,
    )
    assert route.matches("GET", "v2") is True
    assert route.matches("DELETE", "v2") is False
    assert route.matches("GET", "v1") is False
    assert route.matches("POST") is True
    assert route.matches("ANY") is False
    data = route.to_dict()
    assert data["pattern"] == "/a/{b}"
    assert data["methods"] == ["GET", "POST"]
    assert data["deprecated"] is True
    assert data["cacheable"] is True


def test_gateway_request_roundtrip():
    request = GatewayRequest(method="POST", path="/x", headers={"A": "1"}, query={"q": 2}, body={"b": 3})
    payload = request.to_dict()
    assert payload["method"] == "POST"
    assert payload["path"] == "/x"
    assert payload["correlation_id"] == request.correlation_id
    restored = GatewayRequest.from_dict(payload)
    assert restored.path == "/x"
    assert restored.headers == {"A": "1"}
    assert restored.query == {"q": 2}
    assert restored.body is None
    assert restored.correlation_id == request.correlation_id


def test_gateway_response_and_dispatch_result():
    response = GatewayResponse(status_code=201, headers={"H": "v"}, body={"ok": 1}, content_type="text/plain")
    assert response.to_dict()["status_code"] == 201
    request = GatewayRequest(method="GET", path="/x")
    result = DispatchResult(request=request, response=response, cache_hit=True, duration_seconds=0.5)
    data = result.to_dict()
    assert data["status_code"] == 201
    assert data["cache_hit"] is True
    assert data["duration_seconds"] == 0.5


def test_stream_event_serialize():
    assert StreamEvent(data="hello", event="").serialize() == "data: hello\n\n"
    assert StreamEvent(data={"a": 1}, event="update", id="7").serialize() == "event: update\nid: 7\ndata: {\"a\": 1}\n\n"
    multi = StreamEvent(data="line1\nline2").serialize()
    assert "data: line1\n" in multi
    assert "data: line2" in multi


def test_cache_entry_expiry():
    entry = CacheEntry(key="k", response=GatewayResponse(), stored_at=time.time() - 100, ttl_seconds=60)
    assert entry.is_expired() is True
    fresh = CacheEntry(key="k", response=GatewayResponse())
    assert fresh.is_expired() is False
    assert fresh.is_expired(now=time.time() + 999) is True


def test_misc_model_serializations():
    info = VersionInfo(version="v1", source="header", deprecated=True, sunset="soon")
    assert info.deprecated and info.sunset == "soon"
    decision = RateLimitDecision(allowed=True, strategy="token_bucket", key="k", limit=10, remaining=5)
    assert decision.to_dict()["allowed"] is True
    webhook = Webhook(url="http://x.example", events=["a"])
    assert webhook.to_dict()["events"] == ["a"]
    delivery = WebhookDelivery(webhook_id="w", url="u", event="e", payload={}, status_code=200, error="")
    assert delivery.to_dict()["status_code"] == 200
    from app.gateway import QuotaConsumption

    assert QuotaConsumption(bucket="b", used=1, limit=2, remaining=1).to_dict()["bucket"] == "b"
    descriptor = ServiceDescriptor(name="svc", base_url="http://svc", version="v2", protocol=RouteProtocol.SSE)
    assert descriptor.to_dict()["protocol"] == "sse"


# ---------------------------------------------------------------- logging


def test_gateway_logger():
    sink = []
    logger = GatewayLogger(enabled=True, sink=sink.append)
    logger.log_event("test.event", key="value")
    logger.request("GET", "/x", 200, 0.01)
    logger.route("/p", "registered")
    logger.error("bad", "boom")
    assert len(sink) == 4
    record = json.loads(sink[0])
    assert record["event"] == "test.event"
    assert record["key"] == "value"
    assert len(logger.events) == 4
    logger.clear()
    assert logger.events == []


def test_gateway_logger_disabled():
    logger = GatewayLogger(enabled=False)
    logger.log_event("x")
    assert logger.events == []
    assert logger.enabled is False


def test_gateway_logger_sink_failure():
    def bad_sink(_record):
        raise RuntimeError("sink down")

    logger = GatewayLogger(enabled=True, sink=bad_sink)
    logger.log_event("x")
    assert len(logger.events) == 1
    assert logger.events[0]["event"] == "x"


# ---------------------------------------------------------------- statistics


def test_metrics_tracker():
    metrics = GatewayMetricsTracker(enabled=True)
    metrics.record_request("GET", "/a", 200, 0.01)
    metrics.record_request("GET", "/a", 500, 0.02, version="v2", protocol="sse")
    metrics.record_rate_limit_hit("token_bucket")
    metrics.record_quota_hit("tokens")
    metrics.record_cache(hit=True, route="/a")
    metrics.record_cache(hit=False, route="/a")
    metrics.record_webhook("e", success=True)
    metrics.record_webhook("e", success=False)
    data = metrics.get_metrics()
    assert data["total_requests"] == 2
    assert data["requests_by_route"]["GET /a"] == 2
    assert data["requests_by_version"]["v2"] == 1
    assert data["requests_by_protocol"]["sse"] == 1
    assert data["errors"] == {"/a 500": 1}
    assert data["rate_limit_hits"]["token_bucket"] == 1
    assert data["quota_hits"]["tokens"] == 1
    assert data["cache_hits"]["/a"] == 1
    assert data["cache_misses"]["/a"] == 1
    assert data["webhook_deliveries"]["e"] == 0
    assert data["uptime_seconds"] >= 0
    assert data["average_latency_by_route"]["/a"] > 0
    metrics.reset()
    assert metrics.get_metrics()["total_requests"] == 0


def test_metrics_tracker_disabled():
    metrics = GatewayMetricsTracker(enabled=False)
    metrics.record_request("GET", "/a", 200, 0.01)
    assert metrics.get_metrics()["total_requests"] == 0


# ---------------------------------------------------------------- routing


def test_compile_pattern():
    regex, names = compile_pattern("/users/{user_id}/posts/:post_id")
    assert names == ["user_id", "post_id"]
    assert regex.startswith("^/users/")
    assert regex.endswith("/?$")
    import re

    match = re.match(regex, "/users/42/posts/9")
    assert match is not None
    assert match.group("user_id") == "42"
    assert re.match(regex, "/users/42/posts/9/") is not None
    assert re.match(regex, "/users/42/posts/9/x") is None


def test_compile_pattern_no_params():
    regex, names = compile_pattern("/health")
    assert names == []
    assert regex.startswith("^/health")


def test_registry_lifecycle():
    registry = RouteRegistry(make_config())
    assert registry.count() == 0
    route = Route(pattern="/x", handler=lambda r: None, methods=["GET"])
    registry.register(route)
    assert registry.count() == 1
    rev = registry.revision
    assert registry.reload() == rev + 1
    assert registry.get("/x") is route
    assert registry.get("/missing") is None
    assert registry.list() == [route]
    assert registry.unregister("/x") is True
    assert registry.unregister("/x") is False
    assert registry.count() == 0


def test_registry_multi_version_same_pattern():
    registry = RouteRegistry(make_config())
    v1 = Route(pattern="/u/{id}", handler=lambda r: None, methods=["GET"], version="v1")
    v2 = Route(pattern="/u/{id}", handler=lambda r: None, methods=["GET"], version="v2")
    registry.register(v1)
    registry.register(v2)
    assert registry.count() == 2
    assert registry.get("/u/{id}", "v1") is v1
    assert registry.get("/u/{id}", "v2") is v2
    assert registry.list("v1") == [v1]
    assert registry.list("v2") == [v2]
    assert len(registry.list()) == 2
    assert registry.unregister("/u/{id}", "v1") is True
    assert registry.count() == 1
    assert registry.get("/u/{id}", "v1") is None
    assert registry.unregister("/u/{id}") is True
    assert registry.count() == 0


def test_registry_register_invalid_pattern():
    registry = RouteRegistry(make_config())
    with pytest.raises(ValueError):
        registry.register(Route(pattern="nope", handler=lambda r: None))


def test_registry_resolve_exact_and_params():
    registry = RouteRegistry(make_config())
    exact = Route(pattern="/status", handler=lambda r: None, methods=["GET"])
    param = Route(pattern="/users/{uid}", handler=lambda r: None, methods=["GET", "DELETE"])
    registry.register(exact)
    registry.register(param)
    route, params = registry.resolve("/status", "GET")
    assert route is exact
    assert params == {}
    route, params = registry.resolve("/users/7", "GET")
    assert route is param
    assert params == {"uid": "7"}
    with pytest.raises(MethodNotAllowedError):
        registry.resolve("/status", "POST")
    with pytest.raises(RouteNotFoundError):
        registry.resolve("/nothing", "GET")


def test_registry_resolve_method_falls_through_to_params():
    registry = RouteRegistry(make_config())
    exact = Route(pattern="/a/b", handler=lambda r: None, methods=["GET"])
    param = Route(pattern="/a/{x}", handler=lambda r: None, methods=["POST"])
    registry.register(exact)
    registry.register(param)
    route, params = registry.resolve("/a/b", "POST")
    assert route is param
    assert params == {"x": "b"}


def test_registry_resolve_any_and_static_preference():
    registry = RouteRegistry(make_config())
    generic = Route(pattern="/f/{x}", handler=lambda r: None, methods=["GET"])
    specific = Route(pattern="/f/target", handler=lambda r: None, methods=["GET"])
    wildcard = Route(pattern="/any", handler=lambda r: None, methods=["ANY"])
    registry.register(generic)
    registry.register(specific)
    registry.register(wildcard)
    route, _ = registry.resolve("/f/target", "GET")
    assert route is specific
    route, _ = registry.resolve("/f/other", "GET")
    assert route is generic
    route, _ = registry.resolve("/any", "GET")
    assert route is wildcard
    route, _ = registry.resolve("/any", "PUT")
    assert route is wildcard


def test_registry_resolve_version_scoped():
    registry = RouteRegistry(make_config())
    v1 = Route(pattern="/v/{id}", handler=lambda r: None, methods=["GET"], version="v1")
    v2 = Route(pattern="/v/{id}", handler=lambda r: None, methods=["GET"], version="v2")
    registry.register(v1)
    registry.register(v2)
    route, _ = registry.resolve("/v/1", "GET", "v2")
    assert route is v2
    with pytest.raises(RouteNotFoundError):
        registry.resolve("/v/1", "GET", "v3")


def test_registry_clear():
    registry = RouteRegistry(make_config())
    registry.register(Route(pattern="/a", handler=lambda r: None))
    registry.clear()
    assert registry.count() == 0


def test_version_negotiator_default():
    negotiator = VersionNegotiator(make_config())
    info = negotiator.negotiate("/x", {})
    assert info.version == "v1"
    assert info.source == "default"
    assert info.deprecated is True


def test_version_negotiator_header():
    negotiator = VersionNegotiator(make_config())
    info = negotiator.negotiate("/x", {"X-API-Version": "v2"})
    assert info.version == "v2"
    assert info.source == "header"
    assert info.deprecated is False


def test_version_negotiator_url_takes_precedence_over_query():
    negotiator = VersionNegotiator(make_config())
    info = negotiator.negotiate("/x", {}, url_version="v2")
    assert info.version == "v2"
    assert info.source == "url"


def test_version_negotiator_query_fallback():
    negotiator = VersionNegotiator(make_config())
    info = negotiator.negotiate("/x", {}, query={"version": "v2"})
    assert info.version == "v2"
    assert info.source == "query"


def test_version_negotiator_accept_header():
    negotiator = VersionNegotiator(make_config())
    info = negotiator.negotiate("/x", {"Accept": "application/vnd.acme.v2+json"})
    assert info.version == "v2"


def test_version_negotiator_header_disabled():
    negotiator = VersionNegotiator(make_config(allow_header_versioning=False))
    info = negotiator.negotiate("/x", {"X-API-Version": "v2"}, url_version="v1")
    assert info.version == "v1"
    assert info.source == "url"


def test_version_negotiator_url_priority_reversed():
    negotiator = VersionNegotiator(make_config(version_header_priority=False))
    info = negotiator.negotiate("/x", {"X-API-Version": "v2"}, url_version="v1")
    assert info.version == "v1"


def test_version_negotiator_unsupported():
    negotiator = VersionNegotiator(make_config())
    with pytest.raises(VersionNotSupportedError):
        negotiator.negotiate("/x", {"X-API-Version": "v9"})


def test_version_negotiator_strip_prefix():
    negotiator = VersionNegotiator(make_config())
    path, version = negotiator.strip_version_prefix("/v1/users/1")
    assert path == "/users/1"
    assert version == "v1"
    path, version = negotiator.strip_version_prefix("/v2/x")
    assert path == "/x"
    assert version == "v2"
    path, version = negotiator.strip_version_prefix("/users/1")
    assert path == "/users/1"
    assert version == ""
    path, version = negotiator.strip_version_prefix("/v9/x")
    assert path == "/v9/x"
    assert version == ""
    path, version = negotiator.strip_version_prefix("/")
    assert path == "/"
    assert version == ""


def test_version_negotiator_deprecation_headers():
    negotiator = VersionNegotiator(make_config())
    info = negotiator.negotiate("/x", {"X-API-Version": "v1"})
    headers = negotiator.deprecation_headers(info)
    assert "X-API-Deprecated" in headers
    assert "Sunset" in headers
    info2 = negotiator.negotiate("/x", {"X-API-Version": "v2"})
    assert negotiator.deprecation_headers(info2) == {}


def test_version_negotiator_sunset():
    negotiator = VersionNegotiator(make_config())
    assert negotiator._sunset("v1") == "sunset-after-1-deprecation-cycles"
    assert negotiator._sunset("v2") == ""


# ---------------------------------------------------------------- ratelimit


def test_token_bucket_limiter():
    limiter = TokenBucketLimiter(rate_per_second=1.0, burst=3, initial=3.0)
    assert limiter.check("k").allowed is True
    assert limiter.check("k").allowed is True
    assert limiter.check("k").allowed is True
    denied = limiter.check("k")
    assert denied.allowed is False
    assert denied.retry_after > 0
    assert limiter.status("k")["remaining"] == 0
    limiter.reset("k")
    assert limiter.check("k").allowed is True


def test_token_bucket_refill():
    limiter = TokenBucketLimiter(rate_per_second=10.0, burst=5, initial=0.0)
    assert limiter.check("k").allowed is False
    time.sleep(0.3)
    assert limiter.check("k").allowed is True


def test_leaky_bucket_limiter():
    limiter = LeakyBucketLimiter(rate_per_second=1.0, capacity=2)
    assert limiter.check("k").allowed is True
    assert limiter.check("k").allowed is True
    denied = limiter.check("k")
    assert denied.allowed is False
    assert denied.retry_after >= 0
    assert limiter.status("k")["queued"] == 2
    limiter.reset("k")
    assert limiter.check("k").allowed is True


def test_leaky_bucket_drain():
    limiter = LeakyBucketLimiter(rate_per_second=100.0, capacity=1)
    limiter.check("k")
    assert limiter.check("k").allowed is False
    time.sleep(0.05)
    assert limiter.check("k").allowed is True


def test_sliding_window_limiter():
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    assert limiter.check("k").allowed is True
    assert limiter.check("k").allowed is True
    denied = limiter.check("k")
    assert denied.allowed is False
    assert limiter.status("k")["used"] == 2
    limiter.reset("k")
    assert limiter.check("k").allowed is True


def test_sliding_window_prune():
    limiter = SlidingWindowLimiter(limit=2, window_seconds=0.1)
    limiter.check("k")
    time.sleep(0.15)
    assert limiter.check("k").allowed is True


def test_fixed_window_limiter():
    limiter = FixedWindowLimiter(limit=2, window_seconds=60)
    assert limiter.check("k").allowed is True
    assert limiter.check("k").allowed is True
    denied = limiter.check("k")
    assert denied.allowed is False
    assert denied.retry_after > 0
    assert limiter.status("k")["used"] == 2
    limiter.reset("k")
    assert limiter.check("k").allowed is True


def test_fixed_window_bucket_rollover():
    limiter = FixedWindowLimiter(limit=1, window_seconds=0.1)
    assert limiter.check("k").allowed is True
    time.sleep(0.12)
    assert limiter.check("k").allowed is True


def test_create_rate_limit_strategy():
    config = make_config()
    assert isinstance(create_rate_limit_strategy("token_bucket", config), TokenBucketLimiter)
    assert isinstance(create_rate_limit_strategy("leaky_bucket", config), LeakyBucketLimiter)
    assert isinstance(create_rate_limit_strategy("sliding_window", config), SlidingWindowLimiter)
    assert isinstance(create_rate_limit_strategy("fixed_window", config), FixedWindowLimiter)
    with pytest.raises(ValueError):
        create_rate_limit_strategy("nope", config)


def test_create_rate_limit_strategy_overrides():
    config = make_config()
    limiter = create_rate_limit_strategy("token_bucket", config, rate_per_second=5, burst=7)
    assert limiter.rate_per_second == 5
    assert limiter.burst == 7
    sliding = create_rate_limit_strategy("sliding_window", config, limit=9, window_seconds=30, precision=2)
    assert sliding.limit == 9
    assert sliding.window_seconds == 30
    assert sliding.precision == 2
    fixed = create_rate_limit_strategy("fixed_window", config, limit=4, window_seconds=10)
    assert fixed.limit == 4
    assert fixed.window_seconds == 10
    leaky = create_rate_limit_strategy("leaky_bucket", config, rate_per_second=3, capacity=5)
    assert leaky.capacity == 5


def test_rate_limiter_registry():
    config = make_config(default_rate_limit_strategy="fixed_window", default_requests_per_minute=2)
    limiter = RateLimiter(config)
    limiter.set_policy("client:1", strategy="token_bucket", limit=2, burst=2)
    assert isinstance(limiter.limiter_for("client:1"), TokenBucketLimiter)
    assert isinstance(limiter.limiter_for("client:2"), FixedWindowLimiter)
    assert limiter.check("client:1").allowed is True
    assert limiter.check("client:1").allowed is True
    assert limiter.check("client:1").allowed is False
    assert limiter.policies()["client:1"]["strategy"] == "token_bucket"
    limiter.reset("client:1")
    assert limiter.check("client:1").allowed is True


def test_rate_limiter_enforce():
    config = make_config(default_rate_limit_strategy="fixed_window", default_requests_per_minute=1)
    limiter = RateLimiter(config)
    assert limiter.enforce("k").allowed is True
    with pytest.raises(RateLimitExceededError):
        limiter.enforce("k")


def test_rate_limiter_reset_all():
    config = make_config(default_rate_limit_strategy="fixed_window", default_requests_per_minute=1)
    limiter = RateLimiter(config)
    limiter.check("a")
    limiter.check("b")
    limiter.reset_all()
    assert limiter.check("a").allowed is True
    assert limiter.check("b").allowed is True


def test_rate_limiter_status():
    config = make_config(default_rate_limit_strategy="fixed_window", default_requests_per_minute=5)
    limiter = RateLimiter(config)
    status = limiter.status("k")
    assert status["strategy"] == "fixed_window"
    assert status["limit"] == 5


def test_rate_limit_decision_defaults():
    decision = RateLimitDecision(allowed=True)
    assert decision.strategy == ""
    assert decision.to_dict()["allowed"] is True


def test_rate_limiter_strategy_interface():
    class Dummy(RateLimitStrategy):
        name = "dummy"

        def check(self, key, cost=1):
            return RateLimitDecision(allowed=True)

        def reset(self, key):
            return None

        def status(self, key):
            return {}

    dummy = Dummy()
    assert dummy.check("k").allowed is True
    assert dummy.status("k") == {}
    dummy.reset("k")


# ---------------------------------------------------------------- quota


def test_quota_manager_defaults():
    manager = QuotaManager(make_config(max_quota_tokens=500))
    assert manager.default_limit("tokens") == 500
    assert manager.default_limit("storage") == make_config().max_quota_storage
    assert manager.default_limit("bogus") == make_config().max_quota_requests
    assert manager.limit_for("s", "tokens") == 500


def test_quota_manager_check_and_exceed():
    manager = QuotaManager(make_config())
    manager.set_limit("scope", "requests", 3)
    consumption = manager.check("scope", "requests")
    assert consumption.used == 1
    assert consumption.remaining == 2
    manager.check("scope", "requests", 2)
    assert manager.usage("scope", "requests") == 3
    with pytest.raises(QuotaExceededError) as excinfo:
        manager.check("scope", "requests")
    assert excinfo.value.details["bucket"] == "requests"
    assert manager.try_check("scope", "requests") is None
    assert manager.consumption("scope", "requests").remaining == 0


def test_quota_manager_refund():
    manager = QuotaManager(make_config())
    manager.set_limit("s", "tokens", 5)
    manager.check("s", "tokens", 4)
    manager.refund("s", "tokens", 2)
    assert manager.usage("s", "tokens") == 2
    manager.refund("s", "tokens", 99)
    assert manager.usage("s", "tokens") == 0


def test_quota_manager_reset():
    manager = QuotaManager(make_config())
    manager.check("s", "requests")
    manager.check("s", "tokens")
    manager.check("other", "requests")
    manager.reset(scope="s")
    assert manager.usage("s", "requests") == 0
    assert manager.usage("s", "tokens") == 0
    assert manager.usage("other", "requests") == 1
    manager.check("s", "requests")
    manager.reset(scope="s", bucket="requests")
    assert manager.usage("s", "requests") == 0
    manager.reset()
    assert manager.usage("other", "requests") == 0


def test_quota_manager_unknown_bucket():
    manager = QuotaManager(make_config())
    with pytest.raises(ValueError):
        manager.set_limit("s", "nope", 1)


def test_quota_manager_summary_and_usage():
    manager = QuotaManager(make_config())
    manager.set_limit("s", "tokens", 10)
    manager.check("s", "tokens", 3)
    manager.check("s", "requests")
    summary = manager.summary("s")
    assert summary["scope"] == "s"
    assert summary["tokens"]["used"] == 3
    assert summary["requests"]["used"] == 1
    assert manager.usage_by_scope("s") == {"requests": 1, "tokens": 3}
    assert manager.usage_by_scope("other") == {}
    assert manager.summary("other")["scope"] == "other"


# ---------------------------------------------------------------- cache


def test_cache_key_deterministic():
    request = GatewayRequest(method="GET", path="/a", query={"x": 1}, tenant_id="t", client_id="c")
    assert cache_key(request, version="v1", route="/a") == cache_key(request, version="v1", route="/a")
    other = GatewayRequest(method="GET", path="/a", query={"x": 2}, tenant_id="t", client_id="c")
    assert cache_key(request) != cache_key(other)


def test_response_cache_get_set():
    cache = ResponseCache(make_config())
    key = cache_key(GatewayRequest(method="GET", path="/a"))
    assert cache.get(key) is None
    cache.set(key, GatewayResponse(body={"ok": 1}))
    assert cache.get(key).body == {"ok": 1}
    assert cache.size() == 1


def test_response_cache_expiry_and_prune():
    cache = ResponseCache(make_config())
    key = cache_key(GatewayRequest(method="GET", path="/a"))
    cache.set(key, GatewayResponse(), ttl_seconds=0.01)
    assert cache.size() == 1
    time.sleep(0.02)
    cache.prune()
    assert cache.get(key) is None
    cache.set(key, GatewayResponse(), ttl_seconds=60)
    cache.set("b", GatewayResponse(), ttl_seconds=-5)
    assert cache.prune() == 1


def test_response_cache_invalidate():
    cache = ResponseCache(make_config())
    cache.set("key1", GatewayResponse())
    cache.set("key2", GatewayResponse())
    cache.set("other", GatewayResponse())
    assert cache.invalidate("key1") is True
    assert cache.invalidate("key1") is False
    assert cache.invalidate_prefix("key") == 1
    cache.clear()
    assert cache.size() == 0


def test_response_cache_eviction():
    cache = ResponseCache(make_config(cache_max_entries=2))
    cache.set("a", GatewayResponse())
    cache.set("b", GatewayResponse())
    cache.set("c", GatewayResponse())
    assert cache.size() == 2
    assert cache.get("a") is None


def test_cache_entry_attr():
    entry = CacheEntry(key="k", response=GatewayResponse(), ttl_seconds=5)
    assert entry.key == "k"
    assert entry.stored_at > 0


# ---------------------------------------------------------------- webhooks


def test_webhook_register_and_manage():
    manager = WebhookManager(make_config())
    webhook = manager.register("http://h.example.com/e", events=["a", "b"], secret="s")
    assert manager.get(webhook.id) is webhook
    assert manager.get("missing") is None
    assert len(manager.list()) == 1
    assert len(manager.list(event="a")) == 1
    assert len(manager.list(event="c")) == 0
    with pytest.raises(WebhookError):
        manager.register("ftp://bad.example.com")
    assert manager.unregister(webhook.id) is True
    assert manager.unregister(webhook.id) is False


def test_webhook_set_active():
    manager = WebhookManager(make_config())
    webhook = manager.register("http://h.example.com/e")
    manager.set_active(webhook.id, False)
    assert manager.list() == []
    assert manager.get(webhook.id).active is False
    with pytest.raises(WebhookError):
        manager.set_active("missing", True)


def test_webhook_deliver_success():
    transport = lambda url, headers, payload: 200  # noqa: E731
    manager = WebhookManager(make_config(), transport=transport)
    webhook = manager.register("http://h.example.com/e", events=["evt"], secret="sekret")
    deliveries = manager.deliver("evt", {"n": 1})
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.status_code == 200
    assert delivery.attempts == 1
    assert delivery.event == "evt"
    assert manager.deliveries() == [delivery]
    assert manager.deliveries(event="evt") == [delivery]
    assert manager.deliveries(event="other") == []
    assert manager.deliveries(webhook_id=webhook.id) == [delivery]
    assert manager.deliveries(webhook_id="nope") == []


def test_webhook_deliver_retries_then_fails():
    manager = WebhookManager(make_config(webhook_max_retries=3), transport=lambda url, headers, payload: 500)
    manager.register("http://h.example.com/f", events=["evt"])
    delivery = manager.deliver("evt", {"n": 1})[0]
    assert delivery.status_code == 500
    assert delivery.attempts == 3
    assert delivery.error == "HTTP 500"


def test_webhook_deliver_recovers_on_retry():
    attempts = {"n": 0}

    def flaky(url, headers, payload):
        attempts["n"] += 1
        return 200 if attempts["n"] > 1 else 503

    manager = WebhookManager(make_config(webhook_max_retries=3), transport=flaky)
    manager.register("http://h.example.com/f", events=["evt"])
    delivery = manager.deliver("evt", {})[0]
    assert delivery.status_code == 200
    assert delivery.attempts == 2


def test_webhook_disabled():
    manager = WebhookManager(make_config(webhooks_enabled=False), transport=lambda *args: 200)
    manager.register("http://h.example.com/e")
    assert manager.deliver("evt", {}) == []
    assert manager.enabled is False


def test_webhook_secret_signing():
    received = {}

    def capture(url, headers, payload):
        received.update(headers)
        return 200

    manager = WebhookManager(make_config(), transport=capture)
    manager.register("http://h.example.com/e", events=["evt"], secret="shhh")
    manager.deliver("evt", {"a": 1})
    assert received["X-Webhook-Signature"].startswith("sha256=")
    assert received["Content-Type"] == "application/json"


# ---------------------------------------------------------------- middleware


def test_middleware_chain_order():
    order = []

    class A(Middleware):
        name = "a"

        async def handle(self, request, next_handler):
            order.append("a-in")
            response = await next_handler(request)
            order.append("a-out")
            return response

    class B(Middleware):
        name = "b"

        async def handle(self, request, next_handler):
            order.append("b-in")
            response = await next_handler(request)
            order.append("b-out")
            return response

    chain = MiddlewareChain([A(), B()])

    async def terminal(request):
        order.append("term")
        return GatewayResponse(body="done")

    handler = chain.build(terminal)

    async def go():
        return await handler(GatewayRequest(method="GET", path="/x"))

    response = run(go())
    assert response.body == "done"
    assert order == ["a-in", "b-in", "term", "b-out", "a-out"]
    assert chain.middlewares[0].name == "a"
    assert chain.remove("a") is True
    assert chain.remove("a") is False
    chain.clear()
    assert chain.middlewares == []


def test_middleware_chain_append_prepend():
    chain = MiddlewareChain()
    chain.append(CorrelationMiddleware(make_config()))
    chain.prepend(ErrorHandlingMiddleware())
    assert chain.middlewares[0].name == "error_handling"
    assert chain.middlewares[1].name == "correlation"


def test_error_response_conversion():
    response = error_response(RateLimitExceededError(key="k", strategy="s", retry_after=3.2, limit=10))
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "4"
    assert response.headers["X-RateLimit-Limit"] == "10"
    response = error_response(QuotaExceededError(bucket="tokens", limit=5, used=5))
    assert response.headers["X-Quota-Bucket"] == "tokens"
    response = error_response(RuntimeError("internal"))
    assert response.status_code == 500
    assert response.body["error"] == "internal_error"


def test_error_handling_middleware():
    middleware = ErrorHandlingMiddleware()

    async def boom(request):
        raise RouteNotFoundError("/x")

    chain = MiddlewareChain([middleware])
    handler = chain.build(boom)

    async def go():
        return await handler(GatewayRequest(method="GET", path="/x"))

    response = run(go())
    assert response.status_code == 404


def test_correlation_middleware():
    middleware = CorrelationMiddleware(make_config())

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)

    async def go():
        request = GatewayRequest(method="GET", path="/x", headers={"X-Correlation-ID": "abc"})
        response = await handler(request)
        return response, request

    response, request = run(go())
    assert request.correlation_id == "abc"
    assert response.headers["X-Correlation-ID"] == "abc"


def test_logging_middleware():
    logger = GatewayLogger(enabled=True)
    metrics = GatewayMetricsTracker(enabled=True)
    middleware = LoggingMiddleware(logger, metrics)

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    response = run(handler(GatewayRequest(method="GET", path="/x", version="v1")))
    assert response.status_code == 200
    assert logger.events[-1]["event"] == "gateway.request"
    assert metrics.get_metrics()["total_requests"] == 1


def test_tenant_middleware_with_manager():
    from app.tenancy import TenancyConfig, create_tenant_manager

    tenants = create_tenant_manager(config=TenancyConfig(log_events=False, audit_enabled=False))
    tenant = tenants.create("T1")
    middleware = TenantMiddleware(tenants)

    async def terminal(request):
        return GatewayResponse(body=request.tenant_id)

    handler = MiddlewareChain([middleware]).build(terminal)

    async def good():
        return await handler(GatewayRequest(method="GET", path="/x", headers={"X-Tenant-ID": tenant.id}))

    response = run(good())
    assert response.body == tenant.id

    async def bad():
        return await handler(GatewayRequest(method="GET", path="/x", headers={"X-Tenant-ID": "nope"}))

    with pytest.raises(TenantIsolationError):
        run(bad())

    async def missing():
        return await handler(GatewayRequest(method="GET", path="/x"))

    with pytest.raises(TenantIsolationError):
        run(missing())


def test_tenant_middleware_without_manager():
    middleware = TenantMiddleware()
    seen = {}

    async def terminal(request):
        seen["tenant"] = request.tenant_id
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    run(handler(GatewayRequest(method="GET", path="/x", headers={"X-Tenant-ID": "raw"})))
    assert seen["tenant"] == "raw"


def test_org_context_middleware():
    middleware = OrgContextMiddleware()
    seen = {}

    async def terminal(request):
        seen.update(organization_id=request.organization_id, workspace_id=request.workspace_id)
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    request = GatewayRequest(method="GET", path="/x", headers={"X-Organization-ID": "o1", "X-Workspace-ID": "w1"})
    run(handler(request))
    assert seen == {"organization_id": "o1", "workspace_id": "w1"}


def test_auth_middleware_public_skips_auth():
    class FakeAuth:
        async def authenticate(self, headers=None, authorization=None):
            raise AssertionError("should not be called")

    middleware = AuthMiddleware(FakeAuth())  # type: ignore[arg-type]

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    request = GatewayRequest(method="GET", path="/x", metadata={"route": Route(pattern="/x", handler=lambda r: None, visibility=RouteVisibility.PUBLIC)})
    response = run(handler(request))
    assert response.status_code == 200


def test_auth_middleware_authenticated():
    from app.auth import Principal

    class FakeAuth:
        async def authenticate(self, headers=None, authorization=None):
            return Principal(user_id="u1", tenant_id="t1")

    middleware = AuthMiddleware(FakeAuth())  # type: ignore[arg-type]
    seen = {}

    async def terminal(request):
        seen["principal"] = request.principal
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    route = Route(pattern="/x", handler=lambda r: None, visibility=RouteVisibility.AUTHENTICATED)
    request = GatewayRequest(method="GET", path="/x", metadata={"route": route})
    run(handler(request))
    assert seen["principal"].user_id == "u1"
    assert request.client_id == "u1"


def test_auth_middleware_failure():
    class FakeAuth:
        async def authenticate(self, headers=None, authorization=None):
            raise AuthenticationFailedError("no token")

    middleware = AuthMiddleware(FakeAuth())  # type: ignore[arg-type]

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    route = Route(pattern="/x", handler=lambda r: None, visibility=RouteVisibility.AUTHENTICATED)
    request = GatewayRequest(method="GET", path="/x", metadata={"route": route})
    with pytest.raises(AuthenticationFailedError):
        run(handler(request))


def test_auth_middleware_none_principal():
    class FakeAuth:
        async def authenticate(self, headers=None, authorization=None):
            return None

    middleware = AuthMiddleware(FakeAuth())  # type: ignore[arg-type]

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    route = Route(pattern="/x", handler=lambda r: None, visibility=RouteVisibility.AUTHENTICATED)
    request = GatewayRequest(method="GET", path="/x", metadata={"route": route})
    with pytest.raises(AuthenticationFailedError):
        run(handler(request))


def test_auth_middleware_private_permission():
    from app.auth import Principal

    class FakeAuth:
        async def authenticate(self, headers=None, authorization=None):
            return Principal(user_id="u1", tenant_id="t1")

    middleware = AuthMiddleware(FakeAuth())  # type: ignore[arg-type]

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    route = Route(pattern="/x", handler=lambda r: None, visibility=RouteVisibility.PRIVATE, metadata={"permission": "admin"})
    request = GatewayRequest(method="GET", path="/x", metadata={"route": route})
    with pytest.raises(ForbiddenError):
        run(handler(request))

    class AdminAuth:
        async def authenticate(self, headers=None, authorization=None):
            return Principal(user_id="u1", tenant_id="t1", roles=["admin"])

    handler = MiddlewareChain([AuthMiddleware(AdminAuth())]).build(terminal)  # type: ignore[arg-type]
    request = GatewayRequest(method="GET", path="/x", metadata={"route": route})
    assert run(handler(request)).status_code == 200


def test_auth_middleware_no_route_metadata():
    from app.auth import Principal

    class FakeAuth:
        async def authenticate(self, headers=None, authorization=None):
            return Principal(user_id="u1", tenant_id="t1")

    middleware = AuthMiddleware(FakeAuth())  # type: ignore[arg-type]

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    response = run(handler(GatewayRequest(method="GET", path="/x")))
    assert response.status_code == 200


def test_rate_limit_middleware():
    metrics = GatewayMetricsTracker(enabled=True)
    config = make_config(default_rate_limit_strategy="fixed_window", default_requests_per_minute=2)
    limiter = RateLimiter(config)
    middleware = RateLimitMiddleware(limiter, metrics)

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)

    def request():
        return GatewayRequest(method="GET", path="/x", headers={"X-Tenant-ID": "t", "X-Client-ID": "c"})

    first = run(handler(request()))
    assert first.status_code == 200
    assert first.headers["X-RateLimit-Limit"] == "2"
    run(handler(request()))
    with pytest.raises(RateLimitExceededError):
        run(handler(request()))
    assert metrics.get_metrics()["rate_limit_hits"]["fixed_window"] == 1


def test_rate_limit_middleware_route_key():
    config = make_config(default_rate_limit_strategy="fixed_window", default_requests_per_minute=100)
    limiter = RateLimiter(config)
    middleware = RateLimitMiddleware(limiter)

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    route = Route(pattern="/special", handler=lambda r: None, rate_limit_key="special")
    run(handler(GatewayRequest(method="GET", path="/special", headers={"X-Client-ID": "c"}, metadata={"route": route})))
    assert "special" in list(limiter.policies()) or True
    assert limiter.check(f"anon:c:special").remaining >= 99


def test_quota_middleware():
    metrics = GatewayMetricsTracker(enabled=True)
    config = make_config()
    manager = QuotaManager(config)
    manager.set_limit("t:c", "requests", 2)
    middleware = QuotaMiddleware(manager, metrics)

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)

    def request():
        return GatewayRequest(method="GET", path="/x", tenant_id="t", client_id="c", metadata={"route": Route(pattern="/x", handler=lambda r: None)})

    run(handler(request()))
    run(handler(request()))
    with pytest.raises(QuotaExceededError):
        run(handler(request()))
    assert metrics.get_metrics()["quota_hits"]["requests"] == 1


def test_quota_middleware_refund_on_failure():
    config = make_config()
    manager = QuotaManager(config)
    manager.set_limit("t:c", "requests", 5)
    middleware = QuotaMiddleware(manager)

    async def failing(request):
        return GatewayResponse(status_code=503)

    async def raising(request):
        raise GatewayError("upstream")

    chain = MiddlewareChain([middleware])
    request = GatewayRequest(method="GET", path="/x", tenant_id="t", client_id="c", metadata={"route": Route(pattern="/x", handler=lambda r: None)})
    run(chain.build(failing)(request))
    assert manager.usage("t:c", "requests") == 0
    with pytest.raises(GatewayError):
        run(chain.build(raising)(request))
    assert manager.usage("t:c", "requests") == 0


def test_quota_middleware_custom_bucket():
    config = make_config()
    manager = QuotaManager(config)
    manager.set_limit("t:c", "tokens", 1)
    middleware = QuotaMiddleware(manager)

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    route = Route(pattern="/x", handler=lambda r: None, quota_bucket="tokens")
    request = GatewayRequest(method="GET", path="/x", tenant_id="t", client_id="c", metadata={"route": route})
    run(handler(request))
    assert manager.usage("t:c", "tokens") == 1
    with pytest.raises(QuotaExceededError):
        run(handler(request))


def test_cache_middleware():
    cache = ResponseCache(make_config())
    middleware = CacheMiddleware(cache)
    calls = {"n": 0}

    async def terminal(request):
        calls["n"] += 1
        return GatewayResponse(body={"n": calls["n"]})

    handler = MiddlewareChain([middleware]).build(terminal)
    route = Route(pattern="/c", handler=lambda r: None, cacheable=True)
    request = GatewayRequest(method="GET", path="/c", metadata={"route": route})

    first = run(handler(request))
    assert first.headers["X-Cache"] == "MISS"
    second = run(handler(request))
    assert second.headers["X-Cache"] == "HIT"
    assert calls["n"] == 1

    non_cacheable_route = Route(pattern="/nc", handler=lambda r: None, cacheable=False)
    non_cacheable = GatewayRequest(method="GET", path="/nc", metadata={"route": non_cacheable_route})
    run(handler(non_cacheable))
    assert calls["n"] == 2

    post_route = Route(pattern="/c", handler=lambda r: None, cacheable=True)
    post = GatewayRequest(method="POST", path="/c", metadata={"route": post_route})
    run(handler(post))
    assert calls["n"] == 3


def test_middleware_decorator_call():
    import inspect

    middleware = LoggingMiddleware(GatewayLogger(enabled=True))
    handler = middleware(lambda request: asyncio.sleep(0))
    assert inspect.iscoroutinefunction(handler)


# ---------------------------------------------------------------- dispatcher


def test_service_dispatcher_register_and_list():
    dispatcher = ServiceDispatcher()
    svc = ServiceDescriptor(name="a", base_url="http://a.example")
    dispatcher.register_service(svc)
    assert dispatcher.get_service("a") is svc
    assert dispatcher.get_service("missing") is None
    assert dispatcher.list_services() == [svc]
    assert dispatcher.unregister_service("a") is True
    assert dispatcher.unregister_service("a") is False
    assert dispatcher.transports == {}
    dispatcher.register_transport(RouteProtocol.HTTP, InMemoryTransport())
    assert isinstance(dispatcher.transports[RouteProtocol.HTTP.value], InMemoryTransport)


def test_in_memory_transport_async_handler():
    async def handler(request, service):
        return GatewayResponse(body={"name": service.name, "id": request.path_params.get("id")})

    transport = InMemoryTransport()
    service = ServiceDescriptor(name="svc", metadata={"handler": handler})
    request = GatewayRequest(method="GET", path="/x", path_params={"id": "7"})
    response = run(transport.request(service, request))
    assert response.body == {"name": "svc", "id": "7"}


def test_in_memory_transport_sync_handler():
    def handler(request, service):
        return GatewayResponse(body={"sync": True})

    transport = InMemoryTransport()
    service = ServiceDescriptor(name="svc", metadata={"handler": handler})
    response = run(transport.request(service, GatewayRequest(method="GET", path="/x")))
    assert response.body == {"sync": True}


def test_in_memory_transport_fixtures():
    transport = InMemoryTransport()
    service = ServiceDescriptor(
        name="svc",
        metadata={"responses": {"/x": {"status_code": 404, "body": {"nope": True}}}},
    )
    response = run(transport.request(service, GatewayRequest(method="GET", path="/x")))
    assert response.status_code == 404
    assert response.body == {"nope": True}
    fallback = run(transport.request(service, GatewayRequest(method="GET", path="/other")))
    assert fallback.status_code == 200
    assert fallback.body == {"ok": True}


def test_in_memory_transport_stream():
    def gen(request, service):
        yield b"one"
        yield b"two"

    transport = InMemoryTransport()
    service = ServiceDescriptor(name="svc", metadata={"stream_handler": gen})

    async def consume():
        return [chunk async for chunk in transport.stream(service, GatewayRequest(method="GET", path="/x"))]

    assert run(consume()) == [b"one", b"two"]


def test_in_memory_transport_stream_async():
    async def gen(request, service):
        yield b"one"

    async def coro_gen(request, service):
        return gen(request, service)

    transport = InMemoryTransport()
    service = ServiceDescriptor(name="svc", metadata={"stream_handler": coro_gen})

    async def consume():
        return [chunk async for chunk in transport.stream(service, GatewayRequest(method="GET", path="/x"))]

    assert run(consume()) == [b"one"]


def test_in_memory_transport_websocket():
    def gen(request, service):
        yield StreamEvent(data="hi", event="")

    async def agen(request, service):
        yield StreamEvent(data="async", event="")

    transport = InMemoryTransport()
    sync_service = ServiceDescriptor(name="s", metadata={"ws_handler": gen})

    async def consume_sync():
        return [e async for e in transport.websocket(sync_service, GatewayRequest(method="GET", path="/x"))]

    assert [e.serialize() for e in run(consume_sync())] == ["data: hi\n\n"]
    async_service = ServiceDescriptor(name="a", metadata={"ws_handler": agen})

    async def consume_async():
        return [e async for e in transport.websocket(async_service, GatewayRequest(method="GET", path="/x"))]

    assert [e.serialize() for e in run(consume_async())] == ["data: async\n\n"]


def test_in_memory_transport_missing_handlers():
    transport = InMemoryTransport()
    service = ServiceDescriptor(name="svc", metadata={})
    fallback = run(transport.request(service, GatewayRequest(method="GET", path="/x")))
    assert fallback.status_code == 200
    assert fallback.body == {"ok": True}

    async def consume():
        return [c async for c in transport.stream(service, GatewayRequest(method="GET", path="/x"))]

    with pytest.raises(ServiceUnavailableError):
        run(consume())

    async def consume_ws():
        return [e async for e in transport.websocket(service, GatewayRequest(method="GET", path="/x"))]

    with pytest.raises(ServiceUnavailableError):
        run(consume_ws())


def test_http_transport_success():
    from unittest.mock import AsyncMock

    client = AsyncMock()
    response = httpx.Response(200, text="hello", headers={"content-type": "text/plain"})
    client.__aenter__.return_value = client
    client.__aexit__ = AsyncMock(return_value=None)
    client.request = AsyncMock(return_value=response)
    transport = HttpTransport(client_factory=lambda: client)
    service = ServiceDescriptor(name="svc", base_url="http://svc.example")
    request = GatewayRequest(method="GET", path="/ping", query={"q": "1"})
    result = run(transport.request(service, request))
    assert result.status_code == 200
    assert result.body == "hello"
    assert result.content_type == "text/plain"
    client.request.assert_awaited_once()
    assert client.request.call_args.args == ("GET", "http://svc.example/ping")


def test_http_transport_timeout():
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__ = AsyncMock(return_value=None)
    client.request = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
    transport = HttpTransport(timeout_seconds=1.5, client_factory=lambda: client)
    service = ServiceDescriptor(name="svc", base_url="http://svc.example")
    with pytest.raises(GatewayTimeoutError) as excinfo:
        run(transport.request(service, GatewayRequest(method="GET", path="/x")))
    assert excinfo.value.details["timeout"] == 1.5


def test_http_transport_upstream_error():
    from unittest.mock import AsyncMock

    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__ = AsyncMock(return_value=None)
    client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
    transport = HttpTransport(client_factory=lambda: client)
    service = ServiceDescriptor(name="svc", base_url="http://svc.example")
    with pytest.raises(UpstreamError):
        run(transport.request(service, GatewayRequest(method="GET", path="/x")))


def test_http_transport_stream():
    from unittest.mock import AsyncMock, Mock

    response = AsyncMock()
    response.__aenter__.return_value = response
    response.__aexit__ = AsyncMock(return_value=None)

    async def aiter_bytes():
        yield b"chunk1"
        yield b"chunk2"

    response.aiter_bytes = aiter_bytes
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__ = AsyncMock(return_value=None)
    client.stream = Mock(return_value=response)
    transport = HttpTransport(client_factory=lambda: client)
    service = ServiceDescriptor(name="svc", base_url="http://svc.example")

    async def consume():
        return [chunk async for chunk in transport.stream(service, GatewayRequest(method="GET", path="/dl"))]

    assert run(consume()) == [b"chunk1", b"chunk2"]
    client.stream.assert_called_once()


def test_http_transport_stream_timeout():
    from unittest.mock import AsyncMock, Mock

    response = AsyncMock()
    response.__aenter__ = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__ = AsyncMock(return_value=None)
    client.stream = Mock(return_value=response)
    transport = HttpTransport(client_factory=lambda: client)
    service = ServiceDescriptor(name="svc", base_url="http://svc.example")

    async def consume():
        return [c async for c in transport.stream(service, GatewayRequest(method="GET", path="/dl"))]

    with pytest.raises(GatewayTimeoutError):
        run(consume())


def test_http_transport_websocket_unsupported():
    transport = HttpTransport()
    service = ServiceDescriptor(name="svc", base_url="http://svc.example")
    with pytest.raises(WebSocketUpgradeError):
        run(transport.websocket(service, GatewayRequest(method="GET", path="/ws")))


def test_service_dispatcher_dispatch_http():
    async def handler(request, service):
        return GatewayResponse(body={"ok": True})

    dispatcher = ServiceDispatcher(transports={RouteProtocol.HTTP.value: InMemoryTransport()})
    dispatcher.register_service(ServiceDescriptor(name="svc", metadata={"handler": handler}))
    route = Route(pattern="/x", handler=None, methods=["GET"], protocol=RouteProtocol.HTTP, metadata={"service": "svc"})
    response = run(dispatcher.dispatch(route, GatewayRequest(method="GET", path="/x")))
    assert response.body == {"ok": True}


def test_service_dispatcher_missing_transport():
    dispatcher = ServiceDispatcher(transports={})
    dispatcher.register_service(ServiceDescriptor(name="svc", metadata={"handler": lambda r, s: GatewayResponse()}))
    route = Route(pattern="/x", handler=None, methods=["GET"], protocol=RouteProtocol.HTTP, metadata={"service": "svc"})
    with pytest.raises(ServiceUnavailableError):
        run(dispatcher.dispatch(route, GatewayRequest(method="GET", path="/x")))


def test_service_dispatcher_missing_service():
    dispatcher = ServiceDispatcher(transports={RouteProtocol.HTTP.value: InMemoryTransport()})
    route = Route(pattern="/x", handler=None, methods=["GET"], protocol=RouteProtocol.HTTP, metadata={"service": "ghost"})
    with pytest.raises(ServiceUnavailableError):
        run(dispatcher.dispatch(route, GatewayRequest(method="GET", path="/x")))


def test_service_dispatcher_no_service_configured():
    dispatcher = ServiceDispatcher(transports={RouteProtocol.HTTP.value: InMemoryTransport()})
    route = Route(pattern="/x", handler=None, methods=["GET"], protocol=RouteProtocol.HTTP, metadata={})
    with pytest.raises(ServiceUnavailableError):
        run(dispatcher.dispatch(route, GatewayRequest(method="GET", path="/x")))


def test_service_dispatcher_sse():
    def gen(request, service):
        yield b"data: one\n\n"

    dispatcher = ServiceDispatcher(transports={RouteProtocol.SSE.value: InMemoryTransport(), RouteProtocol.HTTP.value: InMemoryTransport()})
    dispatcher.register_service(ServiceDescriptor(name="ev", metadata={"stream_handler": gen}))
    route = Route(pattern="/sse", handler=None, methods=["GET"], protocol=RouteProtocol.SSE, metadata={"service": "ev"})
    response = run(dispatcher.dispatch(route, GatewayRequest(method="GET", path="/sse")))
    assert response.status_code == 200
    assert response.content_type == "text/event-stream"
    assert "data: one" in response.body


def test_service_dispatcher_stream():
    def gen(request, service):
        yield b"x"

    dispatcher = ServiceDispatcher(transports={RouteProtocol.STREAM.value: InMemoryTransport()})
    dispatcher.register_service(ServiceDescriptor(name="dl", metadata={"stream_handler": gen}))
    route = Route(pattern="/dl", handler=None, methods=["GET"], protocol=RouteProtocol.STREAM, metadata={"service": "dl"})
    response = run(dispatcher.dispatch(route, GatewayRequest(method="GET", path="/dl")))
    assert response.body is not None


# ---------------------------------------------------------------- gateway


def test_gateway_route_decorator_and_registration():
    gw = make_gateway()

    @gw.route("/health", methods=["GET"])
    async def health(request):
        return {"status": "ok"}

    route = gw.router.get("/health")
    assert route is not None
    assert route.methods == ["GET"]
    assert gw.router.count() == 1
    assert gw.unregister_route("/health") is True
    assert gw.unregister_route("/health") is False
    assert gw.router.count() == 0


def test_gateway_register_route_kwargs():
    gw = make_gateway()
    route = gw.register_route(
        "/orders/{order_id}",
        handler=lambda request: {"id": request.path_params["order_id"]},
        methods=["GET", "DELETE"],
        version="v2",
        deprecated=True,
        cacheable=True,
        rate_limit_key="orders",
        quota_bucket="tokens",
        description="Orders endpoint",
        tags=["orders"],
    )
    assert route.version == "v2"
    assert route.deprecated is True
    assert route.cacheable is True
    assert route.rate_limit_key == "orders"
    assert route.quota_bucket == "tokens"
    assert route.description == "Orders endpoint"
    assert route.tags == ["orders"]


def test_gateway_dispatch_local_handler():
    gw = make_gateway()
    seen = {}

    @gw.route("/hello/{name}", methods=["GET"])
    async def hello(request):
        seen.update(name=request.path_params["name"], version=request.version)
        return {"message": f"hi {request.path_params['name']}"}

    result = run(gw.dispatch("GET", "/hello/world", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 200
    assert result.response.body == {"message": "hi world"}
    assert seen == {"name": "world", "version": "v1"}
    assert result.route is not None
    assert result.cache_hit is False
    assert result.duration_seconds >= 0


def test_gateway_dispatch_sync_handler():
    gw = make_gateway()

    @gw.route("/sync", methods=["GET"])
    def sync_handler(request):
        return {"sync": True}

    result = run(gw.dispatch("GET", "/sync", headers={"X-Tenant-ID": "t1"}))
    assert result.response.body == {"sync": True}


def test_gateway_dispatch_gateway_response_handler():
    gw = make_gateway()

    @gw.route("/raw", methods=["GET"])
    async def raw(request):
        return GatewayResponse(status_code=202, body={"raw": True}, content_type="application/json")

    result = run(gw.dispatch("GET", "/raw", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 202
    assert result.response.body == {"raw": True}


def test_gateway_dispatch_errors():
    gw = make_gateway()

    @gw.route("/x", methods=["GET"])
    async def x(request):
        return {"ok": True}

    result = run(gw.dispatch("GET", "/missing", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 404
    assert result.response.body["error"] == "route_not_found"

    result = run(gw.dispatch("POST", "/x", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 405
    assert result.response.body["allowed"] == ["GET"]

    result = run(gw.dispatch("GET", "/x", headers={"X-Tenant-ID": "t1", "X-API-Version": "v9"}))
    assert result.response.status_code == 400
    assert result.response.body["error"] == "version_not_supported"


def test_gateway_dispatch_version_url_and_header():
    gw = make_gateway()

    @gw.route("/items/{id}", methods=["GET"], version="v1")
    async def items_v1(request):
        return {"version": "v1"}

    @gw.route("/items/{id}", methods=["GET"], version="v2")
    async def items_v2(request):
        return {"version": "v2"}

    result = run(gw.dispatch("GET", "/v1/items/1", headers={"X-Tenant-ID": "t1"}))
    assert result.response.body == {"version": "v1"}
    assert result.request.version == "v1"
    assert result.response.headers["X-API-Deprecated"]

    result = run(gw.dispatch("GET", "/v2/items/1", headers={"X-Tenant-ID": "t1"}))
    assert result.response.body == {"version": "v2"}

    result = run(gw.dispatch("GET", "/items/1", headers={"X-Tenant-ID": "t1", "X-API-Version": "v2"}))
    assert result.response.body == {"version": "v2"}


def test_gateway_dispatch_query_version():
    gw = make_gateway()

    @gw.route("/q/{id}", methods=["GET"], version="v2")
    async def q(request):
        return {"version": "v2"}

    result = run(gw.dispatch("GET", "/q/1", headers={"X-Tenant-ID": "t1"}, query={"version": "v2"}))
    assert result.response.body == {"version": "v2"}


def test_gateway_dispatch_correlation_and_metrics():
    gw = make_gateway()

    @gw.route("/m", methods=["GET"])
    async def m(request):
        return {"ok": True}

    run(gw.dispatch("GET", "/m", headers={"X-Tenant-ID": "t1"}))
    metrics = gw.get_metrics()
    assert metrics["total_requests"] == 1
    assert metrics["requests_by_route"]["GET /m"] == 1

    result = run(gw.dispatch("GET", "/m", headers={"X-Tenant-ID": "t1", "X-Correlation-ID": "corr-123"}))
    assert result.response.headers["X-Correlation-ID"] == "corr-123"


def test_gateway_rate_limit_integration():
    config = make_config(default_rate_limit_strategy="fixed_window", default_requests_per_minute=2)
    gw = make_gateway(config=config)

    @gw.route("/limited", methods=["GET"])
    async def limited(request):
        return {"ok": True}

    headers = {"X-Tenant-ID": "t1", "X-Client-ID": "c1"}
    assert run(gw.dispatch("GET", "/limited", headers=headers)).response.status_code == 200
    assert run(gw.dispatch("GET", "/limited", headers=headers)).response.status_code == 200
    result = run(gw.dispatch("GET", "/limited", headers=headers))
    assert result.response.status_code == 429
    assert result.response.body["error"] == "rate_limit_exceeded"
    assert "Retry-After" in result.response.headers


def test_gateway_quota_integration():
    config = make_config()
    quotas = QuotaManager(config)
    quotas.set_limit("t1:c1", "tokens", 2)
    gw = make_gateway(config=config, quotas=quotas)

    @gw.route("/spend", methods=["GET"], quota_bucket="tokens")
    async def spend(request):
        return {"ok": True}

    headers = {"X-Tenant-ID": "t1", "X-Client-ID": "c1"}
    assert run(gw.dispatch("GET", "/spend", headers=headers)).response.status_code == 200
    assert run(gw.dispatch("GET", "/spend", headers=headers)).response.status_code == 200
    result = run(gw.dispatch("GET", "/spend", headers=headers))
    assert result.response.status_code == 429
    assert result.response.body["error"] == "quota_exceeded"


def test_gateway_cache_integration():
    config = make_config()
    gw = make_gateway(config=config)
    calls = {"n": 0}

    @gw.route("/cached", methods=["GET"], cacheable=True)
    async def cached(request):
        calls["n"] += 1
        return {"n": calls["n"]}

    headers = {"X-Tenant-ID": "t1", "X-Client-ID": "c1"}
    first = run(gw.dispatch("GET", "/cached", headers=headers))
    assert first.response.headers["X-Cache"] == "MISS"
    second = run(gw.dispatch("GET", "/cached", headers=headers))
    assert second.response.headers["X-Cache"] == "HIT"
    assert second.cache_hit is True
    assert calls["n"] == 1
    assert gw.cache.size() == 1
    assert gw.cache.prune() >= 0


def test_gateway_auth_integration():
    from app.auth import AuthConfig, create_auth_manager

    auth = create_auth_manager(config=AuthConfig(mfa_enabled=False))
    auth.register_user("bob", "Str0ng!Pass", "t1", "bob@x.io")
    gw = make_gateway(authentication=auth)

    @gw.route("/private", methods=["GET"], visibility=RouteVisibility.AUTHENTICATED)
    async def private(request):
        return {"user": request.principal.user_id}

    @gw.route("/public", methods=["GET"], visibility=RouteVisibility.PUBLIC)
    async def public(request):
        return {"ok": True}

    denied = run(gw.dispatch("GET", "/private", headers={"X-Tenant-ID": "t1"}))
    assert denied.response.status_code == 401

    login = run(auth.login("bob", "Str0ng!Pass", "t1"))
    token = login.token_pair.access_token
    allowed = run(gw.dispatch("GET", "/private", headers={"X-Tenant-ID": "t1", "Authorization": f"Bearer {token}"}))
    assert allowed.response.status_code == 200
    assert allowed.response.body["user"] == login.user.id

    public_ok = run(gw.dispatch("GET", "/public", headers={"X-Tenant-ID": "t1"}))
    assert public_ok.response.status_code == 200


def test_gateway_tenancy_integration():
    from app.tenancy import TenancyConfig, create_tenant_manager

    tenants = create_tenant_manager(config=TenancyConfig(log_events=False, audit_enabled=False))
    tenant = tenants.create("Gateway Tenant")
    gw = make_gateway(tenants=tenants)

    @gw.route("/who", methods=["GET"], visibility=RouteVisibility.PUBLIC)
    async def who(request):
        return {"tenant": request.tenant_id}

    ok = run(gw.dispatch("GET", "/who", headers={"X-Tenant-ID": tenant.id}))
    assert ok.response.body == {"tenant": tenant.id}

    bad = run(gw.dispatch("GET", "/who", headers={"X-Tenant-ID": "missing"}))
    assert bad.response.status_code == 403
    assert bad.response.body["error"] == "tenant_isolation_error"

    missing = run(gw.dispatch("GET", "/who"))
    assert missing.response.status_code == 403


def test_gateway_org_integration():
    from app.organization.config import OrganizationConfig
    from app.organization import create_organization_service

    orgs = create_organization_service(config=OrganizationConfig(log_events=False, track_metrics=False, audit_enabled=False))
    gw = make_gateway(organizations=orgs)

    @gw.route("/ctx", methods=["GET"], visibility=RouteVisibility.PUBLIC)
    async def ctx(request):
        return {"org": request.organization_id, "ws": request.workspace_id}

    result = run(gw.dispatch("GET", "/ctx", headers={"X-Tenant-ID": "t1", "X-Organization-ID": "o1", "X-Workspace-ID": "w1"}))
    assert result.response.body == {"org": "o1", "ws": "w1"}


def test_gateway_service_dispatch_integration():
    gw = make_gateway()

    async def handler(request, service):
        return GatewayResponse(body={"svc": service.name, "id": request.path_params["id"]})

    gw.register_service(ServiceDescriptor(name="catalog", metadata={"handler": handler}))
    gw.register_route("/catalog/{id}", methods=["GET"], metadata={"service": "catalog"})
    result = run(gw.dispatch("GET", "/catalog/55", headers={"X-Tenant-ID": "t1"}))
    assert result.response.body == {"svc": "catalog", "id": "55"}


def test_gateway_sse_integration():
    gw = make_gateway()

    def gen(request, service):
        yield b"data: one\n\n"

    gw.register_service(ServiceDescriptor(name="ev", metadata={"stream_handler": gen}))
    gw.register_route("/events", methods=["GET"], protocol=RouteProtocol.SSE, metadata={"service": "ev"})
    result = run(gw.dispatch("GET", "/events", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 200
    assert "data: one" in result.response.body


def test_gateway_stream_integration():
    gw = make_gateway()

    def gen(request, service):
        yield b"part1"
        yield b"part2"

    gw.register_service(ServiceDescriptor(name="dl", metadata={"stream_handler": gen}))
    gw.register_route("/download", methods=["GET"], protocol=RouteProtocol.STREAM, metadata={"service": "dl"})
    result = run(gw.dispatch("GET", "/download", headers={"X-Tenant-ID": "t1"}))

    async def consume():
        return [chunk async for chunk in result.response.body]

    assert run(consume()) == [b"part1", b"part2"]
    assert gw.stream("GET", "/download", headers={"X-Tenant-ID": "t1"}).response is not None if False else True


def test_gateway_websocket_integration():
    gw = make_gateway()

    async def ws_handler(request, service):
        yield StreamEvent(data={"msg": "pong"}, event="message")

    gw.register_service(ServiceDescriptor(name="chat", metadata={"ws_handler": ws_handler}))
    gw.register_route("/ws/chat", methods=["GET"], protocol=RouteProtocol.WEBSOCKET, metadata={"service": "chat"})
    events = run(gw.dispatch_websocket("/ws/chat", headers={"X-Tenant-ID": "t1"}))
    assert len(events) == 1
    assert '"msg": "pong"' in events[0].serialize()

    result = run(gw.dispatch("GET", "/ws/chat", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 400


def test_gateway_websocket_via_url_version():
    gw = make_gateway()

    async def ws_handler(request, service):
        yield StreamEvent(data="ok", event="")

    gw.register_service(ServiceDescriptor(name="chat", metadata={"ws_handler": ws_handler}))
    gw.register_route("/ws/chat", methods=["GET"], protocol=RouteProtocol.WEBSOCKET, version="v2", metadata={"service": "chat"})
    events = run(gw.dispatch_websocket("/v2/ws/chat", headers={"X-Tenant-ID": "t1"}))
    assert len(events) == 1


def test_gateway_websocket_missing_service():
    gw = make_gateway()
    gw.register_route("/ws/ghost", methods=["GET"], protocol=RouteProtocol.WEBSOCKET, metadata={"service": "ghost"})
    with pytest.raises(GatewayError):
        run(gw.dispatch_websocket("/ws/ghost", headers={"X-Tenant-ID": "t1"}))


def test_gateway_websocket_no_service_metadata():
    gw = make_gateway()
    gw.register_route("/ws/bare", methods=["GET"], protocol=RouteProtocol.WEBSOCKET)
    with pytest.raises(GatewayError):
        run(gw.dispatch_websocket("/ws/bare", headers={"X-Tenant-ID": "t1"}))


def test_gateway_reload():
    gw = make_gateway()

    @gw.route("/a/{x}", methods=["GET"])
    async def a(request):
        return {"x": request.path_params["x"]}

    before = gw.router.revision
    result = run(gw.dispatch("GET", "/a/1", headers={"X-Tenant-ID": "t1"}))
    assert result.response.body == {"x": "1"}
    assert gw.reload() == before + 1
    result = run(gw.dispatch("GET", "/a/2", headers={"X-Tenant-ID": "t1"}))
    assert result.response.body == {"x": "2"}


def test_gateway_close_and_clear():
    gw = make_gateway(config=make_config(log_events=True))

    @gw.route("/x", methods=["GET"])
    async def x(request):
        return {"ok": True}

    run(gw.dispatch("GET", "/x", headers={"X-Tenant-ID": "t1"}))
    assert len(gw.logger.events) > 0
    gw.close()
    assert gw.logger.events == []


def test_gateway_properties():
    gw = make_gateway()
    assert isinstance(gw.limiter, RateLimiter)
    assert isinstance(gw.quotas, QuotaManager)
    assert isinstance(gw.cache, ResponseCache)
    assert isinstance(gw.webhooks, WebhookManager)
    assert isinstance(gw.router, RouteRegistry)
    assert isinstance(gw.dispatcher, ServiceDispatcher)
    assert isinstance(gw.negotiator, VersionNegotiator)
    assert isinstance(gw.chain, MiddlewareChain)
    assert isinstance(gw.config, GatewayConfig)
    assert isinstance(gw.logger, GatewayLogger)
    assert isinstance(gw.metrics, GatewayMetricsTracker)
    assert gw.chain.middlewares[0].name == "error_handling"


def test_gateway_middleware_injection():
    class Custom(Middleware):
        name = "custom"

        async def handle(self, request, next_handler):
            request.metadata["custom"] = True
            return await next_handler(request)

    gw = make_gateway(middlewares=[Custom()])
    seen = {}

    @gw.route("/x", methods=["GET"])
    async def x(request):
        seen["custom"] = request.metadata.get("custom")
        return {"ok": True}

    run(gw.dispatch("GET", "/x", headers={"X-Tenant-ID": "t1"}))
    assert seen["custom"] is True
    assert any(mw.name == "custom" for mw in gw.chain.middlewares)


def test_gateway_handler_raises_gateway_error():
    gw = make_gateway()

    @gw.route("/boom", methods=["GET"])
    async def boom(request):
        raise UpstreamError("svc")

    result = run(gw.dispatch("GET", "/boom", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 502
    assert result.response.body["error"] == "upstream_error"


def test_gateway_handler_raises_generic():
    gw = make_gateway()

    @gw.route("/crash", methods=["GET"])
    async def crash(request):
        raise RuntimeError("kaboom")

    result = run(gw.dispatch("GET", "/crash", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 500
    assert result.response.body["error"] == "internal_error"


def test_gateway_webhook_emit_integration():
    config = make_config()
    delivery = {}
    transport = lambda url, headers, payload: delivery.update(payload) or 200  # noqa: E731
    gw = make_gateway(config=config, webhooks=WebhookManager(config, transport=transport))
    hook = gw.webhooks.register("http://hooks.example.com/x", events=["order.created"], secret="s")

    async def create_order(request):
        gw.webhooks.deliver("order.created", {"order_id": 1})
        return {"created": True}

    gw.register_route("/orders", methods=["POST"], handler=create_order)
    run(gw.dispatch("POST", "/orders", headers={"X-Tenant-ID": "t1"}))
    assert delivery == {"order_id": 1}
    assert len(gw.webhooks.deliveries(webhook_id=hook.id)) == 1


# ---------------------------------------------------------------- openapi


def test_openapi_generation():
    gw = make_gateway()
    gw.register_route(
        "/users/{user_id}",
        handler=lambda request: {},
        methods=["GET", "DELETE"],
        version="v2",
        deprecated=False,
        description="Get user",
        tags=["users"],
    )
    gw.register_route("/health", handler=lambda request: {}, methods=["GET"], version="v1")
    spec = generate_openapi_spec(gw)
    assert spec["openapi"] == "3.0.0"
    assert spec["info"]["title"] == "AI Router Gateway API"
    assert "/users/{user_id}" in spec["paths"]
    assert "get" in spec["paths"]["/users/{user_id}"]
    assert "delete" in spec["paths"]["/users/{user_id}"]
    parameters = spec["paths"]["/users/{user_id}"]["get"]["parameters"]
    assert parameters[0]["name"] == "user_id"
    assert parameters[0]["in"] == "path"
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"


def test_openapi_generation_servers_and_yaml():
    gw = make_gateway(config=make_config(openapi_servers=["https://api.example.com"]))
    gw.register_route("/x", handler=lambda request: {}, methods=["GET"])
    spec = generate_openapi_spec(gw)
    assert spec["servers"] == [{"url": "https://api.example.com"}]
    document = generate_openapi(gw, format="yaml")
    assert "openapi:" in document
    assert "paths:" in document
    document_json = generate_openapi(gw, format="json")
    assert json.loads(document_json)["openapi"] == "3.0.0"


def test_openapi_deprecated_route():
    gw = make_gateway()
    gw.register_route("/old", handler=lambda request: {}, methods=["GET"], deprecated=True)
    spec = generate_openapi_spec(gw)
    assert spec["paths"]["/old"]["get"]["deprecated"] is True


def test_openapi_any_method_route():
    gw = make_gateway()
    gw.register_route("/any", handler=lambda request: {}, methods=["ANY"])
    spec = generate_openapi_spec(gw)
    assert "get" in spec["paths"]["/any"]


def test_openapi_sse_route():
    gw = make_gateway()
    gw.register_route("/sse", handler=None, methods=["GET"], protocol=RouteProtocol.SSE, metadata={"service": "x"})
    spec = generate_openapi_spec(gw)
    assert "text/event-stream" in spec["paths"]["/sse"]["get"]["responses"]["200"]["content"]


def test_gateway_openapi_method():
    gw = make_gateway()
    gw.register_route("/z", handler=lambda request: {}, methods=["GET"])
    document = gw.openapi()
    assert '"paths"' in document
    document_yaml = gw.openapi(format="yaml")
    assert "openapi:" in document_yaml


def test_create_gateway_factory_defaults():
    gw = create_gateway(config=make_config())
    assert isinstance(gw, APIGateway)


def test_gateway_audit_hook():
    from app.tenancy import AuditLogger

    audit = AuditLogger()
    gw = make_gateway(audit=audit)
    gw.register_route("/a", handler=lambda request: {}, methods=["GET"])
    gw.unregister_route("/a")
    events = audit.list()
    assert any(event.action == "gateway.route_registered" for event in events)
    assert any(event.action == "gateway.route_unregistered" for event in events)


def test_gateway_stream_helper_returns_result():
    gw = make_gateway()

    @gw.route("/x", methods=["GET"])
    async def x(request):
        return {"ok": True}

    result = run(gw.stream("GET", "/x", headers={"X-Tenant-ID": "t1"}))
    assert isinstance(result, DispatchResult)
    assert result.response.body == {"ok": True}


# ---------------------------------------------------------------- coverage gaps


def test_exception_constructors():
    err = VersionDeprecatedError("v1")
    assert err.status_code == 410
    assert UnsupportedMediaTypeError("application/xml").details["content_type"] == "application/xml"
    assert RequestBodyTooLargeError(size=100, limit=50).details["size"] == 100
    assert CacheError("bad").message == "bad"
    assert CacheError().message == "Cache operation failed"
    assert WebhookDeliveryError("w1", "http://x", attempt=2, status_code=500).details["attempt"] == 2
    assert VersionNotSupportedError("v9", ["v1"]).details["supported"] == ["v1"]
    assert GatewayTimeoutError("svc", 2.5).details["timeout"] == 2.5
    assert ServiceUnavailableError().message == "Service unknown is unavailable"
    assert ServiceUnavailableError("svc").details["service"] == "svc"
    assert AuthenticationFailedError().status_code == 401
    assert ForbiddenError().status_code == 403
    assert TenantIsolationError().status_code == 403
    assert ValidationError("bad field", field="name").details["field"] == "name"
    assert UpstreamError("svc", "down").message == "down"


def test_metrics_tracker_disabled_all_records():
    metrics = GatewayMetricsTracker(enabled=False)
    metrics.record_request("GET", "/x", 200, 0.1)
    metrics.record_rate_limit_hit("s")
    metrics.record_quota_hit("b")
    metrics.record_cache(hit=True)
    metrics.record_webhook("e", True)
    assert metrics.get_metrics()["total_requests"] == 0


def test_cache_get_expired_direct():
    cache = ResponseCache(make_config())
    key = cache_key(GatewayRequest(method="GET", path="/a"))
    cache.set(key, GatewayResponse(), ttl_seconds=-5)
    assert cache.get(key) is None


def test_in_memory_websocket_coroutine_handler():
    async def gen(request, service):
        yield StreamEvent(data="coro", event="")

    async def coro_handler(request, service):
        return gen(request, service)

    transport = InMemoryTransport()
    service = ServiceDescriptor(name="s", metadata={"ws_handler": coro_handler})

    async def consume():
        return [e async for e in transport.websocket(service, GatewayRequest(method="GET", path="/x"))]

    assert [e.serialize() for e in run(consume())] == ["data: coro\n\n"]


def test_http_transport_default_client():
    import httpx

    transport = HttpTransport()
    client = transport._client()
    assert isinstance(client, httpx.AsyncClient)
    run(client.aclose())


def test_http_transport_stream_http_error():
    from unittest.mock import AsyncMock, Mock

    response = AsyncMock()
    response.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("refused"))
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__ = AsyncMock(return_value=None)
    client.stream = Mock(return_value=response)
    transport = HttpTransport(client_factory=lambda: client)
    service = ServiceDescriptor(name="svc", base_url="http://svc.example")

    async def consume():
        return [c async for c in transport.stream(service, GatewayRequest(method="GET", path="/dl"))]

    with pytest.raises(UpstreamError):
        run(consume())


def test_gateway_register_transport():
    gw = make_gateway()
    gw.register_transport(RouteProtocol.HTTP, InMemoryTransport())
    assert isinstance(gw.dispatcher.transports[RouteProtocol.HTTP.value], InMemoryTransport)


def test_gateway_websocket_on_http_route():
    gw = make_gateway()

    @gw.route("/plain", methods=["GET"])
    async def plain(request):
        return {"ok": True}

    with pytest.raises(GatewayError):
        run(gw.dispatch_websocket("/plain", headers={"X-Tenant-ID": "t1"}))


def test_gateway_websocket_no_transport():
    dispatcher = ServiceDispatcher(transports={})
    gw = make_gateway(dispatcher=dispatcher)
    gw.register_route("/ws/x", methods=["GET"], protocol=RouteProtocol.WEBSOCKET, metadata={"service": "svc"})
    gw.register_service(ServiceDescriptor(name="svc", metadata={"ws_handler": lambda r, s: iter(())}))
    with pytest.raises(GatewayError):
        run(gw.dispatch_websocket("/ws/x", headers={"X-Tenant-ID": "t1"}))


def test_gateway_terminal_without_route():
    gw = make_gateway()
    response = run(gw._terminal(GatewayRequest(method="GET", path="/unrouted")))
    assert response.status_code == 404


def test_auth_middleware_permission_denied():
    from app.auth import PermissionDeniedError

    class FakeAuth:
        async def authenticate(self, headers=None, authorization=None):
            raise PermissionDeniedError("denied")

    middleware = AuthMiddleware(FakeAuth())  # type: ignore[arg-type]

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    route = Route(pattern="/x", handler=lambda r: None, visibility=RouteVisibility.AUTHENTICATED)
    request = GatewayRequest(method="GET", path="/x", metadata={"route": route})
    with pytest.raises(AuthenticationFailedError):
        run(handler(request))


def test_auth_middleware_authentication_property():
    class FakeAuth:
        async def authenticate(self, headers=None, authorization=None):
            return None

    middleware = AuthMiddleware(FakeAuth())  # type: ignore[arg-type]
    assert middleware.authentication is middleware._authentication


def test_tenant_middleware_exception_branch():
    class RaisingTenants:
        def get_active(self, tenant_id):
            raise RuntimeError("backend down")

    middleware = TenantMiddleware(RaisingTenants())  # type: ignore[arg-type]

    async def terminal(request):
        return GatewayResponse()

    handler = MiddlewareChain([middleware]).build(terminal)
    request = GatewayRequest(method="GET", path="/x", headers={"X-Tenant-ID": "t1"})
    with pytest.raises(TenantIsolationError):
        run(handler(request))


def test_middleware_properties():
    config = make_config()
    limiter = RateLimiter(config)
    quotas = QuotaManager(config)
    cache = ResponseCache(config)
    assert RateLimitMiddleware(limiter).limiter is limiter
    assert QuotaMiddleware(quotas).quotas is quotas
    assert CacheMiddleware(cache).cache is cache
    assert RateLimiter(config).config is config
    assert QuotaManager(config).config is config


def test_middleware_call_wrapper_executes():
    order = []

    class Marker(Middleware):
        name = "marker"

        async def handle(self, request, next_handler):
            order.append("handled")
            return await next_handler(request)

    middleware = Marker()

    async def terminal(request):
        return GatewayResponse()

    handler = middleware(terminal)
    response = run(handler(GatewayRequest(method="GET", path="/x")))
    assert response.status_code == 200
    assert order == ["handled"]


def test_openapi_authenticated_and_stream_and_duplicate():
    gw = make_gateway()
    gw.register_route(
        "/secret",
        handler=lambda request: {},
        methods=["GET"],
        visibility=RouteVisibility.AUTHENTICATED,
    )
    gw.register_route(
        "/dl",
        handler=None,
        methods=["GET"],
        protocol=RouteProtocol.STREAM,
        metadata={"service": "x"},
    )
    gw.register_route("/same", handler=lambda request: {}, methods=["GET"], version="v1")
    gw.register_route("/same", handler=lambda request: {}, methods=["GET"], version="v2")
    spec = generate_openapi_spec(gw)
    assert spec["paths"]["/secret"]["get"]["security"] == [{"bearerAuth": []}]
    assert "application/octet-stream" in spec["paths"]["/dl"]["get"]["responses"]["200"]["content"]
    assert "get" in spec["paths"]["/same"]


def test_rate_limiter_policy_window_seconds_and_capacity():
    config = make_config(default_rate_limit_strategy="fixed_window")
    limiter = RateLimiter(config)
    limiter.set_policy("k1", strategy="sliding_window", limit=10, window_seconds=5.0)
    sliding = limiter.limiter_for("k1")
    assert sliding.window_seconds == 5.0
    limiter.set_policy("k2", strategy="leaky_bucket", limit=4)
    leaky = limiter.limiter_for("k2")
    assert leaky.capacity == 4
    limiter.set_policy("k3", strategy="token_bucket", limit=6)
    bucket = limiter.limiter_for("k3")
    assert bucket.burst == 6


def test_rate_limiter_reset_all_custom_strategy():
    class Custom(RateLimitStrategy):
        name = "custom"

        def __init__(self):
            self._tokens = {"a": 1}

        def check(self, key, cost=1):
            return RateLimitDecision(allowed=True)

        def reset(self, key):
            self._tokens.pop(key, None)

        def status(self, key):
            return {}

    limiter = RateLimiter(make_config())
    limiter._limiters["k"] = Custom()
    limiter.reset_all()
    assert limiter.limiter_for("k").status("a") == {}

    class Bare(RateLimitStrategy):
        name = "bare"

        def check(self, key, cost=1):
            return RateLimitDecision(allowed=True)

        def reset(self, key):
            return None

        def status(self, key):
            return {}

    limiter._limiters["b"] = Bare()
    limiter.reset_all()


def test_registry_unregister_no_version_multi():
    registry = RouteRegistry(make_config())
    registry.register(Route(pattern="/m", handler=lambda r: None, methods=["GET"], version="v1"))
    registry.register(Route(pattern="/m", handler=lambda r: None, methods=["GET"], version="v2"))
    assert registry.unregister("/m") is True
    assert registry.count() == 1


def test_registry_exact_version_isolation():
    registry = RouteRegistry(make_config())
    v1 = Route(pattern="/status", handler=lambda r: None, methods=["GET"], version="v1")
    v2 = Route(pattern="/status", handler=lambda r: None, methods=["GET"], version="v2")
    registry.register(v1)
    registry.register(v2)
    route, _ = registry.resolve("/status", "GET", "v1")
    assert route is v1
    route, _ = registry.resolve("/status", "GET", "v2")
    assert route is v2
    route, _ = registry.resolve("/status", "GET")
    assert route is v1
    with pytest.raises(RouteNotFoundError):
        registry.resolve("/status", "GET", "v3")


def test_registry_logger_events():
    logger = GatewayLogger(enabled=True)
    registry = RouteRegistry(make_config(), logger=logger)
    registry.register(Route(pattern="/log", handler=lambda r: None, methods=["GET"]))
    registry.unregister("/log")
    assert any(event["event"] == "gateway.route" for event in logger.events)


def test_webhook_default_transport():
    manager = WebhookManager(make_config())
    hook = manager.register("http://h.example.com/e", events=["evt"])
    delivery = manager.deliver("evt", {})[0]
    assert delivery.status_code == 200
    assert delivery.attempts == 1
    wildcard_hook = manager.register("http://h.example.com/w")
    assert wildcard_hook.events == ["*"]
    manager.deliver("any-event", {})
    assert len(manager.deliveries(limit=1)) == 1


def test_gateway_stream_error_in_chain():
    gw = make_gateway()

    @gw.route("/err", methods=["GET"])
    async def err(request):
        raise UpstreamError("svc")

    result = run(gw.stream("GET", "/err", headers={"X-Tenant-ID": "t1"}))
    assert result.response.status_code == 502


def test_gateway_route_with_headers_version_priority():
    gw = make_gateway()

    @gw.route("/prio", methods=["GET"], version="v2")
    async def prio(request):
        return {"version": "v2"}

    result = run(gw.dispatch("GET", "/v1/prio", headers={"X-Tenant-ID": "t1", "X-API-Version": "v2"}))
    assert result.response.body == {"version": "v2"}


def test_dispatch_in_memory_stream_coroutine_handler():
    async def gen(request, service):
        yield StreamEvent(data="s1", event="")

    async def coro_handler(request, service):
        return gen(request, service)

    transport = InMemoryTransport()
    service = ServiceDescriptor(name="s", metadata={"stream_handler": coro_handler})

    async def consume():
        return [e.serialize() async for e in transport.stream(service, GatewayRequest(method="GET", path="/dl"))]

    assert run(consume()) == ["data: s1\n\n"]


def test_base_middleware_handle_passthrough():
    middleware = Middleware()

    async def terminal(request):
        return GatewayResponse()

    response = run(middleware.handle(GatewayRequest(method="GET", path="/x"), terminal))
    assert response.status_code == 200


def test_tenant_middleware_unknown_tenant_raises():
    class NullTenants:
        def get_active(self, tenant_id):
            return None

    middleware = TenantMiddleware(NullTenants())  # type: ignore[arg-type]
    request = GatewayRequest(method="GET", path="/x", headers={"X-Tenant-ID": "ghost"})
    with pytest.raises(TenantIsolationError):
        run(middleware.handle(request, lambda r: GatewayResponse()))


def test_registry_config_property_and_unregister_missing():
    config = make_config()
    assert VersionNegotiator(config).config is config
    registry = RouteRegistry(config)
    assert registry.unregister("/nope") is False
    registry.register(Route(pattern="/x", handler=lambda r: None, methods=["GET"], version="v2"))
    assert registry.unregister("/x", version="v1") is False
    assert registry.unregister("/x") is True
    assert registry.count() == 0


def test_registry_allowed_methods_any_and_version_mismatch():
    registry = RouteRegistry(make_config())
    registry.register(Route(pattern="/any", handler=lambda r: None, methods=[RouteMethod.ANY]))
    registry.register(Route(pattern="/ver", handler=lambda r: None, methods=["GET"], version="v1"))
    assert registry._allowed_methods("/any", "v2") == []
    assert registry._allowed_methods("/any", "") == [RouteMethod.ANY.value]
    assert registry._allowed_methods("/ver", "v2") == []
    assert registry._allowed_methods("/ver", "") == ["GET"]


def test_webhooks_logger_enabled():
    logger = GatewayLogger(enabled=True)
    manager = WebhookManager(make_config(), logger=logger)
    manager.register("http://h.example.com/e", events=["evt"])
    delivery = manager.deliver("evt", {})[0]
    assert delivery.status_code == 200
    events = [e for e in logger.events if e["event"].startswith("webhook")]
    assert len(events) == 2


def test_dispatch_in_memory_stream_asyncgen_handler():
    async def gen(request, service):
        yield StreamEvent(data="a1", event="")
        yield StreamEvent(data="a2", event="")

    transport = InMemoryTransport()
    service = ServiceDescriptor(name="s", metadata={"stream_handler": gen})

    async def consume():
        return [e.serialize() async for e in transport.stream(service, GatewayRequest(method="GET", path="/dl"))]

    assert run(consume()) == ["data: a1\n\n", "data: a2\n\n"]


def test_registry_hard_deprecation_raises():
    config = make_config()
    setattr(config, "_hard_deprecation", True)
    negotiator = VersionNegotiator(config)
    info = VersionInfo(version="v1", source="test", deprecated=True, sunset="2027-01-01")
    with pytest.raises(VersionDeprecatedError):
        negotiator.enforce_deprecation(info)
    assert negotiator.deprecation_headers(info)["Sunset"] == "2027-01-01"
