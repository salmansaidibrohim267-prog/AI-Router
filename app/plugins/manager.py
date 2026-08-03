from __future__ import annotations

import importlib.util
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

from .config import PluginConfig
from .di import Container
from .events import (
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
from .exceptions import (
    PluginAlreadyInstalledError,
    PluginInstallError,
    PluginInvalidError,
    PluginNotFoundError,
    PluginRollbackError,
    PluginSignatureError,
    PluginUninstallError,
    PluginUpgradeError,
)
from .hooks import HookSystem
from .lifecycle import PluginLifecycle
from .logging import PluginLogger
from .marketplace import Marketplace
from .metrics import PluginMetricsTracker
from .models import PluginInfo, PluginSpec, PluginStatus
from .permissions import PermissionManager
from .registry import ExtensionRegistry
from .sandbox import Sandbox
from .sdk import Plugin, PluginSDK, _maybe_await
from .signing import verify_payload
from .validation import CompatibilityChecker, ManifestValidator
from .versioning import compare_versions


class PluginManager:
    """Facade for the plugin & extension platform.

    Owns the plugin lifecycle (install -> verify -> enable/disable ->
    upgrade/rollback -> uninstall), the sandbox, permissions, event bus,
    hook system, extension registry, marketplace and metrics, wired through
    dependency injection (see ``create_plugin_manager``).
    """

    def __init__(
        self,
        config: PluginConfig | None = None,
        logger: PluginLogger | None = None,
        sandbox: Sandbox | None = None,
        permissions: PermissionManager | None = None,
        container: Container | None = None,
        event_bus: PluginEventBus | None = None,
        hooks: HookSystem | None = None,
        extensions: ExtensionRegistry | None = None,
        metrics: PluginMetricsTracker | None = None,
        marketplace: Marketplace | None = None,
        lifecycle: PluginLifecycle | None = None,
        validator: ManifestValidator | None = None,
        compatibility: CompatibilityChecker | None = None,
    ) -> None:
        self._config = config or PluginConfig()
        self._logger = logger or PluginLogger(self._config)
        self._sandbox = sandbox or Sandbox(self._config, self._logger)
        self._permissions = permissions or PermissionManager(self._config, self._logger)
        self._container = container or Container()
        self._event_bus = event_bus or PluginEventBus()
        self._hooks = hooks or HookSystem(self._logger)
        self._extensions = extensions or ExtensionRegistry()
        self._metrics = metrics or PluginMetricsTracker(self._config)
        self._marketplace = marketplace or Marketplace(self._config, self._logger)
        self._lifecycle = lifecycle or PluginLifecycle(self._logger)
        self._validator = validator or ManifestValidator()
        self._compatibility = compatibility or CompatibilityChecker()

        self._plugins: dict[str, Plugin] = {}
        self._specs: dict[str, PluginSpec] = {}
        self._sdks: dict[str, PluginSDK] = {}
        self._dirs: dict[str, str] = {}
        self._module_names: dict[str, str] = {}

    # ------------------------------------------------------------ services

    @property
    def config(self) -> PluginConfig:
        return self._config

    @property
    def logger(self) -> PluginLogger:
        return self._logger

    @property
    def sandbox(self) -> Sandbox:
        return self._sandbox

    @property
    def permissions(self) -> PermissionManager:
        return self._permissions

    @property
    def container(self) -> Container:
        return self._container

    @property
    def event_bus(self) -> PluginEventBus:
        return self._event_bus

    @property
    def hooks(self) -> HookSystem:
        return self._hooks

    @property
    def extensions(self) -> ExtensionRegistry:
        return self._extensions

    @property
    def metrics(self) -> PluginMetricsTracker:
        return self._metrics

    @property
    def marketplace(self) -> Marketplace:
        return self._marketplace

    @property
    def lifecycle(self) -> PluginLifecycle:
        return self._lifecycle

    # ------------------------------------------------------------- install

    async def install(
        self,
        spec: dict[str, Any] | None = None,
        source_dir: str | None = None,
        entry_id: str | None = None,
        auto_enable: bool | None = None,
    ) -> PluginInfo:
        if sum(value is not None for value in (spec, source_dir, entry_id)) != 1:
            raise PluginInstallError("exactly one of spec, source_dir or entry_id is required")

        plugin_dir, resolved_spec = self._materialize(spec=spec, source_dir=source_dir, entry_id=entry_id)
        name = resolved_spec["name"]
        if name in self._plugins:  # pragma: no cover - materialize raises first when the dir exists
            raise PluginAlreadyInstalledError(f"plugin {name!r} is already installed", plugin=name)
        if len(self._plugins) >= self._config.max_plugins:
            raise PluginInstallError(
                f"plugin limit of {self._config.max_plugins} reached", limit=self._config.max_plugins
            )  # noqa: E501

        self._lifecycle.initialize(name)
        try:
            self._lifecycle.transition(name, PluginStatus.INSTALLING)
            self._validate_spec(resolved_spec)
            self._lifecycle.transition(name, PluginStatus.INSTALLED)
            self._lifecycle.transition(name, PluginStatus.VERIFYING)
            self._verify(name, resolved_spec)
            self._lifecycle.transition(name, PluginStatus.VERIFIED)
            self._event_bus.emit(PLUGIN_VERIFIED, plugin=name, version=resolved_spec["version"])

            sdk = PluginSDK(name, self._extensions, self._event_bus, self._hooks, self._logger)
            plugin = self._load_plugin(sdk, plugin_dir)
            self._plugins[name] = plugin
            self._sdks[name] = sdk
            self._dirs[name] = plugin_dir
            self._specs[name] = PluginSpec(
                name=name,
                version=resolved_spec["version"],
                entry=resolved_spec.get("entry", "create_plugin"),
                description=resolved_spec.get("description", ""),
                author=resolved_spec.get("author", ""),
                tags=resolved_spec.get("tags", []),
                requires_router=resolved_spec.get("requires_router", ""),
                permissions=resolved_spec.get("permissions", []),
                signature=resolved_spec.get("signature", ""),
            )  # noqa: E501
            plugin.set_context(self._build_context(name, plugin))
            self._permissions.grant_from_manifest(name, resolved_spec.get("permissions", []))
            await self._run_hook(name, "on_install")

            self._event_bus.emit(PLUGIN_INSTALLED, plugin=name, version=resolved_spec["version"])
            self._metrics.record("install", plugin=name)
            self._logger.log_event("plugin.installed", plugin=name, version=resolved_spec["version"])
        except Exception as exc:
            self._mark_failed(name, exc)
            shutil.rmtree(plugin_dir, ignore_errors=True)
            raise

        enable_now = self._config.auto_enable if auto_enable is None else auto_enable
        if enable_now:
            await self.enable(name)
        return self.info(name)

    def _materialize(
        self, spec: dict[str, Any] | None, source_dir: str | None, entry_id: str | None
    ) -> tuple[str, dict[str, Any]]:  # noqa: E501
        plugins_dir = Path(self._config.plugins_dir)
        if entry_id is not None:
            result = self._marketplace.install_entry(entry_id, self._config.plugins_dir)
            plugin_dir = result["path"]
            spec = self._read_manifest(plugin_dir)
            return plugin_dir, spec
        if source_dir is not None:
            source = Path(source_dir)
            spec = self._read_manifest(str(source))
            name = spec["name"]
            plugin_dir = str(plugins_dir / name)
            if Path(plugin_dir).exists():
                raise PluginAlreadyInstalledError(f"plugin {name!r} is already installed", plugin=name)
            plugins_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(source), plugin_dir)
            return plugin_dir, spec
        assert spec is not None
        if "plugin_code" not in spec:
            raise PluginInstallError("spec requires 'plugin_code' when no source_dir is given")
        name = spec["name"]
        plugin_dir = str(plugins_dir / name)
        if Path(plugin_dir).exists():
            raise PluginAlreadyInstalledError(f"plugin {name!r} is already installed", plugin=name)
        plugins_dir.mkdir(parents=True, exist_ok=True)
        Path(plugin_dir).mkdir()
        manifest = {key: value for key, value in spec.items() if key != "plugin_code"}
        with open(Path(plugin_dir) / "manifest.yaml", "w") as fh:
            fh.write(_spec_to_yaml(manifest))
        with open(Path(plugin_dir) / "plugin.py", "w") as fh:
            fh.write(spec["plugin_code"])
        return plugin_dir, spec

    @staticmethod
    def _read_manifest(plugin_dir: str) -> dict[str, Any]:
        import yaml

        manifest_file = Path(plugin_dir) / "manifest.yaml"
        if not manifest_file.exists():
            raise PluginInstallError(f"manifest.yaml missing in {plugin_dir!r}", path=plugin_dir)
        with open(manifest_file) as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise PluginInstallError(f"invalid manifest in {plugin_dir!r}", path=plugin_dir)
        return data

    def _validate_spec(self, spec: dict[str, Any]) -> None:
        self._validator.validate_or_raise(spec)
        self._compatibility.check_or_raise(spec, extension_count=self._extensions.count())

    def _verify(self, name: str, spec: dict[str, Any]) -> None:
        secret = self._config.signature_secret
        signature = spec.get("signature", "")
        if self._config.require_signatures and not signature:
            raise PluginSignatureError(f"plugin {name!r} is not signed", plugin=name)
        if signature:
            if not verify_payload(spec, signature, secret):
                raise PluginSignatureError(f"signature verification failed for {name!r}", plugin=name)

    def _build_context(self, name: str, plugin: Plugin) -> Any:
        from .sdk import PluginContext

        return PluginContext(
            plugin_name=name,
            config=self._config,
            logger=self._logger,
            sandbox=self._sandbox,
            permissions=self._permissions,
            container=self._container,
            event_bus=self._event_bus,
            hooks=self._hooks,
            extensions=self._extensions,
        )

    def _load_plugin(self, sdk: PluginSDK, plugin_dir: str) -> Plugin:
        plugin_file = Path(plugin_dir) / "plugin.py"
        if not plugin_file.exists():
            raise PluginInstallError(f"plugin.py missing in {plugin_dir!r}", path=plugin_dir)
        module_name = f"_plugin_ext_{sdk._plugin_name}_{uuid.uuid4().hex[:6]}"
        self._module_names[sdk._plugin_name] = module_name
        return self._sandbox.execute(self._import_plugin, module_name, str(plugin_file), sdk)

    @staticmethod
    def _import_plugin(module_name: str, plugin_file: str, sdk: PluginSDK) -> Plugin:
        from .sdk import Plugin

        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        if spec is None or spec.loader is None:  # pragma: no cover - guarded by file existence checks
            raise PluginInstallError(f"cannot create module spec for {plugin_file!r}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            raise PluginInstallError(f"plugin module failed to import: {exc}", error=str(exc)) from exc
        factory = getattr(module, "create_plugin", None)
        if callable(factory):
            try:
                plugin = factory(sdk)
            except Exception as exc:
                sys.modules.pop(module_name, None)
                raise PluginInstallError(f"plugin factory failed: {exc}", error=str(exc)) from exc
        else:
            plugin = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, Plugin) and attr is not Plugin:
                    plugin = attr(sdk)
                    break
        if not isinstance(plugin, Plugin):
            sys.modules.pop(module_name, None)
            raise PluginInstallError(
                f"plugin module must expose create_plugin(sdk) or a Plugin subclass in {plugin_file!r}"
            )  # noqa: E501
        return plugin

    async def _run_hook(self, name: str, hook: str, *args: Any) -> None:
        plugin = self._plugins[name]
        method = getattr(plugin, hook, None)
        if method is None:  # pragma: no cover - base Plugin defines every hook
            return
        await self._sandbox.run(_maybe_await(method, plugin.context, *args))

    def _mark_failed(self, name: str, exc: Exception) -> None:
        try:
            self._lifecycle.transition(name, PluginStatus.FAILED)
        except Exception:  # pragma: no cover - every lifecycle state allows FAILED
            pass
        self._event_bus.emit(PLUGIN_FAILED, plugin=name, error=str(exc))
        self._metrics.record("failed", plugin=name)
        self._logger.log_event("plugin.failed", plugin=name, error=str(exc))

    # --------------------------------------------------------- enable/disable

    async def enable(self, name: str) -> PluginInfo:
        self._require(name)
        if self._lifecycle.is_enabled(name):
            return self.info(name)
        self._lifecycle.transition(name, PluginStatus.ENABLING)
        try:
            await self._run_hook(name, "on_enable")
        except Exception as exc:
            self._mark_failed(name, exc)
            raise
        self._lifecycle.transition(name, PluginStatus.ENABLED)
        self._event_bus.emit(PLUGIN_ENABLED, plugin=name)
        self._metrics.record("enable", plugin=name)
        return self.info(name)

    async def disable(self, name: str) -> PluginInfo:
        self._require(name)
        state = self._lifecycle.state(name)
        if state == PluginStatus.DISABLED:
            return self.info(name)
        if state == PluginStatus.ENABLED:
            await self._run_hook(name, "on_disable")
            self._lifecycle.transition(name, PluginStatus.DISABLED)
            self._event_bus.emit(PLUGIN_DISABLED, plugin=name)
            self._metrics.record("disable", plugin=name)
        elif state == PluginStatus.VERIFIED:
            self._lifecycle.transition(name, PluginStatus.DISABLED)
        return self.info(name)

    # ------------------------------------------------------------- reload

    async def reload(self, name: str) -> PluginInfo:
        self._require(name)
        if self._lifecycle.state(name) in (
            PluginStatus.INSTALLING,
            PluginStatus.UPDATING,
            PluginStatus.UNINSTALLING,
            PluginStatus.FAILED,
            PluginStatus.UNINSTALLED,
        ):  # noqa: E501
            raise PluginInstallError(
                f"cannot reload plugin {name!r} in state {self._lifecycle.state(name).value}", plugin=name
            )  # noqa: E501
        was_enabled = self._lifecycle.is_enabled(name)
        plugin_dir = self._dirs[name]
        spec = self._read_manifest(plugin_dir)
        self._validate_spec(spec)
        old_module = self._module_names.pop(name, None)
        if old_module:
            sys.modules.pop(old_module, None)
        old_plugin = self._plugins[name]
        old_sdk = self._sdks[name]
        self._extensions.unregister_plugin(name)
        old_sdk.cleanup()
        new_sdk = PluginSDK(name, self._extensions, self._event_bus, self._hooks, self._logger)
        plugin = self._load_plugin(new_sdk, plugin_dir)
        self._plugins[name] = plugin
        self._sdks[name] = new_sdk
        plugin.set_context(self._build_context(name, plugin))
        self._permissions.grant_from_manifest(name, spec.get("permissions", []))
        await self._run_hook(name, "on_reload", old_plugin.version)
        self._event_bus.emit(PLUGIN_RELOADED, plugin=name, version=spec["version"])
        self._metrics.record("reload", plugin=name)
        if was_enabled:
            await self.enable(name)
        return self.info(name)

    # ------------------------------------------------------------- upgrade

    async def upgrade(self, name: str, spec: dict[str, Any]) -> PluginInfo:
        self._require(name)
        if "plugin_code" not in spec:
            raise PluginInvalidError(f"upgrade of {name!r} requires 'plugin_code'", plugin=name)
        current = self._specs[name]
        new_version = spec.get("version", "")
        if compare_versions(new_version, current.version) <= 0:
            raise PluginUpgradeError(f"new version {new_version!r} must be newer than {current.version!r}", plugin=name)
        self._validate_spec(spec)
        self._verify(name, spec)
        was_enabled = self._lifecycle.is_enabled(name)
        plugin_dir = self._dirs[name]
        backup_dir = f"{plugin_dir}.bak"
        if Path(backup_dir).exists():
            shutil.rmtree(backup_dir)
        shutil.copytree(plugin_dir, backup_dir)

        self._lifecycle.transition(name, PluginStatus.UPDATING)
        try:
            self._replace_files(plugin_dir, spec)
            old_sdk = self._sdks[name]
            self._extensions.unregister_plugin(name)
            old_sdk.cleanup()
            new_sdk = PluginSDK(name, self._extensions, self._event_bus, self._hooks, self._logger)
            plugin = self._load_plugin(new_sdk, plugin_dir)
            self._plugins[name] = plugin
            self._sdks[name] = new_sdk
            plugin.set_context(self._build_context(name, plugin))
            self._permissions.grant_from_manifest(name, spec.get("permissions", []))
            await self._run_hook(name, "on_upgrade", current.version)
            self._specs[name] = PluginSpec(
                name=name,
                version=new_version,
                entry=spec.get("entry", "create_plugin"),
                description=spec.get("description", ""),
                author=spec.get("author", ""),
                tags=spec.get("tags", []),
                requires_router=spec.get("requires_router", ""),
                permissions=spec.get("permissions", []),
                signature=spec.get("signature", ""),
            )  # noqa: E501
        except Exception as exc:
            await self._rollback(name, backup_dir, was_enabled, exc)
        finally:
            if Path(backup_dir).exists():
                shutil.rmtree(backup_dir, ignore_errors=True)

        if was_enabled:
            self._lifecycle.transition(name, PluginStatus.ENABLED)
            await self.enable(name)
        else:
            self._lifecycle.transition(name, PluginStatus.DISABLED)
        self._event_bus.emit(PLUGIN_UPGRADED, plugin=name, version=new_version)
        self._metrics.record("upgrade", plugin=name)
        return self.info(name)

    async def _rollback(self, name: str, backup_dir: str, was_enabled: bool, cause: Exception) -> None:
        self._lifecycle.transition(name, PluginStatus.ROLLING_BACK)
        self._logger.log_event("plugin.rollback_started", plugin=name, error=str(cause))
        plugin_dir = self._dirs[name]
        try:
            shutil.rmtree(plugin_dir, ignore_errors=True)
            shutil.copytree(backup_dir, plugin_dir)
            spec = self._read_manifest(plugin_dir)
            old_sdk = self._sdks[name]
            self._extensions.unregister_plugin(name)
            old_sdk.cleanup()
            restored_sdk = PluginSDK(name, self._extensions, self._event_bus, self._hooks, self._logger)
            plugin = self._load_plugin(restored_sdk, plugin_dir)
            self._plugins[name] = plugin
            self._sdks[name] = restored_sdk
            plugin.set_context(self._build_context(name, plugin))
            self._permissions.grant_from_manifest(name, spec.get("permissions", []))
            self._lifecycle.transition(name, PluginStatus.ROLLED_BACK)
            self._metrics.record("rollback", plugin=name)
            self._logger.log_event("plugin.rolled_back", plugin=name)
        except Exception as restore_error:
            self._mark_failed(name, restore_error)
        raise PluginRollbackError(f"upgrade of {name!r} failed and was rolled back: {cause}", plugin=name) from cause

    def _replace_files(self, plugin_dir: str, spec: dict[str, Any]) -> None:
        with open(Path(plugin_dir) / "manifest.yaml", "w") as fh:
            fh.write(_spec_to_yaml({key: value for key, value in spec.items() if key != "plugin_code"}))
        if "plugin_code" in spec:
            with open(Path(plugin_dir) / "plugin.py", "w") as fh:
                fh.write(spec["plugin_code"])

    # ------------------------------------------------------------ uninstall

    async def uninstall(self, name: str) -> None:
        self._require(name)
        if self._lifecycle.is_enabled(name):
            await self.disable(name)
        self._lifecycle.transition(name, PluginStatus.UNINSTALLING)
        try:
            await self._run_hook(name, "on_uninstall")
        except Exception as exc:
            self._mark_failed(name, exc)
            raise PluginUninstallError(f"failed to uninstall {name!r}: {exc}", plugin=name) from exc
        plugin = self._plugins.pop(name, None)
        sdk = self._sdks.pop(name, None)
        if plugin is not None:
            await self._sandbox.run(_maybe_await(plugin.shutdown))
        if sdk is not None:
            sdk.cleanup()
        self._extensions.unregister_plugin(name)
        self._permissions.revoke(name)
        old_module = self._module_names.pop(name, None)
        if old_module:
            sys.modules.pop(old_module, None)
        plugin_dir = self._dirs.pop(name, None)
        if plugin_dir:
            shutil.rmtree(plugin_dir, ignore_errors=True)
        self._specs.pop(name, None)
        self._lifecycle.transition(name, PluginStatus.UNINSTALLED)
        self._lifecycle.drop(name)
        self._event_bus.emit(PLUGIN_UNINSTALLED, plugin=name)
        self._metrics.record("uninstall", plugin=name)

    # ------------------------------------------------------------- queries

    def _require(self, name: str) -> None:
        if name not in self._plugins:
            raise PluginNotFoundError(f"plugin {name!r} is not installed", plugin=name)

    def get(self, name: str) -> PluginInfo:
        self._require(name)
        return self.info(name)

    def plugin(self, name: str) -> Plugin:
        self._require(name)
        return self._plugins[name]

    def spec(self, name: str) -> PluginSpec:
        self._require(name)
        return self._specs[name]

    def info(self, name: str) -> PluginInfo:
        self._require(name)
        spec = self._specs[name]
        extensions: dict[str, list[str]] = {}
        for extension in self._extensions.list_by_plugin(name):
            key = extension.kind.value
            extensions.setdefault(key, []).append(extension.name)
        return PluginInfo(
            name=name,
            version=spec.version,
            status=self._lifecycle.state(name),
            description=spec.description,
            author=spec.author,
            tags=spec.tags,
            signature=spec.signature,
            extensions=extensions,
        )

    def list(self, status: str | PluginStatus | None = None) -> list[PluginInfo]:
        infos = [self.info(name) for name in sorted(self._plugins)]
        if status is None:
            return infos
        expected = status.value if isinstance(status, PluginStatus) else status
        return [info for info in infos if info.status.value == expected]

    def is_enabled(self, name: str) -> bool:
        self._require(name)
        return self._lifecycle.is_enabled(name)

    def status(self, name: str) -> PluginStatus:
        self._require(name)
        return self._lifecycle.state(name)

    def names(self) -> list[str]:
        return sorted(self._plugins)

    def count(self) -> int:
        return len(self._plugins)

    # ------------------------------------------------------- hooks & events

    async def dispatch_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> Any:

        enabled = {name for name in self._plugins if self._lifecycle.is_enabled(name)}
        plugins = kwargs.pop("plugins", enabled)
        result = await self._hooks.dispatch(hook_name, *args, plugins=plugins, **kwargs)
        self._metrics.record("hook", plugin="")
        return result

    def dispatch_hook_sync(self, hook_name: str, *args: Any, **kwargs: Any) -> Any:
        return self._hooks.dispatch_sync(hook_name, *args, **kwargs)

    def emit_event(self, event: str, **data: Any) -> list[Any]:
        return self._event_bus.emit_plugin_event(event, **data)

    async def emit_event_async(self, event: str, **data: Any) -> list[Any]:
        return await self._event_bus.emit_plugin_event_async(event, **data)

    def register_hook(self, hook_name: str, listener: Any, plugin: str = "") -> None:
        self._hooks.register(hook_name, listener, plugin=plugin)

    def register_hook_plugin(self, plugin: Plugin, hook_name: str, listener: Any) -> None:
        self._hooks.register(hook_name, listener, plugin=plugin.name)

    # ------------------------------------------------------------ reporting

    def summary(self) -> dict[str, Any]:
        infos = self.list()
        by_status: dict[str, int] = {}
        for info in infos:
            by_status[info.status.value] = by_status.get(info.status.value, 0) + 1
        return {
            "total": len(infos),
            "enabled": sum(1 for info in infos if info.status == PluginStatus.ENABLED),
            "by_status": by_status,
            "extensions": self._extensions.count_by_kind(),
            "metrics": self._metrics.summary(),
            "marketplace_entries": self._marketplace.count(),
            "permissions": self._permissions.all_permissions(),
        }


def _spec_to_yaml(manifest: dict[str, Any]) -> str:
    import io

    import yaml

    buffer = io.StringIO()
    yaml.safe_dump(manifest, buffer, sort_keys=True)
    return buffer.getvalue()


def create_plugin_manager(config: PluginConfig | None = None, **overrides: Any) -> PluginManager:
    """Dependency-injection factory for the plugin platform."""
    config = config or PluginConfig.from_env()
    container = Container()
    container.register_instance("plugin_config", config)
    container.register_instance("plugin_logger", PluginLogger(config))
    container.register_instance("plugin_sandbox", Sandbox(config, container.resolve("plugin_logger")))
    container.register_instance("plugin_permissions", PermissionManager(config, container.resolve("plugin_logger")))
    container.register_instance("plugin_event_bus", PluginEventBus())
    container.register_instance("plugin_hooks", HookSystem(container.resolve("plugin_logger")))
    container.register_instance("plugin_extensions", ExtensionRegistry())
    container.register_instance("plugin_metrics", PluginMetricsTracker(config))
    container.register_instance("plugin_marketplace", Marketplace(config, container.resolve("plugin_logger")))
    container.register_instance("plugin_lifecycle", PluginLifecycle(container.resolve("plugin_logger")))
    container.register_instance("plugin_validator", ManifestValidator())
    container.register_instance("plugin_compatibility", CompatibilityChecker())
    manager = PluginManager(
        config=config,
        logger=container.resolve("plugin_logger"),
        sandbox=container.resolve("plugin_sandbox"),
        permissions=container.resolve("plugin_permissions"),
        container=container,
        event_bus=container.resolve("plugin_event_bus"),
        hooks=container.resolve("plugin_hooks"),
        extensions=container.resolve("plugin_extensions"),
        metrics=container.resolve("plugin_metrics"),
        marketplace=container.resolve("plugin_marketplace"),
        lifecycle=container.resolve("plugin_lifecycle"),
        validator=container.resolve("plugin_validator"),
        compatibility=container.resolve("plugin_compatibility"),
    )
    container.register_instance("plugin_manager", manager)
    for key, value in overrides.items():
        container.register_instance(key, value)
    return manager
