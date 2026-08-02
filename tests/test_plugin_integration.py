"""Integration tests: plugin system + router + events together."""

import pytest

from app.event_bus import event_bus
from app.plugin.base import AIPlugin, HookResult
from app.router import AIRouter, ProviderMetrics


class TestNewHooksInRouter:
    def test_before_route_in_router(self):
        router = AIRouter()
        results = []

        class TestPlugin(AIPlugin):
            name = "test_route"
            async def before_route(self, request, context):
                results.append("before_route_called")
                return HookResult()

        router.plugin_registry._plugins["test_route"] = TestPlugin()
        import asyncio
        asyncio.run(router.pipeline.execute_before_route("req", {}))
        assert "before_route_called" in results

    def test_after_route_in_router(self):
        router = AIRouter()
        received = []

        class TestPlugin(AIPlugin):
            name = "test_after_route"
            async def after_route(self, request, context, routes):
                received.append(routes)
                return HookResult()

        router.plugin_registry._plugins["test_after_route"] = TestPlugin()
        import asyncio
        routes = [("p1", "m1"), ("p2", "m2")]
        asyncio.run(router.pipeline.execute_after_route("req", {}, routes))
        assert received == [routes]

    def test_before_provider_in_router(self):
        router = AIRouter()
        received = {}

        class TestPlugin(AIPlugin):
            name = "test_bp"
            async def before_provider(self, request, provider_name, model, context):
                received["p"] = provider_name
                received["m"] = model
                return HookResult()

        router.plugin_registry._plugins["test_bp"] = TestPlugin()
        import asyncio
        asyncio.run(router.pipeline.execute_before_provider("req", "openai", "gpt-4", {}))
        assert received == {"p": "openai", "m": "gpt-4"}

    def test_after_provider_in_router(self):
        router = AIRouter()
        received = {}

        class TestPlugin(AIPlugin):
            name = "test_ap"
            async def after_provider(self, request, response, provider_name, model, context):
                received["resp"] = response
                return HookResult()

        router.plugin_registry._plugins["test_ap"] = TestPlugin()
        import asyncio
        asyncio.run(router.pipeline.execute_after_provider("req", "resp_data", "p", "m", {}))
        assert received["resp"] == "resp_data"

    def test_before_response_in_router(self):
        router = AIRouter()
        received = []

        class TestPlugin(AIPlugin):
            name = "test_br"
            async def before_response(self, request, response, context):
                received.append(response)
                return HookResult()

        router.plugin_registry._plugins["test_br"] = TestPlugin()
        import asyncio
        asyncio.run(router.pipeline.execute_before_response("req", "resp_data", {}))
        assert received == ["resp_data"]

    def test_all_new_hooks_integration(self):
        router = AIRouter()
        order = []

        class FullPlugin(AIPlugin):
            name = "full_test"

            async def before_route(self, request, context):
                order.append("before_route")
                return HookResult()
            async def after_route(self, request, context, routes):
                order.append("after_route")
                return HookResult()
            async def before_provider(self, request, provider_name, model, context):
                order.append("before_provider")
                return HookResult()
            async def after_provider(self, request, response, provider_name, model, context):
                order.append("after_provider")
                return HookResult()
            async def before_response(self, request, response, context):
                order.append("before_response")
                return HookResult()
            async def after_response(self, request, response, context):
                order.append("after_response")
                return HookResult()

        router.plugin_registry._plugins["full_test"] = FullPlugin()
        import asyncio

        asyncio.run(router.pipeline.execute_before_route("req", {}))
        asyncio.run(router.pipeline.execute_after_route("req", {}, [("p", "m")]))
        asyncio.run(router.pipeline.execute_before_provider("req", "p", "m", {}))
        asyncio.run(router.pipeline.execute_after_provider("req", "r", "p", "m", {}))
        asyncio.run(router.pipeline.execute_before_response("req", "r", {}))
        asyncio.run(router.pipeline.execute_after_response("req", "r", {}))

        assert order == [
            "before_route",
            "after_route",
            "before_provider",
            "after_provider",
            "before_response",
            "after_response",
        ]


class TestEventBusInRouter:
    def test_event_bus_global_instance(self):
        from app.event_bus import event_bus
        assert event_bus is not None

    def test_emit_request_started(self):
        results = []

        async def handler(**kwargs):
            results.append(kwargs)

        event_bus.subscribe("request.started", handler)
        import asyncio
        asyncio.run(event_bus.emit("request.started", request_id="test-123", task="chat", model="gpt-4o"))

        assert len(results) == 1
        assert results[0]["request_id"] == "test-123"
        assert results[0]["task"] == "chat"

    def test_emit_provider_selected(self):
        results = []

        async def handler(**kwargs):
            results.append(kwargs)

        event_bus.subscribe("provider.selected", handler)
        import asyncio
        asyncio.run(event_bus.emit("provider.selected", provider="openai", model="gpt-4o", request_id="r1"))

        assert len(results) == 1
        assert results[0]["provider"] == "openai"

    def test_emit_fallback_triggered(self):
        results = []

        async def handler(**kwargs):
            results.append(kwargs)

        event_bus.subscribe("fallback.triggered", handler)
        import asyncio
        asyncio.run(event_bus.emit("fallback.triggered", from_provider="openai", to_provider="anthropic", task="chat"))

        assert results[0]["from_provider"] == "openai"

    def test_emit_cache_hit(self):
        results = []

        async def handler(**kwargs):
            results.append(kwargs)

        event_bus.subscribe("cache.hit", handler)
        import asyncio
        asyncio.run(event_bus.emit("cache.hit", cache_name="responses"))

        assert results[0]["cache_name"] == "responses"

    def test_emit_benchmark_completed(self):
        results = []

        async def handler(**kwargs):
            results.append(kwargs)

        event_bus.subscribe("benchmark.completed", handler)
        import asyncio
        asyncio.run(event_bus.emit("benchmark.completed", model="gpt-4o", provider="openai", num_requests=10))

        assert results[0]["model"] == "gpt-4o"

    def test_plugin_before_request_in_router(self):
        router = AIRouter()
        plugin_ctx = {}

        class TestPlugin(AIPlugin):
            name = "test_integration"

            async def before_request(self, request, context):
                plugin_ctx["called"] = True
                plugin_ctx["context_keys"] = list(context.keys())
                return HookResult()

        router.plugin_registry._plugins["test_integration"] = TestPlugin()
        import asyncio
        asyncio.run(router.pipeline.execute_before_request("req", {"test": True}))

        assert plugin_ctx["called"] is True

    def test_plugin_after_response_in_router(self):
        router = AIRouter()
        plugin_ctx = {}

        class TestPlugin(AIPlugin):
            name = "test_after"

            async def after_response(self, request, response, context):
                plugin_ctx["response_seen"] = response
                return HookResult()

        router.plugin_registry._plugins["test_after"] = TestPlugin()
        import asyncio
        asyncio.run(router.pipeline.execute_after_response("req", "resp_data", {}))

        assert plugin_ctx["response_seen"] == "resp_data"

    def test_plugin_on_error_in_router(self):
        router = AIRouter()
        plugin_ctx = {}

        class TestPlugin(AIPlugin):
            name = "test_error"

            async def on_error(self, request, error, context):
                plugin_ctx["error"] = str(error)
                return HookResult()

        router.plugin_registry._plugins["test_error"] = TestPlugin()
        import asyncio
        asyncio.run(router.pipeline.execute_on_error("req", ValueError("boom"), {}))

        assert "boom" in plugin_ctx["error"]

    def test_plugin_cancels_request(self):
        router = AIRouter()

        class BlockPlugin(AIPlugin):
            name = "blocker"

            async def before_request(self, request, context):
                return HookResult(should_cancel=True, cancel_reason="blocked by plugin")

        router.plugin_registry._plugins["blocker"] = BlockPlugin()
        import asyncio
        result = asyncio.run(router.pipeline.execute_before_request("req", {}))
        assert result.should_cancel is True
        assert result.cancel_reason == "blocked by plugin"

    def test_initialize_shutdown_plugins(self):
        router = AIRouter()
        init_called = []
        shutdown_called = []

        class LifecyclePlugin(AIPlugin):
            name = "lifecycle"

            async def initialize(self):
                init_called.append("ok")

            async def shutdown(self):
                shutdown_called.append("ok")

        router.plugin_registry._plugins["lifecycle"] = LifecyclePlugin()
        import asyncio
        asyncio.run(router.pipeline.initialize_plugins())
        assert init_called == ["ok"]

        asyncio.run(router.pipeline.shutdown_plugins())
        assert shutdown_called == ["ok"]

    def test_hot_reload_watcher(self):
        router = AIRouter()
        assert router._plugin_watcher is not None
        assert router._plugin_watcher._interval == 5.0
