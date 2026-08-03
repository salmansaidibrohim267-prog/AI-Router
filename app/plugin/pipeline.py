from __future__ import annotations

from typing import Any

from app.event_bus import event_bus
from app.plugin.base import HookResult
from app.plugin.registry import PluginRegistry


class MiddlewarePipeline:
    def __init__(self, registry: PluginRegistry):
        self._registry = registry

    async def _run_hook(
        self,
        hook_name: str,
        plugin: Any,
        hook_method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> HookResult:
        method = getattr(plugin, hook_method_name, None)
        if method is None:
            return HookResult()
        try:
            result = await method(*args, **kwargs)
            if not isinstance(result, HookResult):
                return HookResult()
            return result
        except Exception:
            import traceback

            traceback.print_exc()
        return HookResult()

    async def _execute_hook_chain(
        self,
        hook_name: str,
        plugin_method: str,
        *args: Any,
        **kwargs: Any,
    ) -> HookResult:
        aggregate = HookResult()
        for plugin in self._registry.get_enabled():
            result = await self._run_hook(hook_name, plugin, plugin_method, *args, **kwargs)
            if result.should_cancel:
                return result
            if result.modified_request is not None:
                aggregate.modified_request = result.modified_request
            if result.modified_response is not None:
                aggregate.modified_response = result.modified_response
            if result.metadata:
                aggregate.metadata.update(result.metadata)
        return aggregate

    async def execute_before_request(
        self,
        request: Any,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain("before_request", "before_request", request, context)

    async def execute_before_route(
        self,
        request: Any,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain("before_route", "before_route", request, context)

    async def execute_after_route(
        self,
        request: Any,
        context: dict[str, Any],
        routes: list[tuple[str, str]],
    ) -> HookResult:
        return await self._execute_hook_chain("after_route", "after_route", request, context, routes)

    async def execute_before_provider(
        self,
        request: Any,
        provider_name: str,
        model: str,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain(
            "before_provider", "before_provider", request, provider_name, model, context
        )

    async def execute_after_provider(
        self,
        request: Any,
        response: Any,
        provider_name: str,
        model: str,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain(
            "after_provider", "after_provider", request, response, provider_name, model, context
        )

    async def execute_before_response(
        self,
        request: Any,
        response: Any,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain("before_response", "before_response", request, response, context)

    async def execute_after_response(
        self,
        request: Any,
        response: Any,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain("after_response", "after_response", request, response, context)

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

    async def execute_before_plan(
        self,
        request: Any,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain("before_plan", "before_plan", request, context)

    async def execute_after_agent(
        self,
        agent_result: Any,
        agent_name: str,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain("after_agent", "after_agent", agent_result, agent_name, context)

    async def execute_before_reflection(
        self,
        agent_result: Any,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain("before_reflection", "before_reflection", agent_result, context)

    async def execute_after_orchestrate(
        self,
        response: Any,
        context: dict[str, Any],
    ) -> HookResult:
        return await self._execute_hook_chain("after_orchestrate", "after_orchestrate", response, context)

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
