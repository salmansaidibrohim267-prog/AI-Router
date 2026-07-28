from __future__ import annotations

from typing import Any

from app.plugin.base import HookResult
from app.plugin.registry import PluginRegistry
from app.event_bus import event_bus


class MiddlewarePipeline:
    def __init__(self, registry: PluginRegistry):
        self._registry = registry

    async def execute_before_request(
        self,
        request: Any,
        context: dict[str, Any],
    ) -> HookResult:
        aggregate = HookResult()
        for plugin in self._registry.get_enabled():
            try:
                result = await plugin.before_request(request, context)
                if result.should_cancel:
                    return result
                if result.modified_request is not None:
                    aggregate.modified_request = result.modified_request
                if result.metadata:
                    aggregate.metadata.update(result.metadata)
            except Exception:
                import traceback
                traceback.print_exc()
        return aggregate

    async def execute_after_response(
        self,
        request: Any,
        response: Any,
        context: dict[str, Any],
    ) -> HookResult:
        aggregate = HookResult()
        for plugin in self._registry.get_enabled():
            try:
                result = await plugin.after_response(request, response, context)
                if result.should_cancel:
                    return result
                if result.modified_response is not None:
                    aggregate.modified_response = result.modified_response
                if result.metadata:
                    aggregate.metadata.update(result.metadata)
            except Exception:
                import traceback
                traceback.print_exc()
        return aggregate

    async def execute_on_error(
        self,
        request: Any,
        error: Exception,
        context: dict[str, Any],
    ) -> None:
        for plugin in self._registry.get_enabled():
            try:
                await plugin.on_error(request, error, context)
            except Exception:
                pass

    async def initialize_plugins(self) -> None:
        for plugin in self._registry.get_enabled():
            try:
                await plugin.initialize()
            except Exception:
                import traceback
                traceback.print_exc()

        await event_bus.emit("plugins.initialized", count=len(self._registry.get_enabled()))

    async def shutdown_plugins(self) -> None:
        await event_bus.emit("plugins.shutting_down")
        for plugin in self._registry.get_enabled():
            try:
                await plugin.shutdown()
            except Exception:
                pass
