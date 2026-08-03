from __future__ import annotations

import inspect
import uuid
from typing import Any, Callable

from .config import PluginConfig
from .di import Container
from .events import PluginEventBus
from .hooks import HookSystem
from .logging import PluginLogger
from .models import Extension, ExtensionKind, PermissionResource, SchedulerSpec
from .permissions import PermissionManager
from .registry import ExtensionRegistry
from .sandbox import Sandbox


class PluginContext:
    """Services injected into a plugin at creation time (DI pattern)."""

    def __init__(
        self,
        plugin_name: str,
        config: PluginConfig,
        logger: PluginLogger,
        sandbox: Sandbox,
        permissions: PermissionManager,
        container: Container,
        event_bus: PluginEventBus,
        hooks: HookSystem,
        extensions: ExtensionRegistry,
    ) -> None:
        self.plugin_name = plugin_name
        self.config = config
        self.logger = logger
        self.sandbox = sandbox
        self.permissions = permissions
        self.container = container
        self.event_bus = event_bus
        self.hooks = hooks
        self.extensions = extensions

    def check_permission(self, resource: str | PermissionResource, action: str = "*") -> bool:
        resource_name = resource.value if isinstance(resource, PermissionResource) else resource
        return self.permissions.check(self.plugin_name, resource_name, action)

    def require_permission(self, resource: str | PermissionResource, action: str = "*") -> None:
        resource_name = resource.value if isinstance(resource, PermissionResource) else resource
        self.permissions.check_or_raise(self.plugin_name, resource_name, action)

    def emit(self, event: str, **data: Any) -> list[Any]:
        return self.event_bus.emit_plugin_event(event, plugin=self.plugin_name, **data)

    def log(self, event: str, **extra: Any) -> None:
        self.logger.log_event(event, plugin=self.plugin_name, **extra)


class Plugin:
    """Base class for platform plugins (Template Method pattern)."""

    name: str = "base"
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    tags: list[str] = []

    def __init__(self, sdk: PluginSDK | None = None) -> None:
        self.sdk = sdk
        self._context: PluginContext | None = None

    @property
    def context(self) -> PluginContext:
        if self._context is None:
            raise RuntimeError(f"plugin {self.name!r} has no active context")
        return self._context

    def set_context(self, context: PluginContext) -> None:
        self._context = context

    async def on_install(self, context: PluginContext) -> None:
        pass

    async def on_enable(self, context: PluginContext) -> None:
        pass

    async def on_disable(self, context: PluginContext) -> None:
        pass

    async def on_reload(self, context: PluginContext, previous_version: str = "") -> None:
        pass

    async def on_upgrade(self, context: PluginContext, old_version: str) -> None:
        pass

    async def on_uninstall(self, context: PluginContext) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    def __repr__(self) -> str:
        return f"<Plugin name={self.name} v{self.version}>"


async def _maybe_await(callable_: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    result = callable_(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


class PluginSDK:
    """Registration surface handed to plugins (Factory pattern).

    A plugin calls ``create_plugin(sdk)`` from its entry point and uses the
    SDK to register tools, API routes, MCP/LLM providers, embedding models,
    schedulers, CLI commands and event listeners.
    """

    def __init__(
        self,
        plugin_name: str,
        extensions: ExtensionRegistry,
        event_bus: PluginEventBus,
        hooks: HookSystem,
        logger: PluginLogger,
    ) -> None:
        self._plugin_name = plugin_name
        self._extensions = extensions
        self._event_bus = event_bus
        self._hooks = hooks
        self._logger = logger
        self._listeners: list[tuple[str, Callable[..., Any]]] = []

    # --------------------------------------------------------------- tools

    def register_tool(self, name: str, handler: Callable[..., Any], schema: dict[str, Any] | None = None) -> Extension:
        return self._extensions.register(
            Extension(
                kind=ExtensionKind.TOOL,
                name=name,
                handler=handler,
                plugin=self._plugin_name,
                metadata={"schema": schema},
            )  # noqa: E501
        )

    def unregister_tool(self, name: str) -> bool:
        return self._extensions.unregister(ExtensionKind.TOOL, name)

    # -------------------------------------------------------------- routes

    def register_route(self, path: str, handler: Callable[..., Any], methods: tuple[str, ...] = ("GET",)) -> Extension:
        return self._extensions.register(
            Extension(
                kind=ExtensionKind.ROUTE,
                name=path,
                handler=handler,
                plugin=self._plugin_name,
                metadata={"methods": list(methods)},
            )
        )

    def unregister_route(self, path: str) -> bool:
        return self._extensions.unregister(ExtensionKind.ROUTE, path)

    # --------------------------------------------------------- MCP provider

    def register_mcp_provider(
        self, name: str, factory: Callable[..., Any], config: dict[str, Any] | None = None
    ) -> Extension:  # noqa: E501
        return self._extensions.register(
            Extension(
                kind=ExtensionKind.MCP_PROVIDER,
                name=name,
                handler=factory,
                plugin=self._plugin_name,
                metadata={"config": config},
            )  # noqa: E501
        )

    def unregister_mcp_provider(self, name: str) -> bool:
        return self._extensions.unregister(ExtensionKind.MCP_PROVIDER, name)

    # --------------------------------------------------------- LLM provider

    def register_llm_provider(
        self, name: str, factory: Callable[..., Any], models: list[str] | None = None
    ) -> Extension:  # noqa: E501
        return self._extensions.register(
            Extension(
                kind=ExtensionKind.LLM_PROVIDER,
                name=name,
                handler=factory,
                plugin=self._plugin_name,
                metadata={"models": models or []},
            )  # noqa: E501
        )

    def unregister_llm_provider(self, name: str) -> bool:
        return self._extensions.unregister(ExtensionKind.LLM_PROVIDER, name)

    # ------------------------------------------------------ embedding model

    def register_embedding_model(self, name: str, factory: Callable[..., Any], dimensions: int = 0) -> Extension:
        return self._extensions.register(
            Extension(
                kind=ExtensionKind.EMBEDDING_MODEL,
                name=name,
                handler=factory,
                plugin=self._plugin_name,
                metadata={"dimensions": dimensions},
            )  # noqa: E501
        )

    def unregister_embedding_model(self, name: str) -> bool:
        return self._extensions.unregister(ExtensionKind.EMBEDDING_MODEL, name)

    # ------------------------------------------------------------ scheduler

    def register_scheduler(
        self, name: str, spec: SchedulerSpec | dict[str, Any], handler: Callable[..., Any]
    ) -> Extension:  # noqa: E501
        if isinstance(spec, dict):
            spec = SchedulerSpec(**spec)
        return self._extensions.register(
            Extension(
                kind=ExtensionKind.SCHEDULER,
                name=name,
                handler=handler,
                plugin=self._plugin_name,
                metadata={"spec": spec.to_dict()},
            )  # noqa: E501
        )

    def unregister_scheduler(self, name: str) -> bool:
        return self._extensions.unregister(ExtensionKind.SCHEDULER, name)

    # ---------------------------------------------------------- CLI command

    def register_cli_command(self, name: str, handler: Callable[..., Any], help_text: str = "") -> Extension:
        return self._extensions.register(
            Extension(
                kind=ExtensionKind.CLI_COMMAND,
                name=name,
                handler=handler,
                plugin=self._plugin_name,
                metadata={"help": help_text},
            )  # noqa: E501
        )

    def unregister_cli_command(self, name: str) -> bool:
        return self._extensions.unregister(ExtensionKind.CLI_COMMAND, name)

    # ------------------------------------------------------- event listener

    def register_event_listener(self, event: str, handler: Callable[..., Any]) -> Extension:
        extension_name = f"{event}#{uuid.uuid4().hex[:8]}"
        extension = self._extensions.register(
            Extension(
                kind=ExtensionKind.EVENT_LISTENER,
                name=extension_name,
                handler=handler,
                plugin=self._plugin_name,
                metadata={"event": event},
            )
        )
        self._event_bus.subscribe(event, handler)
        self._listeners.append((event, handler, extension_name))
        return extension

    def unregister_event_listener(self, event: str, handler: Callable[..., Any] | None = None) -> bool:
        removed = False
        if handler is not None:
            for registered_event, registered_handler, extension_name in list(self._listeners):
                if registered_event == event and registered_handler is handler:
                    self._event_bus.unsubscribe(event, registered_handler)
                    self._listeners.remove((registered_event, registered_handler, extension_name))
                    self._extensions.unregister(ExtensionKind.EVENT_LISTENER, extension_name)
                    removed = True
            return removed
        for registered_event, registered_handler, extension_name in list(self._listeners):
            if registered_event == event:
                self._event_bus.unsubscribe(registered_event, registered_handler)
                self._listeners.remove((registered_event, registered_handler, extension_name))
                self._extensions.unregister(ExtensionKind.EVENT_LISTENER, extension_name)
                removed = True
        return removed

    def cleanup(self) -> None:
        for event, handler, _ in self._listeners:
            self._event_bus.unsubscribe(event, handler)
        self._listeners.clear()

    # ------------------------------------------------------------- queries

    def get_extension(self, kind: ExtensionKind | str, name: str) -> Extension:
        return self._extensions.get(kind, name)

    def extensions(self, kind: ExtensionKind | str | None = None) -> list[Extension]:
        return self._extensions.list(kind)
