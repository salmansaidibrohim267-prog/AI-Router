"""Stage 10.7 — Plugin & Extension Platform tests."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

from app.plugins import (
    CompatibilityChecker,
    Container,
    ContainerError,
    Extension,
    ExtensionAlreadyRegisteredError,
    ExtensionKind,
    ExtensionNotFoundError,
    ExtensionRegistry,
    HookResult,
    HookSystem,
    ManifestValidator,
    Marketplace,
    MarketplaceEntry,
    PermissionManager,
    PermissionResource,
    Plugin,
    PluginAlreadyInstalledError,
    PluginCompatibilityError,
    PluginConfig,
    PluginContext,
    PluginError,
    PluginInfo,
    PluginInstallError,
    PluginInvalidError,
    PluginLifecycle,
    PluginLifecycleError,
    PluginLogger,
    PluginManager,
    PluginManagerSource,
    PluginMarketplaceError,
    PluginMetricsTracker,
    PluginNotFoundError,
    PluginPermissionDeniedError,
    PluginRatingError,
    PluginRollbackError,
    PluginSandboxViolationError,
    PluginSDK,
    PluginSignatureError,
    PluginSpec,
    PluginStatus,
    PluginTimeoutError,
    PluginUninstallError,
    PluginUpgradeError,
    PluginVerificationError,
    Rating,
    Sandbox,
    SchedulerSpec,
    Signature,
    compare_versions,
    compute_digest,
    create_plugin_manager,
    generate_id,
    hash_directory,
    is_valid_version,
    parse_version,
    sign_payload,
    verify_or_raise,
    verify_payload,
    version_meets,
)
from app.plugins.events import (
    PLUGIN_DISABLED,
    PLUGIN_ENABLED,
    PLUGIN_FAILED,
    PLUGIN_INSTALLED,
    PLUGIN_RELOADED,
    PLUGIN_UNINSTALLED,
    PLUGIN_UPGRADED,
    PLUGIN_VERIFIED,
    PluginEventBus,
)
TEST_ROUTER_VERSION = "2.0.0"


def run(coro):
    return asyncio.run(coro)


def make_config(tmp_path, **kwargs):
    defaults = {"plugins_dir": str(tmp_path / "ext"), "signature_secret": "s3cret", "require_signatures": False}
    defaults.update(kwargs)
    return PluginConfig(**defaults)


def make_spec(name="demo", version="1.0.0", **overrides):
    spec = {
        "name": name,
        "version": version,
        "entry": "create_plugin",
        "description": "test plugin",
        "author": "tester",
        "permissions": [{"resource": "filesystem", "actions": ["read"]}],
    }
    spec.update(overrides)
    return spec


def make_code(tools: list[str] | None = None, hooks: dict[str, str] | None = None, version="1.0.0", name="demo"):
    lines = ["from app.plugins import Plugin", "", "class DemoPlugin(Plugin):", f"    name = \"{name}\"", f"    version = \"{version}\"", "", "def create_plugin(sdk):", "    p = DemoPlugin(sdk)"]
    for tool in tools or []:
        lines.append(f'    sdk.register_tool("{tool}", lambda: "{tool} ok")')
    for event, handler in (hooks or {}).items():
        lines.append(f'    sdk.register_event_listener("{event}", {handler})')
    lines.append("    return p")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------- config


class TestConfig:
    def test_defaults(self):
        config = PluginConfig()
        assert config.timeout_seconds == 30.0
        assert config.max_memory_mb == 512.0
        assert config.network_allowed is False
        assert config.auto_enable is True
        assert config.max_plugins == 100

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("PLG_DIR", "/tmp/plg")
        monkeypatch.setenv("PLG_TIMEOUT", "5")
        monkeypatch.setenv("PLG_NETWORK", "1")
        monkeypatch.setenv("PLG_REQUIRE_SIGNATURES", "1")
        monkeypatch.setenv("PLG_AUTO_ENABLE", "0")
        config = PluginConfig.from_env()
        assert config.plugins_dir == "/tmp/plg"
        assert config.timeout_seconds == 5.0
        assert config.network_allowed is True
        assert config.require_signatures is True
        assert config.auto_enable is False

    def test_as_dict(self):
        data = make_config(Path(".")).as_dict()
        assert data["plugins_dir"] == "ext"
        assert "timeout_seconds" in data
        assert "max_plugins" in data


# ---------------------------------------------------------------- exceptions


class TestExceptions:
    def test_base(self):
        error = PluginError("boom", code=1)
        assert error.message == "boom"
        assert error.details == {"code": 1}
        assert error.status_code == 400
        assert error.error_code == "plugin_error"

    def test_subclass_codes(self):
        assert PluginNotFoundError("x").status_code == 404
        assert PluginAlreadyInstalledError("x").status_code == 409
        assert PluginInstallError("x").status_code == 500
        assert PluginUninstallError("x").status_code == 500
        assert PluginVerificationError("x").status_code == 422
        assert PluginInvalidError("x").status_code == 422
        assert PluginSandboxViolationError("x").status_code == 403
        assert PluginTimeoutError("x").status_code == 504
        assert PluginPermissionDeniedError("x").status_code == 403
        assert PluginSignatureError("x").status_code == 403
        assert PluginCompatibilityError("x").status_code == 422
        assert PluginUpgradeError("x").status_code == 500
        assert PluginRollbackError("x").status_code == 500
        assert PluginLifecycleError("x").status_code == 409
        assert PluginMarketplaceError("x").status_code == 404
        assert PluginRatingError("x").status_code == 422
        assert ExtensionAlreadyRegisteredError("x").status_code == 409
        assert ExtensionNotFoundError("x").status_code == 404
        assert ContainerError("x").status_code == 500


# ------------------------------------------------------------------- logging


class TestLogger:
    def test_log_event(self):
        logger = PluginLogger(PluginConfig(log_events=True))
        logger.log_event("installed", plugin="demo")
        assert logger.events[0]["event"] == "plugin_installed"
        assert logger.events[0]["data"] == {"plugin": "demo"}

    def test_disabled(self):
        logger = PluginLogger(PluginConfig(log_events=False))
        logger.log_event("x")
        assert logger.events == []

    def test_non_serializable_payload(self):
        logger = PluginLogger(PluginConfig(log_events=True))
        logger.log_event("x", payload={"data": {1, 2}})
        assert logger.events[0]["event"] == "plugin_x"


# --------------------------------------------------------------------- models


class TestModels:
    def test_generate_id(self):
        assert generate_id("plg").startswith("plg_")

    def test_statuses(self):
        assert PluginStatus.DRAFT.value == "draft"
        assert PluginStatus.ENABLED.value == "enabled"
        assert PluginStatus.ROLLING_BACK.value == "rolling_back"
        assert PluginStatus.UNINSTALLED.value == "uninstalled"
        assert len(list(PluginStatus)) == 14

    def test_extension_kinds(self):
        assert {kind.value for kind in ExtensionKind} == {
            "tool", "route", "mcp_provider", "llm_provider", "embedding_model", "scheduler", "cli_command", "event_listener",
        }

    def test_permission_resources(self):
        assert PermissionResource.NETWORK.value == "network"

    def test_plugin_spec_to_dict(self):
        spec = PluginSpec(name="demo", version="1.0.0", permissions=[{"resource": "x", "actions": ["read"]}])
        data = spec.to_dict()
        assert data["name"] == "demo"
        assert data["entry"] == "create_plugin"
        assert data["permissions"] == [{"resource": "x", "actions": ["read"]}]
        assert "installed_at" in data

    def test_plugin_info_to_dict(self):
        info = PluginInfo(name="demo", version="1.0.0", status=PluginStatus.ENABLED, extensions={"tool": ["greet"]}, error="")
        data = info.to_dict()
        assert data["status"] == "enabled"
        assert data["extensions"] == {"tool": ["greet"]}
        assert data["error"] == ""
        assert "updated_at" in data

    def test_extension_to_dict(self):
        extension = Extension(kind=ExtensionKind.TOOL, name="t", handler=lambda: None, plugin="p", metadata={"schema": {}})
        data = extension.to_dict()
        assert data["kind"] == "tool"
        assert data["plugin"] == "p"
        assert data["metadata"] == {"schema": {}}

    def test_signature_rating_scheduler(self):
        assert Signature(digest="abc").to_dict() == {"algorithm": "hmac-sha256", "digest": "abc"}
        rating = Rating(entry_id="e1", user="u", score=5, comment="great")
        assert rating.to_dict()["score"] == 5
        assert SchedulerSpec(interval_seconds=60).to_dict() == {"interval_seconds": 60, "cron": "", "max_runs": 0}


# ---------------------------------------------------------------- versioning


class TestVersioning:
    def test_is_valid_version(self):
        assert is_valid_version("1.0.0")
        assert is_valid_version("2.1.3-rc.1")
        assert not is_valid_version("1.0")
        assert not is_valid_version("v1.0.0")
        assert not is_valid_version("")

    def test_parse_version(self):
        assert parse_version("1.2.3") == (1, 2, 3, "")
        assert parse_version("1.2.3-rc.1") == (1, 2, 3, "rc.1")
        with pytest.raises(ValueError):
            parse_version("nope")

    def test_compare(self):
        assert compare_versions("1.0.0", "2.0.0") == -1
        assert compare_versions("2.0.0", "1.0.0") == 1
        assert compare_versions("1.2.3", "1.2.3") == 0
        assert compare_versions("1.10.0", "1.9.0") == 1
        assert compare_versions("1.0.0", "1.0.0-rc.1") == 1
        assert compare_versions("1.0.0-rc.1", "1.0.0") == -1

    def test_version_meets(self):
        assert version_meets("2.0.0", "")
        assert version_meets("2.0.0", ">=2.0.0")
        assert not version_meets("1.9.0", ">=2.0.0")
        assert version_meets("2.0.1", "<=2.0.1")
        assert version_meets("3.0.0", ">2.0.0")
        assert version_meets("1.5.0", "<2.0.0")
        assert version_meets("2.1.0", "^2.0.0")
        assert not version_meets("1.9.0", "^2.0.0")
        assert not version_meets("3.0.0", "^2.0.0")
        assert version_meets("2.2.5", "~2.2.0")
        assert not version_meets("2.3.0", "~2.2.0")
        assert not version_meets("2.1.0", "~2.2.0")
        assert version_meets("1.0.0", "1.0.0")


# ------------------------------------------------------------------- signing


class TestSigning:
    def test_roundtrip(self):
        payload = {"name": "demo", "version": "1.0.0"}
        signature = sign_payload(payload, "secret")
        assert verify_payload(payload, signature, "secret") is True

    def test_tamper(self):
        payload = {"name": "demo", "version": "1.0.0"}
        signature = sign_payload(payload, "secret")
        assert verify_payload({"name": "evil", "version": "1.0.0"}, signature, "secret") is False
        assert verify_payload(payload, signature, "other") is False
        assert verify_payload(payload, "bad", "secret") is False
        assert verify_payload(payload, Signature(), "secret") is False
        assert verify_payload(payload, signature, "") is False

    def test_verify_or_raise(self):
        payload = {"name": "demo", "version": "1.0.0"}
        signature = sign_payload(payload, "secret")
        verify_or_raise(payload, signature, "secret", "demo")
        with pytest.raises(PluginSignatureError):
            verify_or_raise(payload, "forged", "secret", "demo")

    def test_compute_digest(self):
        assert len(compute_digest(b"data")) == 64
        assert compute_digest(b"data") == compute_digest(b"data")

    def test_hash_directory(self, tmp_path):
        root = tmp_path / "pkg"
        root.mkdir()
        (root / "a.txt").write_text("hello")
        (root / "b").mkdir()
        (root / "b" / "c.txt").write_text("world")
        digest = hash_directory(str(root))
        assert len(digest) == 64
        (root / "a.txt").write_text("changed")
        assert hash_directory(str(root)) != digest
        assert hash_directory(str(tmp_path / "missing")) == ""


# ---------------------------------------------------------------- validation


class TestValidation:
    def test_valid_manifest(self):
        assert ManifestValidator().validate(make_spec()) == []

    def test_missing_fields(self):
        errors = ManifestValidator().validate({"name": "demo"})
        assert "missing required field 'version'" in errors
        assert "missing required field 'entry'" in errors

    def test_bad_name_version_entry(self):
        errors = ManifestValidator().validate(make_spec(name="Bad Name", version="abc", entry="9bad"))
        assert any("invalid plugin name" in error for error in errors)
        assert any("invalid semver" in error for error in errors)
        assert any("invalid entry point" in error for error in errors)

    def test_bad_permissions(self):
        errors = ManifestValidator().validate(
            make_spec(permissions=[{"resource": "unknown_resource", "actions": []}, {"actions": ["nope"]}, "bad"])
        )
        assert any("unknown resource" in error for error in errors)
        assert any("invalid actions" in error for error in errors)
        assert any("must be a mapping" in error for error in errors)
        errors = ManifestValidator().validate(make_spec(permissions="nope"))
        assert any("permissions must be a list" in error for error in errors)

    def test_not_a_mapping(self):
        assert ManifestValidator().validate([]) == ["manifest must be a mapping"]

    def test_bad_signature_type(self):
        errors = ManifestValidator().validate(make_spec(signature=123))
        assert any("signature must be a string" in error for error in errors)

    def test_validate_or_raise(self):
        validator = ManifestValidator()
        validator.validate_or_raise(make_spec())
        with pytest.raises(PluginInvalidError):
            validator.validate_or_raise(make_spec(version="nope"))

    def test_compatibility(self):
        checker = CompatibilityChecker(router_version=TEST_ROUTER_VERSION)
        assert checker.check(make_spec()) == []
        issues = checker.check(make_spec(requires_router=">=3.0.0"))
        assert "requires router" in issues[0]
        issues = checker.check(make_spec(tags=["deprecated"]))
        assert issues == ["plugin is marked deprecated"]
        issues = checker.check(make_spec(tags="nope"))
        assert issues == ["tags must be a list"]
        issues = checker.check(make_spec(), extension_count=9999)
        assert "exceeds limit" in issues[0]
        with pytest.raises(PluginCompatibilityError):
            checker.check_or_raise(make_spec(requires_router=">=99.0.0"))


# ---------------------------------------------------------------- permissions


class TestPermissions:
    def test_deny_by_default(self):
        permissions = PermissionManager()
        assert permissions.check("demo", "filesystem", "read") is False
        assert permissions.permissions("demo") == {}

    def test_grant_and_check(self):
        permissions = PermissionManager()
        permissions.grant("demo", "filesystem", ["read"])
        assert permissions.check("demo", "filesystem", "read") is True
        assert permissions.check("demo", "filesystem", "write") is False
        permissions.grant("demo", "filesystem", ["write"])
        assert permissions.check("demo", "filesystem", "write") is True

    def test_wildcard(self):
        permissions = PermissionManager()
        permissions.grant("demo", "network", ["*"])
        assert permissions.check("demo", "network", "connect") is True

    def test_grant_from_manifest(self):
        permissions = PermissionManager()
        permissions.grant_from_manifest("demo", [{"resource": "secrets", "actions": ["access"]}, {"resource": "network"}])
        assert permissions.check("demo", "secrets", "access") is True
        assert permissions.check("demo", "network", "connect") is True

    def test_revoke(self):
        permissions = PermissionManager()
        permissions.grant("demo", "filesystem", ["read", "write"])
        assert permissions.revoke("nope") is False
        assert permissions.revoke("demo", "network") is False
        assert permissions.revoke("demo", "filesystem", "read") is True
        assert permissions.check("demo", "filesystem", "read") is False
        assert permissions.revoke("demo", "filesystem") is True
        assert permissions.check("demo", "filesystem", "write") is False
        permissions.grant("demo", "filesystem", ["read"])
        assert permissions.revoke("demo") is True
        assert permissions.permissions("demo") == {}
        permissions.grant("demo", "network", ["connect"])
        assert permissions.revoke("demo", "network", "connect") is True
        assert permissions.check("demo", "network", "connect") is False

    def test_check_or_raise(self):
        permissions = PermissionManager()
        with pytest.raises(PluginPermissionDeniedError):
            permissions.check_or_raise("demo", "filesystem", "read")
        permissions.grant("demo", "filesystem", ["read"])
        permissions.check_or_raise("demo", "filesystem", "read")

    def test_snapshot(self):
        permissions = PermissionManager()
        permissions.grant("demo", "filesystem", ["read", "write"])
        assert permissions.permissions("demo") == {"filesystem": ["read", "write"]}
        assert permissions.all_permissions() == {"demo": {"filesystem": ["read", "write"]}}
        permissions.clear()
        assert permissions.all_permissions() == {}


# -------------------------------------------------------------------- sandbox


class TestSandbox:
    def test_path_allowlist(self, tmp_path):
        config = make_config(tmp_path, fs_allowed_paths=[str(tmp_path)])
        sandbox = Sandbox(config)
        assert sandbox.is_path_allowed(str(tmp_path / "x" / "y")) is True
        assert sandbox.is_path_allowed("/etc/passwd") is False
        sandbox.check_path(str(tmp_path))
        with pytest.raises(PluginSandboxViolationError):
            sandbox.check_path("/etc/passwd")
        assert sandbox.allowed_paths() == [str(tmp_path)]

    def test_network_and_process(self):
        sandbox = Sandbox(make_config(Path(".")))
        with pytest.raises(PluginSandboxViolationError):
            sandbox.check_network()
        with pytest.raises(PluginSandboxViolationError):
            sandbox.check_process()
        open_sandbox = Sandbox(make_config(Path("."), network_allowed=True, processes_allowed=True))
        open_sandbox.check_network()
        open_sandbox.check_process()

    def test_cpu(self):
        sandbox = Sandbox(make_config(Path(".")))
        sandbox.check_cpu()
        with pytest.raises(PluginSandboxViolationError):
            Sandbox(make_config(Path("."), cpu_limit=0)).check_cpu()

    def test_memory(self):
        sandbox = Sandbox(make_config(Path(".")))
        assert sandbox.memory_usage_mb() > 0
        sandbox.check_memory()
        with pytest.raises(PluginSandboxViolationError):
            Sandbox(make_config(Path("."), max_memory_mb=0.001)).check_memory()

    def test_verify_environment(self):
        sandbox = Sandbox(make_config(Path(".")))
        sandbox.verify_environment()
        missing = Sandbox(make_config(Path("."), fs_allowed_paths=["/definitely/missing/dir"]))
        missing.verify_environment()

    def test_execute(self):
        sandbox = Sandbox(make_config(Path("."), timeout_seconds=1.0))
        assert sandbox.execute(lambda: 42) == 42
        assert sandbox.execute(lambda a, b: a + b, 1, 2) == 3

    def test_execute_timeout(self):
        sandbox = Sandbox(make_config(Path("."), timeout_seconds=0.2))

        def slow():
            time.sleep(2)

        with pytest.raises(PluginTimeoutError):
            sandbox.execute(slow, timeout=0.1)

    def test_run(self):
        sandbox = Sandbox(make_config(Path("."), timeout_seconds=1.0))

        async def ok():
            return "done"

        assert run(sandbox.run(ok())) == "done"

    def test_run_timeout(self):
        sandbox = Sandbox(make_config(Path("."), timeout_seconds=0.2))

        async def slow():
            await asyncio.sleep(2)

        with pytest.raises(PluginTimeoutError):
            run(sandbox.run(slow(), timeout=0.1))

    def test_shutdown(self):
        sandbox = Sandbox(make_config(Path(".")))
        sandbox.shutdown()

    def test_timeout_property(self):
        assert Sandbox(make_config(Path("."), timeout_seconds=7.0)).timeout_seconds == 7.0


# -------------------------------------------------------------------- events


class TestEventBus:
    def test_subscribe_emit(self):
        bus = PluginEventBus()
        seen: list[tuple[str, str]] = []

        def sync_handler(name: str, plugin: str = "") -> None:
            seen.append(("sync", name))

        async def async_handler(name: str, plugin: str = "") -> None:
            seen.append(("async", name))

        bus.subscribe("demo.ping", sync_handler)
        bus.subscribe("demo.ping", async_handler)
        results = bus.emit("demo.ping", name="p")
        assert len(results) == 2
        assert sorted(seen) == [("async", "p"), ("sync", "p")]
        assert bus.subscribers("demo.ping") == [sync_handler, async_handler]
        bus.unsubscribe("demo.ping", sync_handler)
        assert bus.subscribers("demo.ping") == [async_handler]

    def test_emit_plugin_event(self):
        bus = PluginEventBus()
        seen: list[dict] = []
        bus.subscribe("plugin.installed", lambda **kw: seen.append(kw))
        bus.emit_plugin_event("plugin.installed", plugin="demo", version="1.0.0")
        run(bus.emit_plugin_event_async("plugin.installed", plugin="other"))
        assert seen[0]["plugin"] == "demo"
        assert seen[1]["plugin"] == "other"

    def test_handler_error_is_captured(self):
        bus = PluginEventBus()

        def boom(**kw):
            raise RuntimeError("handler exploded")

        bus.subscribe("x", boom)
        assert bus.emit("x") == []

    def test_async_handler_running_loop(self):
        bus = PluginEventBus()
        done = asyncio.Event()

        async def handler(**kw):
            done.set()

        bus.subscribe("e", handler)

        async def inside():
            bus.emit("e")
            await asyncio.wait_for(done.wait(), timeout=2)

        run(inside())
        assert done.is_set()

    def test_history_trim(self):
        bus = PluginEventBus()
        for index in range(1005):
            bus.emit("a", v=index)
        assert len(bus.get_history(2000)) == 1000

    def test_factory(self):
        from app.plugins.events import create_plugin_event_bus

        assert isinstance(create_plugin_event_bus(), PluginEventBus)

    def test_history_and_clear(self):
        bus = PluginEventBus()
        bus.emit("a", v=1)
        bus.emit("b", v=2)
        history = bus.get_history()
        assert [entry["event"] for entry in history] == ["a", "b"]
        assert bus.event_names() == []
        bus.clear()
        assert bus.get_history() == []


# --------------------------------------------------------------------- hooks


class TestHookSystem:
    def test_register_unregister(self):
        hooks = HookSystem()
        listener = lambda: None
        assert hooks.unregister("h", listener) is False
        hooks.register("h", listener, plugin="demo")
        assert hooks.listeners("h") == [("demo", listener)]
        assert hooks.has_listener("h") is True
        assert hooks.hook_names() == ["h"]
        assert hooks.unregister("h", listener) is True
        assert hooks.has_listener("h") is False

    def test_dispatch_sync_listeners(self):
        hooks = HookSystem()
        calls: list[str] = []
        hooks.register("pre", lambda v: calls.append(f"a{v}"))
        hooks.register("pre", lambda v: calls.append(f"b{v}"))
        run(hooks.dispatch("pre", 1))
        assert calls == ["a1", "b1"]

    def test_dispatch_async_listeners(self):
        hooks = HookSystem()

        async def handler(v):
            return HookResult(payload={"v": v})

        hooks.register("h", handler)
        result = run(hooks.dispatch("h", 5))
        assert result.payload == {"v": 5}
        assert result.should_cancel is False

    def test_cancel_stops_chain(self):
        hooks = HookSystem()
        calls: list[str] = []
        hooks.register("h", lambda: calls.append("first"))
        hooks.register("h", lambda: HookResult(should_cancel=True, cancel_reason="enough"))
        hooks.register("h", lambda: calls.append("third"))
        result = run(hooks.dispatch("h"))
        assert result.should_cancel is True
        assert result.cancel_reason == "enough"

    def test_hook_result_to_dict(self):
        result = HookResult(should_cancel=True, cancel_reason="nope", payload={"a": 1})
        assert result.to_dict() == {"should_cancel": True, "cancel_reason": "nope", "payload": {"a": 1}}

    def test_listener_exception_captured(self):
        hooks = HookSystem()
        calls: list[str] = []

        def boom():
            raise ValueError("nope")

        hooks.register("h", boom)
        hooks.register("h", lambda: calls.append("after"))
        result = run(hooks.dispatch("h"))
        assert result.should_cancel is False
        assert calls == ["after"]

    def test_plugins_filter(self):
        hooks = HookSystem()
        calls: list[str] = []
        hooks.register("h", lambda: calls.append("a"), plugin="alpha")
        hooks.register("h", lambda: calls.append("b"), plugin="beta")
        hooks.register("h", lambda: calls.append("plain"))
        run(hooks.dispatch("h", plugins={"alpha"}))
        assert calls == ["a", "plain"]

    def test_unregister_plugin(self):
        hooks = HookSystem()
        hooks.register("h1", lambda: None, plugin="demo")
        hooks.register("h2", lambda: None, plugin="demo")
        hooks.register("h2", lambda: None, plugin="other")
        assert hooks.unregister_plugin("demo") == 2
        assert hooks.listeners("h1") == []
        assert len(hooks.listeners("h2")) == 1

    def test_dispatch_sync_no_loop(self):
        hooks = HookSystem()
        result = hooks.dispatch_sync("h")
        assert result.should_cancel is False

    def test_dispatch_sync_with_running_loop(self):
        hooks = HookSystem()
        hooks.register("h", lambda: HookResult(payload={"ok": True}))

        async def inside_running_loop():
            return hooks.dispatch_sync("h")

        result = run(inside_running_loop())
        assert result.payload == {"ok": True}


# ------------------------------------------------------------------------ di


class TestContainer:
    def test_instances(self):
        container = Container()
        container.register_instance("config", PluginConfig())
        assert container.resolve("config") is container.resolve("config")
        assert container.has("config") is True
        assert "config" in container.keys()

    def test_singleton_and_transient(self):
        container = Container()
        container.register_singleton("s", lambda: {})
        container.register_transient("t", lambda: {})
        container.register_factory("f", lambda: {})
        container.register_factory("g", lambda: {}, singleton=False)
        assert container.resolve("s") is container.resolve("s")
        assert container.resolve("t") is not container.resolve("t")
        assert container.resolve("f") is container.resolve("f")
        assert container.resolve("g") is not container.resolve("g")

    def test_factory_overrides(self):
        container = Container()
        container.register_singleton("v", lambda x: x * 2)
        assert container.resolve("v", x=21) == 42

    def test_factory_type_error_retry(self):
        container = Container()
        container.register_singleton("v", lambda: 42)
        assert container.resolve("v", x=21) == 42

    def test_provides(self):
        container = Container()
        container.register_instance("a", 1)
        container.register_instance("b", 2)
        container.register_provides("service", "a")
        container.register_provides("service", "b")
        assert container.resolve_provides("service") == [1, 2]
        assert container.resolve_provides("none") == []

    def test_unknown_and_circular(self):
        container = Container()
        with pytest.raises(ContainerError):
            container.resolve("missing")
        container.register_singleton("a", lambda: container.resolve("b"))
        container.register_singleton("b", lambda: container.resolve("a"))
        with pytest.raises(ContainerError):
            container.resolve("a")

    def test_clear(self):
        container = Container()
        container.register_instance("a", 1)
        container.clear()
        assert container.keys() == []


# ----------------------------------------------------------- extension registry


class TestExtensionRegistry:
    def test_register_and_get(self):
        registry = ExtensionRegistry()
        extension = Extension(kind=ExtensionKind.TOOL, name="greet", handler=lambda: None, plugin="demo")
        registry.register(extension)
        assert registry.get(ExtensionKind.TOOL, "greet") is extension
        assert registry.get("tool", "greet") is extension
        assert registry.get_or_none("tool", "missing") is None

    def test_duplicate_raises(self):
        registry = ExtensionRegistry()
        registry.register(Extension(kind=ExtensionKind.TOOL, name="t", handler=lambda: None))
        with pytest.raises(ExtensionAlreadyRegisteredError):
            registry.register(Extension(kind=ExtensionKind.TOOL, name="t", handler=lambda: None))

    def test_missing_raises(self):
        registry = ExtensionRegistry()
        with pytest.raises(ExtensionNotFoundError):
            registry.get("tool", "nope")

    def test_list_and_count(self):
        registry = ExtensionRegistry()
        registry.register(Extension(kind=ExtensionKind.TOOL, name="t1", handler=1, plugin="a"))
        registry.register(Extension(kind=ExtensionKind.TOOL, name="t2", handler=2, plugin="a"))
        registry.register(Extension(kind=ExtensionKind.ROUTE, name="/x", handler=3, plugin="b"))
        assert len(registry.list()) == 3
        assert len(registry.list(ExtensionKind.TOOL)) == 2
        assert len(registry.list("route")) == 1
        assert registry.count() == 3
        assert registry.count_by_kind() == {"tool": 2, "route": 1}
        assert len(registry.list_by_plugin("a")) == 2

    def test_unregister(self):
        registry = ExtensionRegistry()
        registry.register(Extension(kind=ExtensionKind.TOOL, name="t", handler=1, plugin="a"))
        assert registry.unregister("tool", "missing") is False
        assert registry.unregister(ExtensionKind.TOOL, "t") is True
        assert registry.count() == 0

    def test_unregister_plugin(self):
        registry = ExtensionRegistry()
        registry.register(Extension(kind=ExtensionKind.TOOL, name="t", handler=1, plugin="a"))
        registry.register(Extension(kind=ExtensionKind.ROUTE, name="/x", handler=2, plugin="a"))
        registry.register(Extension(kind=ExtensionKind.ROUTE, name="/y", handler=3, plugin="b"))
        assert registry.unregister_plugin("a") == 2
        assert registry.count() == 1
        assert registry.list_by_plugin("a") == []


# ----------------------------------------------------------------------- sdk


class TestSDK:
    def make_sdk(self, registry=None, bus=None, hooks=None):
        return PluginSDK(
            "demo",
            registry or ExtensionRegistry(),
            bus or PluginEventBus(),
            hooks or HookSystem(),
            PluginLogger(),
        )

    def test_tool_route_cli(self):
        sdk = self.make_sdk()
        tool = sdk.register_tool("greet", lambda: None, schema={"type": "object"})
        route = sdk.register_route("/demo", lambda: None, methods=("GET", "POST"))
        cli = sdk.register_cli_command("demo-run", lambda: None, help_text="run it")
        assert tool.kind == ExtensionKind.TOOL
        assert tool.metadata["schema"] == {"type": "object"}
        assert route.metadata["methods"] == ["GET", "POST"]
        assert cli.metadata["help"] == "run it"
        assert sdk.unregister_tool("greet") is True
        assert sdk.unregister_route("/demo") is True
        assert sdk.unregister_cli_command("demo-run") is True
        assert sdk.unregister_tool("greet") is False

    def test_providers(self):
        sdk = self.make_sdk()
        mcp = sdk.register_mcp_provider("files", lambda: None, config={"dir": "/tmp"})
        llm = sdk.register_llm_provider("acme", lambda: None, models=["acme-1"])
        emb = sdk.register_embedding_model("emb-1", lambda: None, dimensions=768)
        assert mcp.metadata["config"] == {"dir": "/tmp"}
        assert llm.metadata["models"] == ["acme-1"]
        assert emb.metadata["dimensions"] == 768
        assert sdk.unregister_mcp_provider("files") is True
        assert sdk.unregister_llm_provider("acme") is True
        assert sdk.unregister_embedding_model("emb-1") is True

    def test_scheduler(self):
        sdk = self.make_sdk()
        sdk.register_scheduler("cleanup", SchedulerSpec(interval_seconds=60), lambda: None)
        sdk.register_scheduler("backup", {"interval_seconds": 300, "cron": "0 * * * *"}, lambda: None)
        schedulers = sdk.extensions(ExtensionKind.SCHEDULER)
        assert len(schedulers) == 2
        assert schedulers[0].metadata["spec"]["interval_seconds"] == 60
        assert schedulers[1].metadata["spec"]["cron"] == "0 * * * *"
        assert sdk.unregister_scheduler("cleanup") is True

    def test_event_listener(self):
        bus = PluginEventBus()
        sdk = self.make_sdk(bus=bus)
        seen: list[str] = []
        extension = sdk.register_event_listener("demo.ping", lambda **kw: seen.append(kw["v"]))
        assert extension.kind == ExtensionKind.EVENT_LISTENER
        assert bus.subscribers("demo.ping")
        bus.emit("demo.ping", v=1)
        assert seen == [1]
        sdk.unregister_event_listener("demo.ping")
        assert bus.subscribers("demo.ping") == []
        assert sdk.unregister_event_listener("demo.ping") is False

    def test_event_listener_with_handler(self):
        bus = PluginEventBus()
        sdk = self.make_sdk(bus=bus)

        def handler(**kw):
            return None

        other = lambda **kw: None
        sdk.register_event_listener("e", handler)
        sdk.register_event_listener("e", other)
        assert sdk.unregister_event_listener("e", handler) is True
        assert bus.subscribers("e") == [other]
        sdk.unregister_event_listener("e")
        assert bus.subscribers("e") == []

    def test_cleanup_unsubscribes(self):
        bus = PluginEventBus()
        sdk = self.make_sdk(bus=bus)
        sdk.register_event_listener("e", lambda **kw: None)
        sdk.cleanup()
        assert bus.subscribers("e") == []

    def test_queries(self):
        sdk = self.make_sdk()
        sdk.register_tool("t", lambda: None)
        extension = sdk.get_extension(ExtensionKind.TOOL, "t")
        assert extension.name == "t"
        assert len(sdk.extensions()) == 1
        assert len(sdk.extensions("tool")) == 1

    def test_plugin_no_context_raises(self):
        plugin = Plugin()
        with pytest.raises(RuntimeError):
            plugin.context

    def test_maybe_await_sync_and_async(self):
        from app.plugins.sdk import _maybe_await

        assert run(_maybe_await(lambda: 5)) == 5

        async def give():
            return 7

        assert run(_maybe_await(give)) == 7

    def test_duplicate_registration(self):
        sdk = self.make_sdk()
        sdk.register_tool("t", lambda: None)
        with pytest.raises(ExtensionAlreadyRegisteredError):
            sdk.register_tool("t", lambda: None)


# ---------------------------------------------------------------- lifecycle


class TestLifecycle:
    def test_states(self):
        lifecycle = PluginLifecycle()
        lifecycle.initialize("demo")
        assert lifecycle.state("demo") == PluginStatus.DRAFT
        assert lifecycle.state("unknown") == PluginStatus.DRAFT

    def test_transitions(self):
        lifecycle = PluginLifecycle()
        lifecycle.initialize("demo")
        assert lifecycle.can_transition("demo", PluginStatus.INSTALLING) is True
        assert lifecycle.transition("demo", PluginStatus.INSTALLING) == PluginStatus.INSTALLING
        assert lifecycle.transition("demo", PluginStatus.INSTALLED) == PluginStatus.INSTALLED
        assert lifecycle.transition("demo", PluginStatus.VERIFYING) == PluginStatus.VERIFYING
        assert lifecycle.transition("demo", PluginStatus.VERIFIED) == PluginStatus.VERIFIED
        assert lifecycle.transition("demo", PluginStatus.ENABLING) == PluginStatus.ENABLING
        assert lifecycle.transition("demo", PluginStatus.ENABLED) == PluginStatus.ENABLED
        assert lifecycle.is_enabled("demo") is True
        assert lifecycle.is_installed("demo") is True
        assert lifecycle.transition("demo", PluginStatus.DISABLED) == PluginStatus.DISABLED
        assert lifecycle.is_enabled("demo") is False
        assert lifecycle.transition("demo", PluginStatus.UPDATING) == PluginStatus.UPDATING
        assert lifecycle.transition("demo", PluginStatus.ROLLING_BACK) == PluginStatus.ROLLING_BACK
        assert lifecycle.transition("demo", PluginStatus.ROLLED_BACK) == PluginStatus.ROLLED_BACK
        assert lifecycle.is_installed("demo") is True
        assert lifecycle.transition("demo", PluginStatus.UNINSTALLING) == PluginStatus.UNINSTALLING
        assert lifecycle.transition("demo", PluginStatus.UNINSTALLED) == PluginStatus.UNINSTALLED
        assert lifecycle.is_installed("demo") is False

    def test_invalid_transition(self):
        lifecycle = PluginLifecycle()
        lifecycle.initialize("demo")
        lifecycle.transition("demo", PluginStatus.INSTALLING)
        with pytest.raises(PluginLifecycleError):
            lifecycle.transition("demo", PluginStatus.ENABLED)
        assert lifecycle.state("demo") == PluginStatus.INSTALLING

    def test_failed_recovery(self):
        lifecycle = PluginLifecycle()
        lifecycle.initialize("demo")
        lifecycle.transition("demo", PluginStatus.INSTALLING)
        lifecycle.transition("demo", PluginStatus.FAILED)
        assert lifecycle.can_transition("demo", PluginStatus.INSTALLING) is True
        assert lifecycle.can_transition("demo", PluginStatus.UNINSTALLING) is True

    def test_drop_and_states(self):
        lifecycle = PluginLifecycle()
        lifecycle.initialize("a")
        lifecycle.initialize("b")
        lifecycle.transition("b", PluginStatus.INSTALLING)
        assert lifecycle.states() == {"a": "draft", "b": "installing"}
        lifecycle.drop("a")
        assert lifecycle.states() == {"b": "installing"}


# ------------------------------------------------------------------- metrics


class TestMetrics:
    def test_record(self):
        metrics = PluginMetricsTracker()
        metrics.record("install", plugin="demo")
        metrics.record("install", plugin="demo")
        metrics.record("enable", plugin="demo")
        metrics.record("hook")
        assert metrics.counts() == {"install": 2, "enable": 1, "hook": 1}
        assert metrics.for_plugin("demo") == {"install": 2, "enable": 1}
        summary = metrics.summary()
        assert summary["total_events"] == 4
        assert summary["plugins"]["demo"]["install"] == 2

    def test_disabled(self):
        metrics = PluginMetricsTracker(PluginConfig(track_metrics=False))
        metrics.record("install", plugin="demo")
        assert metrics.summary()["total_events"] == 0


# ---------------------------------------------------------------- marketplace


class TestMarketplace:
    def make_entry(self, entry_id="e1", name="demo", version="1.0.0", **overrides):
        data = {
            "id": entry_id,
            "name": name,
            "version": version,
            "description": "demo plugin for testing",
            "author": "tester",
            "tags": ["ai", "tools"],
            "requires_router": ">=2.0.0",
            "plugin_code": make_code(),
        }
        data.update(overrides)
        return MarketplaceEntry(**data)

    def test_add_get_remove(self):
        marketplace = Marketplace()
        entry = self.make_entry()
        marketplace.add(entry)
        assert marketplace.get("e1") is entry
        assert marketplace.count() == 1
        with pytest.raises(PluginMarketplaceError):
            marketplace.get("missing")
        assert marketplace.remove("missing") is False
        assert marketplace.remove("e1") is True
        assert marketplace.count() == 0

    def test_search(self):
        marketplace = Marketplace()
        marketplace.add(self.make_entry("e1", name="alpha", tags=["ai"]))
        marketplace.add(self.make_entry("e2", name="beta", tags=["tools"], description="nothing here"))
        assert len(marketplace.search()) == 2
        assert [e.id for e in marketplace.search(query="alpha")] == ["e1"]
        assert [e.id for e in marketplace.search(query="testing")] == ["e1"]
        assert [e.id for e in marketplace.search(query="tester")] == ["e1", "e2"]
        assert [e.id for e in marketplace.search(tag="tools")] == ["e2"]
        assert len(marketplace.search(limit=1)) == 1
        assert marketplace.search(query="zzz") == []
        assert [e.id for e in marketplace.search_by_name("alpha")] == ["e1"]

    def test_latest_and_updates(self):
        marketplace = Marketplace()
        marketplace.add(self.make_entry("e1", name="demo", version="1.0.0"))
        marketplace.add(self.make_entry("e2", name="demo", version="2.0.0"))
        assert marketplace.latest("demo").id == "e2"
        assert marketplace.latest("missing") is None
        assert marketplace.update_available("demo", "1.0.0") == "2.0.0"
        assert marketplace.update_available("demo", "2.0.0") is None
        assert marketplace.update_available("demo", "3.0.0") is None
        assert marketplace.update_available("missing", "1.0.0") is None

    def test_compatible_with(self):
        marketplace = Marketplace()
        marketplace.add(self.make_entry("e1", name="demo"))
        marketplace.add(self.make_entry("e2", name="old", requires_router=">=9.0.0"))
        compatible = marketplace.compatible_with("2.0.0")
        assert [entry.id for entry in compatible] == ["e1"]
        assert [entry.id for entry in marketplace.compatible_with("2.0.0", entry_id="e1")] == ["e1"]

    def test_ratings(self):
        marketplace = Marketplace()
        marketplace.add(self.make_entry())
        with pytest.raises(PluginRatingError):
            marketplace.rate("e1", "u1", 0)
        with pytest.raises(PluginRatingError):
            marketplace.rate("e1", "u1", 6)
        marketplace.rate("e1", "u1", 4, "good")
        marketplace.rate("e1", "u2", 2)
        assert marketplace.average("e1") == 3.0
        assert len(marketplace.ratings("e1")) == 2
        marketplace.rate("e1", "u1", 5, "updated")
        assert marketplace.average("e1") == 3.5
        assert marketplace.get("e1").average_rating == 3.5
        assert marketplace.get("e1").rating_count == 2

    def test_install_entry(self, tmp_path):
        marketplace = Marketplace(make_config(tmp_path))
        marketplace.add(self.make_entry())
        result = marketplace.install_entry("e1", str(tmp_path / "target"))
        assert result["plugin"] == "demo"
        assert result["signature_verified"] is False
        plugin_dir = tmp_path / "target" / "demo"
        assert (plugin_dir / "manifest.yaml").exists()
        assert (plugin_dir / "plugin.py").exists()
        assert (plugin_dir / "metadata.json").exists()
        assert marketplace.get("e1").downloads == 1
        with pytest.raises(PluginMarketplaceError):
            marketplace.install_entry("e1", str(tmp_path / "target"))

    def test_install_entry_signed(self, tmp_path):
        config = make_config(tmp_path, signature_secret="k")
        marketplace = Marketplace(config)
        entry = self.make_entry(version="2.0.0")
        manifest = {
            "name": entry.name,
            "version": entry.version,
            "entry": entry.entry,
            "requires_router": entry.requires_router,
            "tags": entry.tags,
        }
        entry.signature = sign_payload(manifest, "k").digest
        marketplace.add(entry)
        result = marketplace.install_entry("e1", str(tmp_path / "target"))
        assert result["signature_verified"] is True

    def test_install_entry_bad_signature(self, tmp_path):
        marketplace = Marketplace(make_config(tmp_path, signature_secret="k"))
        marketplace.add(self.make_entry(signature="forged"))
        with pytest.raises(PluginSignatureError):
            marketplace.install_entry("e1", str(tmp_path / "target"))

    def test_install_entry_requires_signature(self, tmp_path):
        marketplace = Marketplace(make_config(tmp_path, require_signatures=True))
        marketplace.add(self.make_entry())
        with pytest.raises(PluginSignatureError):
            marketplace.install_entry("e1", str(tmp_path / "target"))

    def test_install_entry_invalid(self, tmp_path):
        marketplace = Marketplace()
        marketplace.add(self.make_entry(name="Bad Name", version="1.0"))
        with pytest.raises(PluginMarketplaceError):
            marketplace.install_entry("e1", str(tmp_path / "target"))

    def test_install_entry_incompatible(self, tmp_path):
        marketplace = Marketplace()
        marketplace.add(self.make_entry(requires_router=">=9.0.0"))
        with pytest.raises(PluginCompatibilityError):
            marketplace.install_entry("e1", str(tmp_path / "target"))

    def test_install_entry_skip_compatibility(self, tmp_path):
        marketplace = Marketplace()
        marketplace.add(self.make_entry(requires_router=">=9.0.0"))
        result = marketplace.install_entry("e1", str(tmp_path / "target"), verify_compatibility=False)
        assert result["plugin"] == "demo"


# ------------------------------------------------------------------ manager


class TestManager:
    async def install_demo(self, manager, name="demo", version="1.0.0", **spec_overrides):
        code = make_code(tools=["greet"], hooks={"demo.ping": "lambda **kw: None"}, version=version)
        spec = make_spec(name=name, version=version, plugin_code=code)
        spec.update(spec_overrides)
        return await manager.install(spec)

    def test_install_full_lifecycle(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        info = run(self.install_demo(manager))
        assert info.status == PluginStatus.ENABLED
        assert info.version == "1.0.0"
        assert manager.is_enabled("demo") is True
        assert "tool" in info.to_dict()["extensions"]
        assert manager.extensions.get("tool", "greet").plugin == "demo"
        assert manager.permissions.check("demo", "filesystem", "read") is True
        assert manager.permissions.check("demo", "network", "connect") is False
        files = Path(manager.config.plugins_dir) / "demo"
        assert (files / "manifest.yaml").exists()
        assert (files / "plugin.py").exists()
        assert manager.metrics.counts()["install"] == 1
        assert manager.metrics.counts()["enable"] == 1

    def test_install_disabled_auto_enable(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        info = run(self.install_demo(manager))
        assert info.status == PluginStatus.VERIFIED
        assert manager.is_enabled("demo") is False
        assert manager.list(status="verified")[0].name == "demo"
        assert manager.list(status=PluginStatus.ENABLED) == []

    def test_install_requires_source(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginInstallError):
            run(manager.install())
        with pytest.raises(PluginInstallError):
            run(manager.install(make_spec(plugin_code="x"), source_dir="/tmp/nope"))

    def test_install_duplicate(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        with pytest.raises(PluginAlreadyInstalledError):
            run(self.install_demo(manager))

    def test_install_invalid_spec(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginInvalidError):
            run(manager.install(make_spec(version="nope", plugin_code=make_code())))
        with pytest.raises(PluginInstallError):
            run(manager.install(make_spec()))

    def test_install_incompatible(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginCompatibilityError):
            run(manager.install(make_spec(requires_router=">=99.0.0", plugin_code=make_code())))

    def test_install_signature_required(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, require_signatures=True))
        with pytest.raises(PluginSignatureError):
            run(self.install_demo(manager))
        signed = make_spec(plugin_code=make_code(), signature="forged")
        with pytest.raises(PluginSignatureError):
            run(manager.install(signed))

    def test_install_signed_ok(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, require_signatures=True))
        spec = make_spec(plugin_code=make_code())
        spec["signature"] = sign_payload(spec, manager.config.signature_secret).digest
        info = run(manager.install(spec))
        assert info.status == PluginStatus.ENABLED

    def test_install_source_dir(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        (source / "plugin.py").write_text(make_code())
        (source / "manifest.yaml").write_text("name: demo\nversion: 1.0.0\nentry: create_plugin\n")
        manager = create_plugin_manager(make_config(tmp_path))
        info = run(manager.install(source_dir=str(source)))
        assert info.status == PluginStatus.ENABLED
        assert (Path(manager.config.plugins_dir) / "demo" / "manifest.yaml").exists()

    def test_install_source_dir_missing_manifest(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginInstallError):
            run(manager.install(source_dir=str(source)))

    def test_install_source_dir_already_installed(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        (source / "plugin.py").write_text(make_code())
        (source / "manifest.yaml").write_text("name: demo\nversion: 1.0.0\nentry: create_plugin\n")
        manager = create_plugin_manager(make_config(tmp_path))
        run(manager.install(source_dir=str(source)))
        with pytest.raises(PluginAlreadyInstalledError):
            run(manager.install(source_dir=str(source)))

    def test_install_source_dir_invalid_manifest(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        (source / "plugin.py").write_text(make_code())
        (source / "manifest.yaml").write_text("- just\n- a\n- list\n")
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginInstallError):
            run(manager.install(source_dir=str(source)))

    def test_install_source_dir_missing_plugin_file(self, tmp_path):
        source = tmp_path / "src"
        source.mkdir()
        (source / "manifest.yaml").write_text("name: demo\nversion: 1.0.0\nentry: create_plugin\n")
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginInstallError):
            run(manager.install(source_dir=str(source)))

    def test_install_marketplace_entry(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        manager.marketplace.add(MarketplaceEntry(id="e1", name="demo", version="1.0.0", plugin_code=make_code()))
        info = run(manager.install(entry_id="e1"))
        assert info.status == PluginStatus.ENABLED
        assert manager.marketplace.get("e1").downloads == 1

    def test_install_marketplace_missing(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginMarketplaceError):
            run(manager.install(entry_id="nope"))

    def test_install_bad_code(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginInstallError):
            run(manager.install(make_spec(plugin_code="def create_plugin(sdk):\n    raise RuntimeError('bad')\n")))
        with pytest.raises(PluginInstallError):
            run(manager.install(make_spec(plugin_code="this is not python ###")))

    def test_install_plugin_subclass(self, tmp_path):
        code = "from app.plugins import Plugin\nclass MyPlugin(Plugin):\n    name = 'demo'\n    version = '1.0.0'\n"
        manager = create_plugin_manager(make_config(tmp_path))
        info = run(manager.install(make_spec(plugin_code=code)))
        assert info.status == PluginStatus.ENABLED

    def test_install_max_plugins(self, tmp_path):
        config = make_config(tmp_path, max_plugins=1)
        manager = create_plugin_manager(config)
        run(manager.install(make_spec(plugin_code=make_code())))
        with pytest.raises(PluginInstallError):
            run(manager.install(make_spec(name="second", plugin_code=make_code())))

    def test_install_no_factory_or_subclass(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginInstallError):
            run(manager.install(make_spec(plugin_code="x = 1\n")))

    def test_upgrade_cleans_stale_backup(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        Path(manager.config.plugins_dir, "demo.bak").mkdir()
        info = run(manager.upgrade("demo", make_spec(version="1.1.0", plugin_code=make_code(version="1.1.0"))))
        assert info.version == "1.1.0"
        assert not Path(manager.config.plugins_dir, "demo.bak").exists()

    def test_install_hook_failure(self, tmp_path):
        code = "from app.plugins import Plugin\n\ndef create_plugin(sdk):\n    p = Plugin()\n    p.name = 'demo'\n    async def on_install(ctx):\n        raise RuntimeError('install failed')\n    p.on_install = on_install\n    return p\n"
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(RuntimeError):
            run(manager.install(make_spec(plugin_code=code)))
        assert manager.lifecycle.state("demo") == PluginStatus.FAILED
        assert "plugin.failed" in [e["event"] for e in manager.event_bus.get_history()]

    def test_enable_disable(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(self.install_demo(manager))
        run(manager.disable("demo"))
        assert manager.status("demo") == PluginStatus.DISABLED
        assert manager.is_enabled("demo") is False
        run(manager.disable("demo"))
        assert manager.status("demo") == PluginStatus.DISABLED
        run(manager.enable("demo"))
        assert manager.status("demo") == PluginStatus.ENABLED
        run(manager.enable("demo"))
        assert manager.status("demo") == PluginStatus.ENABLED
        assert [e["event"] for e in manager.event_bus.get_history() if e["event"] in (PLUGIN_ENABLED, PLUGIN_DISABLED)] == [PLUGIN_ENABLED]

    def test_enable_unknown(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginNotFoundError):
            run(manager.enable("nope"))
        with pytest.raises(PluginNotFoundError):
            run(manager.disable("nope"))
        with pytest.raises(PluginNotFoundError):
            manager.get("nope")
        with pytest.raises(PluginNotFoundError):
            manager.is_enabled("nope")

    def test_reload(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        info = run(manager.reload("demo"))
        assert info.status == PluginStatus.ENABLED
        assert manager.extensions.get("tool", "greet").plugin == "demo"
        assert PLUGIN_RELOADED in [e["event"] for e in manager.event_bus.get_history()]

    def test_reload_disabled_stays_disabled(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(self.install_demo(manager))
        info = run(manager.reload("demo"))
        assert info.status == PluginStatus.VERIFIED

    def test_reload_failed_state(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        manager.lifecycle.drop("demo")
        manager.lifecycle.initialize("demo", PluginStatus.FAILED)
        with pytest.raises(PluginInstallError):
            run(manager.reload("demo"))

    def test_reload_unknown(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        with pytest.raises(PluginNotFoundError):
            run(manager.reload("nope"))

    def test_upgrade(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        upgraded_code = make_code(tools=["greet", "wave"], version="1.1.0")
        info = run(manager.upgrade("demo", make_spec(version="1.1.0", plugin_code=upgraded_code)))
        assert info.version == "1.1.0"
        assert info.status == PluginStatus.ENABLED
        assert manager.extensions.get("tool", "wave").plugin == "demo"
        assert manager.spec("demo").version == "1.1.0"
        assert PLUGIN_UPGRADED in [e["event"] for e in manager.event_bus.get_history()]

    def test_upgrade_disabled_plugin(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(self.install_demo(manager))
        info = run(manager.upgrade("demo", make_spec(version="1.1.0", plugin_code=make_code(version="1.1.0"))))
        assert info.status == PluginStatus.DISABLED
        assert info.version == "1.1.0"

    def test_upgrade_same_version(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        with pytest.raises(PluginUpgradeError):
            run(manager.upgrade("demo", make_spec(version="1.0.0", plugin_code=make_code())))
        with pytest.raises(PluginUpgradeError):
            run(manager.upgrade("demo", make_spec(version="0.9.0", plugin_code=make_code())))

    def test_upgrade_invalid(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        with pytest.raises(PluginInvalidError):
            run(manager.upgrade("demo", make_spec(version="2.0.0")))
        with pytest.raises(PluginCompatibilityError):
            run(manager.upgrade("demo", make_spec(version="2.0.0", requires_router=">=99.0.0", plugin_code=make_code())))

    def test_upgrade_rollback(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        bad_code = "from app.plugins import Plugin\ndef create_plugin(sdk):\n    raise RuntimeError('upgrade broke')\n"
        with pytest.raises(PluginRollbackError):
            run(manager.upgrade("demo", make_spec(version="2.0.0", plugin_code=bad_code)))
        assert manager.spec("demo").version == "1.0.0"
        assert manager.status("demo") == PluginStatus.ROLLED_BACK
        assert manager.extensions.get("tool", "greet").plugin == "demo"
        assert manager.metrics.counts()["rollback"] == 1
        assert (Path(manager.config.plugins_dir) / "demo" / "plugin.py").exists()

    def test_upgrade_hook_failure_rolls_back(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        code = (
            "from app.plugins import Plugin\n"
            "def create_plugin(sdk):\n"
            "    p = Plugin()\n"
            "    p.name = 'demo'\n"
            "    p.version = '2.0.0'\n"
            "    async def on_upgrade(ctx, old):\n"
            "        raise RuntimeError('no')\n"
            "    p.on_upgrade = on_upgrade\n"
            "    return p\n"
        )
        with pytest.raises(PluginRollbackError):
            run(manager.upgrade("demo", make_spec(version="2.0.0", plugin_code=code)))
        assert manager.spec("demo").version == "1.0.0"

    def test_upgrade_rollback_restore_failure(self, tmp_path, monkeypatch):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        bad_code = "from app.plugins import Plugin\ndef create_plugin(sdk):\n    raise RuntimeError('upgrade broke')\n"
        import app.plugins.manager as manager_module

        real_copytree = manager_module.shutil.copytree

        def selective_copytree(src, *args, **kwargs):
            if str(src).endswith(".bak"):
                raise OSError("restore failed")
            return real_copytree(src, *args, **kwargs)

        monkeypatch.setattr(manager_module.shutil, "copytree", selective_copytree)
        with pytest.raises(PluginRollbackError):
            run(manager.upgrade("demo", make_spec(version="2.0.0", plugin_code=bad_code)))
        assert manager.lifecycle.state("demo") == PluginStatus.FAILED

    def test_uninstall(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        plugin_dir = Path(manager.config.plugins_dir) / "demo"
        run(manager.uninstall("demo"))
        assert manager.count() == 0
        assert not plugin_dir.exists()
        assert manager.extensions.count() == 0
        assert manager.permissions.permissions("demo") == {}
        assert PLUGIN_UNINSTALLED in [e["event"] for e in manager.event_bus.get_history()]
        with pytest.raises(PluginNotFoundError):
            manager.get("demo")

    def test_uninstall_hook_failure(self, tmp_path):
        code = (
            "from app.plugins import Plugin\n"
            "def create_plugin(sdk):\n"
            "    p = Plugin()\n"
            "    p.name = 'demo'\n"
            "    async def on_uninstall(ctx):\n"
            "        raise RuntimeError('cannot leave')\n"
            "    p.on_uninstall = on_uninstall\n"
            "    return p\n"
        )
        manager = create_plugin_manager(make_config(tmp_path))
        run(manager.install(make_spec(plugin_code=code)))
        with pytest.raises(PluginUninstallError):
            run(manager.uninstall("demo"))
        assert manager.lifecycle.state("demo") == PluginStatus.FAILED

    def test_list_and_queries(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(manager.install(make_spec(name="alpha", plugin_code=make_code(name="alpha"))))
        run(manager.install(make_spec(name="beta", version="2.0.0", plugin_code=make_code(version="2.0.0", name="beta"))))
        run(manager.enable("beta"))
        assert [info.name for info in manager.list()] == ["alpha", "beta"]
        assert [info.name for info in manager.list(status="verified")] == ["alpha"]
        assert [info.name for info in manager.list(status=PluginStatus.ENABLED)] == ["beta"]
        assert manager.names() == ["alpha", "beta"]
        assert manager.count() == 2
        assert manager.status("beta") == PluginStatus.ENABLED
        assert manager.is_enabled("beta") is True
        assert manager.plugin("beta").name == "beta"
        assert manager.spec("beta").version == "2.0.0"
        assert manager.info("beta").status == PluginStatus.ENABLED
        assert manager.get("beta").name == "beta"

    def test_emit_event_sync(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        seen: list[dict] = []
        manager.event_bus.subscribe("custom.event", lambda **kw: seen.append(kw))
        manager.emit_event("custom.event", v=3)
        assert seen == [{"v": 3}]

    def test_dispatch_hook_only_enabled(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        seen: list[str] = []

        async def listen(**kw):
            seen.append(kw["v"])

        code = "from app.plugins import Plugin\n"
        code += "def create_plugin(sdk):\n"
        code += "    def listen(**kw):\n"
        code += "        pass\n"
        code += "    p = Plugin()\n"
        code += "    p.name = 'demo'\n"
        code += "    sdk.register_event_listener('demo.ping', listen)\n"
        code += "    return p\n"
        manager.register_hook("demo.ping", lambda **kw: seen.append("manager-listen"))
        run(manager.install(make_spec(plugin_code=code)))
        result = run(manager.dispatch_hook("demo.ping", v=7))
        assert seen == ["manager-listen"]
        assert result.should_cancel is False
        seen.clear()
        run(manager.enable("demo"))
        run(manager.dispatch_hook("demo.ping", v=8))
        assert seen == ["manager-listen"]

    def test_dispatch_hook_sync(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        seen: list[str] = []
        manager.register_hook("pre", lambda: seen.append("x"), plugin="p1")
        manager.dispatch_hook_sync("pre")
        assert seen == ["x"]
        result = run(manager.dispatch_hook("pre", plugins=set()))
        assert result.should_cancel is False

    def test_hook_cancellation(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        manager.register_hook("pre", lambda: HookResult(should_cancel=True, cancel_reason="blocked"))
        result = run(manager.dispatch_hook("pre"))
        assert result.should_cancel is True
        assert result.cancel_reason == "blocked"

    def test_events(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        seen: list[dict] = []
        manager.event_bus.subscribe("custom.event", lambda **kw: seen.append(kw))
        run(manager.emit_event_async("custom.event", v=1))
        assert seen == [{"v": 1}]
        run(manager.emit_event_async("custom.event", v=2, plugin="demo"))
        assert seen[-1] == {"v": 2, "plugin": "demo"}

    def test_register_hook_plugin(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        run(self.install_demo(manager))
        plugin = manager.plugin("demo")
        manager.register_hook_plugin(plugin, "mine", lambda: None)
        assert manager.hooks.listeners("mine")[0][0] == "demo"

    def test_summary(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(self.install_demo(manager))
        summary = manager.summary()
        assert summary["total"] == 1
        assert summary["enabled"] == 0
        assert summary["by_status"] == {"verified": 1}
        assert summary["extensions"]["tool"] == 1
        assert summary["marketplace_entries"] == 0
        assert "metrics" in summary
        assert "permissions" in summary

    def test_admin_plugins_module_integration(self, tmp_path):
        from app.admin import AdminAPI, PluginsModule

        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(self.install_demo(manager))
        run(manager.enable("demo"))
        api = AdminAPI(plugins=PluginsModule(source=PluginManagerSource(manager)))
        plugins = api.module("plugins").plugins()
        assert [plugin["name"] for plugin in plugins] == ["demo"]
        assert plugins[0]["enabled"] is True
        assert api.module("plugins").stats() == {"total_plugins": 1, "enabled": 1}
        run(manager.disable("demo"))
        assert api.module("plugins").plugins()[0]["enabled"] is False

    def test_plugin_context_in_hooks(self, tmp_path):
        code = (
            "from app.plugins import Plugin\n"
            "def create_plugin(sdk):\n"
            "    p = Plugin()\n"
            "    p.name = 'demo'\n"
            "    async def on_enable(ctx):\n"
            "        assert ctx.check_permission('filesystem', 'read') is True\n"
            "        assert ctx.check_permission('network') is False\n"
            "        ctx.require_permission('filesystem', 'read')\n"
            "        ctx.log('enabled', detail='yes')\n"
            "        ctx.emit('demo.enabled')\n"
            "    p.on_enable = on_enable\n"
            "    return p\n"
        )
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(manager.install(make_spec(plugin_code=code)))
        run(manager.enable("demo"))
        assert any(
            e["event"] == "plugin_enabled" and e["data"].get("plugin") == "demo" for e in manager.logger.events
        )

    def test_plugin_context_require_permission_raises(self, tmp_path):
        code = (
            "from app.plugins import Plugin\n"
            "def create_plugin(sdk):\n"
            "    p = Plugin()\n"
            "    p.name = 'demo'\n"
            "    async def on_enable(ctx):\n"
            "        ctx.require_permission('network', 'connect')\n"
            "    p.on_enable = on_enable\n"
            "    return p\n"
        )
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(manager.install(make_spec(plugin_code=code)))
        with pytest.raises(PluginPermissionDeniedError):
            run(manager.enable("demo"))
        assert manager.lifecycle.state("demo") == PluginStatus.FAILED

    def test_create_plugin_manager_di(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path), extra="value")
        assert manager.container.resolve("plugin_manager") is manager
        assert manager.container.resolve("plugin_config") is manager.config
        assert manager.container.resolve("plugin_sandbox") is manager.sandbox
        assert manager.container.resolve("plugin_permissions") is manager.permissions
        assert manager.container.resolve("plugin_event_bus") is manager.event_bus
        assert manager.container.resolve("plugin_hooks") is manager.hooks
        assert manager.container.resolve("plugin_extensions") is manager.extensions
        assert manager.container.resolve("plugin_metrics") is manager.metrics
        assert manager.container.resolve("plugin_marketplace") is manager.marketplace
        assert manager.container.resolve("plugin_lifecycle") is manager.lifecycle
        assert manager.container.resolve("plugin_validator") is not None
        assert manager.container.resolve("plugin_compatibility") is not None
        assert manager.container.resolve("extra") == "value"

    def test_manager_source_adapter(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path, auto_enable=False))
        run(self.install_demo(manager))
        source = PluginManagerSource(manager)
        assert [info.name for info in source.get_enabled()] == []
        assert source.disabled() == ["demo"]
        run(manager.enable("demo"))
        assert [info.name for info in source.get_enabled()] == ["demo"]
        assert source.disabled() == []

    def test_manager_services(self, tmp_path):
        manager = create_plugin_manager(make_config(tmp_path))
        assert manager.sandbox.config is manager.config
        assert manager.hooks is not None
        assert manager.extensions is not None
        assert manager.event_bus is not None
        assert manager.lifecycle is not None
        assert manager.logger is not None
        assert manager.metrics is not None
        assert manager.marketplace is not None

    def test_install_with_manual_manager(self, tmp_path):
        config = make_config(tmp_path)
        manager = PluginManager(config=config)
        info = run(manager.install(make_spec(plugin_code=make_code())))
        assert info.status == PluginStatus.ENABLED
