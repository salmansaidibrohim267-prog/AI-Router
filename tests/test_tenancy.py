from __future__ import annotations

import asyncio
import base64
import json

import pytest

from app.tenancy import (
    APIKeyStrategy,
    AuditLogger,
    CustomDomainStrategy,
    HeaderStrategy,
    InMemoryTenantRepository,
    JWTStrategy,
    SubdomainStrategy,
    TenancyConfig,
    TenancyLogger,
    TenancyMetricsTracker,
    Tenant,
    TenantConfigService,
    TenantContext,
    TenantContextManager,
    TenantIsolation,
    TenantLimits,
    TenantManager,
    TenantMiddleware,
    TenantResolver,
    TenantStatus,
    create_tenant_config_service,
    create_tenant_context,
    create_tenant_manager,
    create_tenant_middleware,
    create_tenant_resolver,
    decode_jwt_claims,
)
from app.tenancy.context import (
    get_current_tenant,
    get_tenant_context_manager,
    require_current_tenant,
    set_current_tenant,
)
from app.tenancy.exceptions import (
    TenantAlreadyExistsError,
    TenantContextMissingError,
    TenantDeletedError,
    TenantIsolationError,
    TenantNotFoundError,
    TenantResolutionError,
    TenantSuspendedError,
)


def make_config(**kwargs):
    defaults = {"log_events": False, "track_metrics": True}
    defaults.update(kwargs)
    return TenancyConfig(**defaults)


def make_manager(**kwargs):
    return TenantManager(config=make_config(), **kwargs)


def make_jwt(claims, issuer="airouter"):
    payload = base64.urlsafe_b64encode(
        json.dumps({"iss": issuer, **claims}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.sig"


class FakeASGIApp:
    def __init__(self, status=200):
        self.calls = []
        self.status = status

    async def __call__(self, scope, receive, send):
        self.calls.append(scope)
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})


def make_scope(headers=None, host=None, method="GET", path="/v1/chat", type_="http"):
    header_pairs = []
    for k, v in (headers or {}).items():
        header_pairs.append((k.encode(), v.encode()))
    if host:
        header_pairs.append((b"host", host.encode()))
    return {"type": type_, "method": method, "path": path, "headers": header_pairs}


async def run_asgi(middleware, scope):
    messages = []

    async def send(message):
        messages.append(message)

    async def receive():
        return {}

    await middleware(scope, receive, send)
    return messages


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("TEN_HEADER", "X-Tenant")
    monkeypatch.setenv("TEN_ALLOW_ANONYMOUS", "1")
    monkeypatch.setenv("TEN_SUBDOMAIN_SUFFIX", ".acme.io")
    config = TenancyConfig.from_env()
    assert config.header_name == "X-Tenant"
    assert config.allow_anonymous is True
    assert config.subdomain_suffix == ".acme.io"
    assert config.context_var_name == "tenant_context"


def test_exception_hierarchy():
    from app.tenancy import TenancyError

    assert issubclass(TenantNotFoundError, TenancyError)
    assert issubclass(TenantAlreadyExistsError, TenancyError)
    assert issubclass(TenantSuspendedError, TenancyError)
    assert issubclass(TenantDeletedError, TenancyError)
    assert issubclass(TenantResolutionError, TenancyError)
    assert issubclass(TenantContextMissingError, TenancyError)
    assert issubclass(TenantIsolationError, TenancyError)
    assert "x" in str(TenantNotFoundError("x"))
    assert "x" in str(TenantSuspendedError("x"))
    assert "x" in str(TenantAlreadyExistsError("x"))
    assert "x" in str(TenantDeletedError("x"))
    assert "no" in str(TenantContextMissingError("no"))


def test_tenant_model():
    tenant = Tenant(id="t1", name="Acme")
    assert tenant.is_active is True
    assert tenant.is_suspended is False
    assert tenant.is_deleted is False
    assert tenant.config_section("llm") == {}
    tenant.set_config("llm", {"model": "gpt-4o"})
    assert tenant.config_section("llm") == {"model": "gpt-4o"}
    assert tenant.updated_at >= tenant.created_at
    payload = tenant.to_dict()
    assert payload["status"] == "active"
    assert payload["limits"]["max_seats"] == 5
    restored = Tenant.from_dict(payload)
    assert restored.id == "t1"
    assert restored.config["llm"]["model"] == "gpt-4o"
    assert restored.is_active


def test_tenant_model_suspended():
    tenant = Tenant(id="t1", status=TenantStatus.SUSPENDED)
    assert tenant.is_suspended is True
    assert tenant.is_active is False
    tenant = Tenant.from_dict({"id": "t2", "status": "deleted"})
    assert tenant.is_deleted is True


def test_tenant_limits_roundtrip():
    limits = TenantLimits(max_requests_per_min=10, max_seats=2)
    payload = limits.to_dict()
    assert payload["max_requests_per_min"] == 10
    restored = TenantLimits.from_dict(payload)
    assert restored.max_seats == 2
    default = TenantLimits.from_dict({})
    assert default.max_requests_per_min == 1000


def test_tenant_context():
    context = TenantContext(tenant_id="t1")
    assert context.is_isolated is True
    context.require_tenant()
    empty = TenantContext(tenant_id="")
    with pytest.raises(TenantContextMissingError):
        empty.require_tenant()
    anonymous = TenantContext.anonymous("anon")
    assert anonymous.auth_method == "anonymous"
    assert anonymous.to_dict()["tenant_id"] == "anon"
    merged = context.merged(Tenant(id="t1", name="Acme"))
    assert merged.tenant_name == "Acme"
    assert merged.status == "active"
    context.with_attribute("k", "v")
    assert context.attributes == {"k": "v"}
    context = TenantContext(tenant_id="t1", resolved_by="x", user_id="u1")
    assert context.to_dict()["user_id"] == "u1"
    assert context.to_dict()["resolved_by"] == "x"


def test_repository():
    repo = InMemoryTenantRepository()
    tenant = repo.create(Tenant(id="t1", name="A"))
    assert repo.get("t1").name == "A"
    with pytest.raises(TenantNotFoundError):
        repo.get("missing")
    tenant.name = "B"
    repo.update(tenant)
    assert repo.get("t1").name == "B"
    with pytest.raises(TenantNotFoundError):
        repo.update(Tenant(id="missing"))
    assert repo.delete("t1") is True
    assert repo.list() == []
    with pytest.raises(TenantNotFoundError):
        repo.delete("t1")


def test_manager_create_and_get():
    manager = make_manager()
    tenant = manager.create("Acme", tenant_id="acme", plan="pro")
    assert tenant.id == "acme"
    assert tenant.plan == "pro"
    assert manager.get("acme").name == "Acme"
    assert manager.count() == 1
    with pytest.raises(TenantAlreadyExistsError):
        manager.create("Acme 2", tenant_id="acme")


def test_manager_create_auto_id():
    manager = make_manager()
    tenant = manager.create("Auto")
    assert tenant.id.startswith("t_")


def test_manager_create_invalid_section():
    manager = make_manager()
    with pytest.raises(ValueError):
        manager.create("X", tenant_id="x1", config={"bogus": {}})


def test_manager_update():
    manager = make_manager()
    manager.create("Acme", tenant_id="acme")
    tenant = manager.update("acme", name="Acme Corp", plan="enterprise")
    assert tenant.name == "Acme Corp"
    assert tenant.plan == "enterprise"
    tenant = manager.update("acme", limits={"max_requests_per_min": 500})
    assert tenant.limits.max_requests_per_min == 500
    with pytest.raises(ValueError):
        manager.update("acme", bogus_field=1)
    with pytest.raises(TenantNotFoundError):
        manager.update("missing", name="X")


def test_manager_suspend_activate_delete():
    manager = make_manager()
    manager.create("Acme", tenant_id="acme")
    tenant = manager.suspend("acme")
    assert tenant.is_suspended
    assert manager.get("acme").is_suspended
    tenant = manager.activate("acme")
    assert tenant.is_active
    assert manager.delete("acme") is True
    with pytest.raises(TenantDeletedError):
        manager.suspend("acme")
    with pytest.raises(TenantDeletedError):
        manager.activate("acme")
    with pytest.raises(TenantDeletedError):
        manager.update("acme", name="X")
    with pytest.raises(TenantDeletedError):
        manager.delete("acme")
    with pytest.raises(TenantNotFoundError):
        manager.suspend("missing")


def test_manager_get_active():
    manager = make_manager()
    manager.create("Acme", tenant_id="acme")
    assert manager.get_active("acme").is_active
    manager.suspend("acme")
    with pytest.raises(TenantSuspendedError):
        manager.get_active("acme")
    config = make_config(enforce_active=False)
    manager2 = TenantManager(config=config)
    manager2.create("A", tenant_id="a")
    manager2.suspend("a")
    assert manager2.get_active("a").is_suspended
    manager2.delete("a")
    with pytest.raises(TenantDeletedError):
        manager2.get_active("a")


def test_manager_list_filters():
    manager = make_manager()
    manager.create("A", tenant_id="a", plan="free")
    manager.create("B", tenant_id="b", plan="pro")
    manager.create("C", tenant_id="c", plan="free")
    manager.suspend("c")
    manager.delete("b")
    assert [t.id for t in manager.list()] == ["a", "c"]
    assert [t.id for t in manager.list(include_deleted=True)] == ["a", "b", "c"]
    assert [t.id for t in manager.list(status="suspended")] == ["c"]
    assert [t.id for t in manager.list(status=TenantStatus.SUSPENDED)] == ["c"]
    assert [t.id for t in manager.list(plan="free")] == ["a", "c"]
    assert manager.count(status="active") == 1


def test_manager_set_config():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    manager.set_config("a", "llm", {"model": "gpt-4o"})
    assert manager.get("a").config_section("llm") == {"model": "gpt-4o"}
    with pytest.raises(ValueError):
        manager.set_config("a", "bogus", {})


def test_manager_async_variants():
    manager = make_manager()

    async def run():
        tenant = await manager.create_async("Acme", tenant_id="acme")
        assert (await manager.get_async("acme")).id == tenant.id
        updated = await manager.update_async("acme", name="New")
        assert updated.name == "New"
        assert (await manager.suspend_async("acme")).is_suspended
        assert (await manager.activate_async("acme")).is_active
        assert (await manager.list_async()) == [tenant]
        assert await manager.delete_async("acme") is True

    asyncio.run(run())


def test_audit_logger():
    logger = AuditLogger(make_config())
    logger.record("tenant.created", tenant_id="a", actor="admin", details={"x": 1})
    logger.record("tenant.created", tenant_id="b")
    assert logger.count() == 2
    assert logger.count(tenant_id="a") == 1
    events = logger.list(tenant_id="a")
    assert events[0].action == "tenant.created"
    assert events[0].to_dict()["actor"] == "admin"
    assert logger.list(limit=0) == logger.list()
    logger.clear()
    assert logger.count() == 0


def test_audit_logger_disabled():
    logger = AuditLogger(make_config(audit_enabled=False))
    logger.record("tenant.created", tenant_id="a")
    assert logger.count() == 0


def test_audit_events_attached_to_manager():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    manager.suspend("a")
    assert any(e.action == "tenant.created" for e in manager.audit.list())
    assert any(e.action == "tenant.suspended" for e in manager.audit.list())


def test_context_manager():
    cm = TenantContextManager(make_config())
    assert cm.is_set() is False
    assert cm.get() is None
    with pytest.raises(TenantContextMissingError):
        cm.require()
    anonymous = cm.get_or_anonymous()
    assert anonymous.tenant_id == "default"
    context = TenantContext(tenant_id="t1")
    token = cm.set(context)
    assert cm.is_set() is True
    assert cm.require().tenant_id == "t1"
    cm.clear(token)
    assert cm.is_set() is False
    token = cm.set(context)
    cm.clear()
    assert cm.get() is None
    assert cm.config is cm.config


def test_context_propagation_across_coroutines():
    cm = TenantContextManager(make_config())

    async def worker(tenant_id):
        await asyncio.sleep(0)
        context = cm.get()
        return context.tenant_id if context else None

    async def run():
        results = []
        for tid in ["a", "b", "a"]:
            token = cm.set(TenantContext(tenant_id=tid))
            try:
                results.append(await worker(tid))
            finally:
                cm.clear(token)
        return results

    assert asyncio.run(run()) == ["a", "b", "a"]


def test_context_run_with_context():
    cm = TenantContextManager(make_config())

    async def inner():
        return cm.require().tenant_id

    async def run():
        return await cm.run_with_context(TenantContext(tenant_id="t1"), inner())

    assert asyncio.run(run()) == "t1"
    assert cm.is_set() is False


def test_module_level_context_helpers():
    context = TenantContext(tenant_id="t1")
    token = set_current_tenant(context)
    try:
        assert get_current_tenant().tenant_id == "t1"
        assert require_current_tenant().tenant_id == "t1"
    finally:
        get_tenant_context_manager().clear(token)
    assert get_current_tenant() is None
    with pytest.raises(TenantContextMissingError):
        require_current_tenant()


def test_decode_jwt_claims():
    token = make_jwt({"tenant_id": "acme", "sub": "u1"})
    claims = decode_jwt_claims(token)
    assert claims["tenant_id"] == "acme"
    assert claims["sub"] == "u1"
    with pytest.raises(ValueError):
        decode_jwt_claims("not.a.jwt")
    with pytest.raises(ValueError):
        decode_jwt_claims("a.b.c.d")
    bad = base64.urlsafe_b64encode(b"not json").decode().rstrip("=")
    with pytest.raises(ValueError):
        decode_jwt_claims(f"h.{bad}.s")
    arr = base64.urlsafe_b64encode(b"[1,2]").decode().rstrip("=")
    with pytest.raises(ValueError):
        decode_jwt_claims(f"h.{arr}.s")


def test_resolver_explicit():
    resolver = TenantResolver(config=make_config())
    context = resolver.resolve(tenant_id="acme")
    assert context.tenant_id == "acme"
    assert context.resolved_by == "explicit"
    assert context.user_id == ""


def test_resolver_header_strategy():
    strategy = HeaderStrategy(make_config())
    context = strategy.resolve({"headers": {"X-Tenant-ID": "acme"}})
    assert context.tenant_id == "acme"
    assert context.resolved_by == "header"
    assert strategy.resolve({}) is None
    assert strategy.resolve({"headers": {"X-Tenant-ID": ""}}) is None


def test_resolver_jwt_strategy():
    strategy = JWTStrategy(make_config())
    context = strategy.resolve({"jwt_claims": {"tenant_id": "acme", "sub": "u1"}})
    assert context.tenant_id == "acme"
    assert context.user_id == "u1"
    assert context.resolved_by == "jwt"
    assert strategy.resolve({"jwt_claims": {}}) is None
    assert strategy.resolve({"jwt_claims": None, "jwt": make_jwt({"tenant_id": "x"})}) is not None
    assert strategy.resolve({}) is None
    wrong_issuer = strategy.resolve({"jwt_claims": {"tenant_id": "a", "iss": "evil"}})
    assert wrong_issuer is None
    allowed = strategy.resolve({"jwt_claims": {"tenant_id": "a", "iss": "airouter"}})
    assert allowed.tenant_id == "a"


def test_resolver_api_key_strategy():
    strategy = APIKeyStrategy(make_config())
    context = strategy.resolve({"api_key": "acme.abc123"})
    assert context.tenant_id == "acme"
    assert context.attributes["api_key"] == "acme.abc123"
    assert strategy.resolve({}) is None
    context = strategy.resolve({"headers": {"X-API-Key": "tenant2.key"}})
    assert context.tenant_id == "tenant2"
    lookup = APIKeyStrategy(make_config(), lookup=lambda key: "mapped" if key == "k1" else None)
    assert lookup.resolve({"api_key": "k1"}).tenant_id == "mapped"
    assert lookup.resolve({"api_key": "k2"}) is None

    def broken_lookup(key):
        raise RuntimeError("boom")

    broken = APIKeyStrategy(make_config(), lookup=broken_lookup)
    assert broken.resolve({"api_key": "k1"}) is None


def test_resolver_subdomain_strategy():
    strategy = SubdomainStrategy(make_config())
    context = strategy.resolve({"host": "acme.airouter.app"})
    assert context.tenant_id == "acme"
    context = strategy.resolve({"host": "acme.airouter.app:8080"})
    assert context.tenant_id == "acme"
    context = strategy.resolve({"headers": {"Host": "acme.airouter.app"}})
    assert context.tenant_id == "acme"
    assert strategy.resolve({"host": "airouter.app"}) is None
    assert strategy.resolve({"host": "api.acme.airouter.app"}) is None
    assert strategy.resolve({}) is None
    no_suffix = SubdomainStrategy(make_config(subdomain_suffix=""))
    assert no_suffix.resolve({"host": "acme.example.com"}).tenant_id == "acme"
    assert no_suffix.resolve({"host": "plain"}) is None


def test_resolver_custom_domain_strategy():
    config = make_config(custom_domain_map={"acme.com": "acme"})
    strategy = CustomDomainStrategy(config)
    context = strategy.resolve({"host": "acme.com"})
    assert context.tenant_id == "acme"
    context = strategy.resolve({"host": "acme.com:443"})
    assert context.tenant_id == "acme"
    assert strategy.resolve({"host": "other.com"}) is None
    assert strategy.resolve({}) is None


def test_resolver_full_flow():
    manager = make_manager()
    manager.create("Acme", tenant_id="acme")
    resolver = create_tenant_resolver(manager=manager)
    context = resolver.resolve(headers={"X-Tenant-ID": "acme"})
    assert context.tenant_id == "acme"
    assert context.tenant_name == "Acme"
    assert context.status == "active"
    assert context.merged is not None


def test_resolver_strategy_order_and_registration():
    resolver = TenantResolver(config=make_config())
    assert len(resolver.strategies) == 5

    class CustomStrategy:
        name = "custom"

        def resolve(self, request):
            return TenantContext(tenant_id="custom", resolved_by="custom")

    resolver.register(CustomStrategy())
    assert resolver.strategies[-1].name == "custom"
    context = resolver.resolve(headers={"X-Tenant-ID": "header-tenant"})
    assert context.tenant_id == "header-tenant"


def test_resolver_unknown_tenant_raises():
    manager = make_manager()
    resolver = TenantResolver(manager=manager, config=make_config())
    with pytest.raises(TenantResolutionError):
        resolver.resolve(headers={"X-Tenant-ID": "ghost"})


def test_resolver_suspended_tenant_raises():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    manager.suspend("a")
    resolver = TenantResolver(manager=manager, config=make_config())
    with pytest.raises(TenantSuspendedError):
        resolver.resolve(headers={"X-Tenant-ID": "a"})


def test_resolver_deleted_tenant_raises():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    manager.delete("a")
    resolver = TenantResolver(manager=manager, config=make_config())
    with pytest.raises(TenantResolutionError):
        resolver.resolve(headers={"X-Tenant-ID": "a"})


def test_resolver_anonymous():
    resolver = TenantResolver(config=make_config(allow_anonymous=True))
    context = resolver.resolve(headers={})
    assert context.tenant_id == "default"
    assert context.auth_method == "anonymous"
    resolver = TenantResolver(config=make_config(allow_anonymous=False))
    with pytest.raises(TenantResolutionError):
        resolver.resolve(headers={})


def test_resolver_with_request_dict():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    resolver = TenantResolver(manager=manager, config=make_config())
    context = resolver.resolve({"headers": {"X-Tenant-ID": "a"}})
    assert context.tenant_id == "a"


def test_resolver_strategy_exception_skipped():
    class ExplodingStrategy:
        name = "exploding"

        def resolve(self, request):
            raise RuntimeError("boom")

    resolver = TenantResolver(config=make_config(), strategies=[ExplodingStrategy()])
    context = resolver.resolve(tenant_id="direct")
    assert context.tenant_id == "direct"


def test_resolver_jwt_invalid_token():
    strategy = JWTStrategy(make_config())
    assert strategy.resolve({"jwt": "not.a.jwt"}) is None
    assert strategy.resolve({"jwt_claims": {"sub": "u1"}}) is None


def test_resolver_kwargs_parts():
    resolver = TenantResolver(config=make_config())
    context = resolver.resolve(
        jwt_claims={"tenant_id": "jwt-tenant", "sub": "u1"},
        jwt="header.payload.sig",
        api_key="key-tenant.k",
        host="sub.airouter.app",
    )
    assert context.tenant_id == "jwt-tenant"
    assert context.user_id == "u1"
    assert resolver.config is resolver.config
    context = resolver.resolve(api_key="key-tenant2.k")
    assert context.tenant_id == "key-tenant2"


def test_resolver_strategy_exception_falls_through():
    class ExplodingStrategy:
        name = "exploding"

        def resolve(self, request):
            raise RuntimeError("boom")

    resolver = TenantResolver(config=make_config(), strategies=[ExplodingStrategy()])
    with pytest.raises(TenantResolutionError):
        resolver.resolve(headers={"X-Tenant-ID": "x"})


def test_resolver_async():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    resolver = TenantResolver(manager=manager, config=make_config())

    async def run():
        return await resolver.resolve_async(headers={"X-Tenant-ID": "a"})

    assert asyncio.run(run()).tenant_name == "A"


def test_isolation_namespaces():
    isolation = TenantIsolation(make_config())
    assert isolation.key("t1", "k") == "tenant:t1:k"
    assert isolation.cache_key("t1", "k") == "tenant:t1:cache:k"
    assert isolation.kb_namespace("t1") == "tenant:t1:kb"
    assert isolation.vector_namespace("t1") == "tenant:t1:vectors"
    assert isolation.citation_namespace("t1") == "tenant:t1:citations"
    assert isolation.mcp_prefix("t1") == "tenant:t1:mcp"
    assert isolation.metrics_name("t1", "latency") == "tenant:t1:metrics:latency"
    assert isolation.log_name("t1", "chat") == "tenant:t1:logs:chat"
    assert isolation.prefix_for("x", "t1") == "tenant:t1:x"
    scope = isolation.memory_scope("t1", workspace_id="w", user_id="u", session_id="s")
    assert scope == {"tenant_id": "t1", "workspace_id": "w", "user_id": "u", "session_id": "s"}
    assert isolation.memory_scope("t1") == {"tenant_id": "t1"}


def test_isolation_enforce():
    isolation = TenantIsolation(make_config())
    context = TenantContext(tenant_id="t1")
    assert isolation.enforce(context).tenant_id == "t1"
    with pytest.raises(TenantContextMissingError):
        isolation.enforce(None)
    with pytest.raises(TenantContextMissingError):
        isolation.enforce(TenantContext(tenant_id=""))
    with pytest.raises(TenantSuspendedError):
        isolation.enforce(TenantContext(tenant_id="t1", status="suspended"))
    with pytest.raises(TenantIsolationError):
        isolation.enforce(TenantContext(tenant_id="t1", status="deleted"))
    loose = TenantIsolation(make_config(enforce_active=False))
    assert loose.enforce(TenantContext(tenant_id="t1", status="suspended")).status == "suspended"


def test_isolation_assert_isolated():
    isolation = TenantIsolation(make_config())
    isolation.assert_isolated(TenantContext(tenant_id="t1"), TenantContext(tenant_id="t1"))
    isolation.assert_isolated(TenantContext(tenant_id="t1"), None)
    isolation.assert_isolated(None, None)
    with pytest.raises(TenantIsolationError):
        isolation.assert_isolated(
            TenantContext(tenant_id="t1"), TenantContext(tenant_id="t2")
        )


def test_metrics_tracker():
    tracker = TenancyMetricsTracker(make_config())
    tracker.record_request("t1", 10.5)
    tracker.record_request("t1", 20.5, success=False)
    tracker.record_error("t1", "timeout")
    tracker.record_resolution("t1", "header")
    tracker.record_resolution("t1", "jwt", success=False)
    by_tenant = tracker.by_tenant("t1")
    assert by_tenant["requests"] == 2
    assert by_tenant["avg_latency_ms"] == 15.5
    assert by_tenant["total_errors"] == 2
    assert by_tenant["resolutions"]["header:ok"] == 1
    assert by_tenant["resolutions"]["jwt:fail"] == 1
    summary = tracker.summary()
    assert summary["total_requests"] == 2
    assert summary["tenants"] == ["t1"]
    assert "uptime_seconds" in summary
    assert tracker.enabled is True
    tracker.reset()
    assert tracker.summary()["total_requests"] == 0


def test_metrics_tracker_disabled():
    tracker = TenancyMetricsTracker(make_config(track_metrics=False))
    tracker.record_request("t1", 1.0)
    assert tracker.summary()["total_requests"] == 0
    assert tracker.enabled is False


def test_config_service():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    service = TenantConfigService(manager=manager, config=make_config())
    llm = service.get("a", "llm")
    assert llm["provider"] == "openai"
    assert llm["model"] == "gpt-4o-mini"
    updated = service.set("a", "llm", {"model": "gpt-4o"})
    assert updated["model"] == "gpt-4o"
    assert service.get("a", "llm")["model"] == "gpt-4o"
    effective = service.effective("a")
    assert set(effective.keys()) == set(service.sections)
    assert effective["mcp"]["enabled"] is True
    service.update_defaults({"llm": {"temperature": 0.2}})
    assert service.get("a", "llm")["temperature"] == 0.2
    with pytest.raises(ValueError):
        service.get("a", "bogus")
    with pytest.raises(ValueError):
        service.set("a", "bogus", {})
    with pytest.raises(ValueError):
        service.update_defaults({"bogus": {}})


def test_config_service_tenant_overrides():
    manager = make_manager()
    manager.create("A", tenant_id="a", config={"prompts": {"system": "be brief"}})
    service = TenantConfigService(manager=manager)
    assert service.get("a", "prompts")["system"] == "be brief"
    assert service.get("b", "prompts")["system"] == ""


def test_middleware_happy_path():
    app = FakeASGIApp()
    manager = make_manager()
    manager.create("A", tenant_id="a")
    middleware = TenantMiddleware(
        app, resolver=TenantResolver(manager=manager, config=make_config()), config=make_config()
    )
    messages = asyncio.run(
        run_asgi(middleware, make_scope(headers={"X-Tenant-ID": "a"}))
    )
    assert messages[0]["status"] == 200
    assert len(app.calls) == 1
    assert middleware.context_manager.is_set() is False
    assert middleware.context_manager.get() is None
    assert middleware._metrics.by_tenant("a")["requests"] == 1


def test_middleware_metrics_failure_status():
    app = FakeASGIApp(status=500)
    manager = make_manager()
    manager.create("A", tenant_id="a")
    middleware = TenantMiddleware(
        app, resolver=TenantResolver(manager=manager, config=make_config()), config=make_config()
    )
    asyncio.run(run_asgi(middleware, make_scope(headers={"X-Tenant-ID": "a"})))
    assert middleware._metrics.by_tenant("a")["total_errors"] == 1


def test_middleware_resolution_failure():
    app = FakeASGIApp()
    middleware = TenantMiddleware(
        app, resolver=TenantResolver(config=make_config()), config=make_config()
    )
    messages = asyncio.run(run_asgi(middleware, make_scope(headers={})))
    assert messages[0]["status"] == 401
    assert app.calls == []


def test_middleware_suspended_403():
    app = FakeASGIApp()
    manager = make_manager()
    manager.create("A", tenant_id="a")
    manager.suspend("a")
    middleware = TenantMiddleware(
        app, resolver=TenantResolver(manager=manager, config=make_config()), config=make_config()
    )
    messages = asyncio.run(
        run_asgi(middleware, make_scope(headers={"X-Tenant-ID": "a"}))
    )
    assert messages[0]["status"] == 403
    assert b"blocked" in messages[1]["body"]


def test_middleware_unknown_tenant_401():
    app = FakeASGIApp()
    manager = make_manager()
    middleware = TenantMiddleware(
        app, resolver=TenantResolver(manager=manager, config=make_config()), config=make_config()
    )
    messages = asyncio.run(
        run_asgi(middleware, make_scope(headers={"X-Tenant-ID": "ghost"}))
    )
    assert messages[0]["status"] == 401


def test_middleware_non_http_scope():
    recorded = []

    async def passthrough_app(scope, receive, send):
        recorded.append(scope)
        if scope.get("type") == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    middleware = TenantMiddleware(
        app=passthrough_app,
        resolver=TenantResolver(config=make_config()),
        config=make_config(),
    )
    messages = asyncio.run(run_asgi(middleware, make_scope(type_="websocket")))
    assert messages == []
    assert len(recorded) == 1
    assert middleware._metrics.summary()["total_requests"] == 0


def test_middleware_resolver_exception():
    app = FakeASGIApp()

    class ExplodingResolver:
        def resolve(self, **kwargs):
            raise RuntimeError("boom")

    middleware = TenantMiddleware(
        app, resolver=ExplodingResolver(), config=make_config()
    )
    messages = asyncio.run(run_asgi(middleware, make_scope(headers={"X-Tenant-ID": "a"})))
    assert messages[0]["status"] == 401


def test_middleware_isolation_blocked_403():
    app = FakeASGIApp()

    class SuspendedContextResolver:
        def resolve(self, **kwargs):
            return TenantContext(tenant_id="a", status="suspended")

    middleware = TenantMiddleware(
        app, resolver=SuspendedContextResolver(), config=make_config()
    )
    messages = asyncio.run(run_asgi(middleware, make_scope(headers={"X-Tenant-ID": "a"})))
    assert messages[0]["status"] == 403


def test_middleware_context_set_during_request():
    app = FakeASGIApp()
    observed = {}

    async def context_app(scope, receive, send):
        observed["tenant"] = require_current_tenant().tenant_id
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = TenantMiddleware(
        app=context_app,
        resolver=TenantResolver(config=make_config()),
        config=make_config(),
    )
    asyncio.run(run_asgi(middleware, make_scope(headers={"X-Tenant-ID": "a"})))
    assert observed["tenant"] == "a"


def test_middleware_headers_from_scope_bytes():
    app = FakeASGIApp()
    middleware = TenantMiddleware(
        app, resolver=TenantResolver(config=make_config()), config=make_config()
    )
    scope = make_scope()
    scope["headers"] = [(b"X-Tenant-ID", b"byted")] + scope["headers"]
    messages = asyncio.run(run_asgi(middleware, scope))
    assert messages[0]["status"] == 200


def test_middleware_fastapi_adapter():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    middleware = TenantMiddleware(
        app=FakeASGIApp(),
        resolver=TenantResolver(manager=manager, config=make_config()),
        config=make_config(),
    )

    class FakeRequest:
        def __init__(self):
            self.headers = {"X-Tenant-ID": "a"}
            self.url = type("URL", (), {"hostname": "acme.airouter.app"})()

        async def __aenter__(self):
            return self

    async def call_next(request):
        assert middleware.context_manager.require().tenant_id == "a"
        return "response"

    async def run():
        return await middleware.fastapi_http(FakeRequest(), call_next)

    assert asyncio.run(run()) == "response"
    assert middleware.context_manager.is_set() is False


def test_factories():
    manager = create_tenant_manager(config=make_config())
    assert isinstance(manager, TenantManager)
    resolver = create_tenant_resolver(manager=manager, config=make_config())
    assert isinstance(resolver, TenantResolver)
    middleware = create_tenant_middleware(
        app=FakeASGIApp(), resolver=resolver, config=make_config()
    )
    assert isinstance(middleware, TenantMiddleware)
    context = create_tenant_context("t1", tenant_name="Acme", attributes={"k": "v"})
    assert context.tenant_id == "t1"
    assert context.attributes == {"k": "v"}
    service = create_tenant_config_service(manager, config=make_config())
    assert isinstance(service, TenantConfigService)


def test_tenant_context_merged_none():
    context = TenantContext(tenant_id="t1")
    assert context.merged(None) is context


def test_tenant_not_found_helper():
    from app.tenancy.models import tenant_not_found

    error = tenant_not_found("t1")
    assert error.tenant_id == "t1"


def test_audit_logger_trimming():
    logger = AuditLogger(make_config(), max_events=2)
    logger.record("e1", tenant_id="a")
    logger.record("e2", tenant_id="b")
    logger.record("e3", tenant_id="c")
    assert logger.count() == 2
    assert [e.tenant_id for e in logger.list()] == ["b", "c"]


def test_context_get_or_anonymous_with_context():
    cm = TenantContextManager(make_config())
    cm.set(TenantContext(tenant_id="t1"))
    assert cm.get_or_anonymous().tenant_id == "t1"
    cm.clear()


def test_isolation_config_property():
    config = make_config()
    isolation = TenantIsolation(config)
    assert isolation.config is config


def test_metrics_tracker_resolution_disabled():
    tracker = TenancyMetricsTracker(make_config(track_metrics=False))
    tracker.record_resolution("t1", "header")
    tracker.record_error("t1", "x")
    assert tracker.summary()["total_errors"] == 0


def test_tenancy_logger_fallback():
    class Unserializable:
        def __str__(self):
            raise ValueError("nope")

    logger = TenancyLogger()
    logger.log_event("test", tenant_id="t1", value=Unserializable())


def test_middleware_fastapi_adapter_call_next_raises():
    manager = make_manager()
    manager.create("A", tenant_id="a")
    middleware = TenantMiddleware(
        app=FakeASGIApp(),
        resolver=TenantResolver(manager=manager, config=make_config()),
        config=make_config(),
    )

    class FakeRequest:
        def __init__(self):
            self.headers = {"X-Tenant-ID": "a"}
            self.url = type("URL", (), {"hostname": "acme.airouter.app"})()

    async def call_next(request):
        raise RuntimeError("downstream exploded")

    async def run():
        with pytest.raises(RuntimeError):
            await middleware.fastapi_http(FakeRequest(), call_next)
        return True

    assert asyncio.run(run()) is True
    assert middleware.context_manager.is_set() is False


def test_default_components_share_config():
    config = make_config()
    manager = TenantManager(config=config)
    assert manager.repository is not None
    assert manager.audit is not None
    assert manager._logger is not None
