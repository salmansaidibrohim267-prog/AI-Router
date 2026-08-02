"""Tests for plugin lifecycle management (initialize, shutdown, enable/disable)."""

import asyncio

import pytest

from app.plugin.base import AIPlugin, HookResult
from app.plugin.pipeline import MiddlewarePipeline
from app.plugin.registry import PluginRegistry


class TestPluginLifecycle:
    def test_initialize_called_for_each_plugin(self):
        inits = []

        class InitPlugin(AIPlugin):
            name = "init1"
            async def initialize(self):
                inits.append("init1")

        class InitPlugin2(AIPlugin):
            name = "init2"
            async def initialize(self):
                inits.append("init2")

        registry = PluginRegistry()
        registry._plugins["init1"] = InitPlugin()
        registry._plugins["init2"] = InitPlugin2()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.initialize_plugins())
        assert "init1" in inits
        assert "init2" in inits

    def test_shutdown_called_for_each_plugin(self):
        shutdowns = []

        class ShutdownPlugin(AIPlugin):
            name = "sd1"
            async def shutdown(self):
                shutdowns.append("sd1")

        class ShutdownPlugin2(AIPlugin):
            name = "sd2"
            async def shutdown(self):
                shutdowns.append("sd2")

        registry = PluginRegistry()
        registry._plugins["sd1"] = ShutdownPlugin()
        registry._plugins["sd2"] = ShutdownPlugin2()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.shutdown_plugins())
        assert "sd1" in shutdowns
        assert "sd2" in shutdowns

    def test_disabled_plugin_not_initialized(self):
        inits = []

        class DisabledPlugin(AIPlugin):
            name = "disabled_init"
            async def initialize(self):
                inits.append("should_not_run")

        registry = PluginRegistry()
        registry._plugins["disabled_init"] = DisabledPlugin()
        registry.disable("disabled_init")
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.initialize_plugins())
        assert inits == []

    def test_disabled_plugin_not_shutdown(self):
        shutdowns = []

        class DisabledPlugin(AIPlugin):
            name = "disabled_sd"
            async def shutdown(self):
                shutdowns.append("should_not_run")

        registry = PluginRegistry()
        registry._plugins["disabled_sd"] = DisabledPlugin()
        registry.disable("disabled_sd")
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.shutdown_plugins())
        assert shutdowns == []

    def test_enable_disable_during_lifecycle(self):
        registry = PluginRegistry()
        registry._plugins["test"] = AIPlugin()
        assert registry.is_enabled("test") is True

        registry.disable("test")
        assert registry.is_enabled("test") is False

        registry.enable("test")
        assert registry.is_enabled("test") is True

    def test_lifecycle_order_init_before_use(self):
        order = []

        class LifecyclePlugin(AIPlugin):
            name = "lifecycle"
            async def initialize(self):
                order.append("init")
            async def before_request(self, request, context):
                order.append("before_request")
                return HookResult()
            async def shutdown(self):
                order.append("shutdown")

        registry = PluginRegistry()
        registry._plugins["lifecycle"] = LifecyclePlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.initialize_plugins())
        asyncio.run(pipeline.execute_before_request("req", {}))
        asyncio.run(pipeline.shutdown_plugins())

        assert order == ["init", "before_request", "shutdown"]

    def test_initialize_failure_does_not_stop_others(self):
        inits = []

        class FailingInitPlugin(AIPlugin):
            name = "fail_init"
            async def initialize(self):
                raise RuntimeError("init failed")

        class GoodInitPlugin(AIPlugin):
            name = "good_init"
            async def initialize(self):
                inits.append("good")

        registry = PluginRegistry()
        registry._plugins["fail_init"] = FailingInitPlugin()
        registry._plugins["good_init"] = GoodInitPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.initialize_plugins())
        assert inits == ["good"]

    def test_shutdown_failure_does_not_stop_others(self):
        shutdowns = []

        class FailingShutdownPlugin(AIPlugin):
            name = "fail_sd"
            async def shutdown(self):
                raise RuntimeError("shutdown failed")

        class GoodShutdownPlugin(AIPlugin):
            name = "good_sd"
            async def shutdown(self):
                shutdowns.append("good")

        registry = PluginRegistry()
        registry._plugins["fail_sd"] = FailingShutdownPlugin()
        registry._plugins["good_sd"] = GoodShutdownPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.shutdown_plugins())
        assert shutdowns == ["good"]

    def test_plugin_pipeline_shutdown(self):
        shutdowns = []

        class PluginA(AIPlugin):
            name = "a"
            async def shutdown(self):
                shutdowns.append("a")

        class PluginB(AIPlugin):
            name = "b"
            async def shutdown(self):
                shutdowns.append("b")

        registry = PluginRegistry()
        registry._plugins["a"] = PluginA()
        registry._plugins["b"] = PluginB()
        pipeline = MiddlewarePipeline(registry)
        asyncio.run(pipeline.shutdown_plugins())

        assert "a" in shutdowns
        assert "b" in shutdowns

    def test_reinitialize_plugin(self):
        inits = []

        class ReinitPlugin(AIPlugin):
            name = "reinit"
            async def initialize(self):
                inits.append("init")

        registry = PluginRegistry()
        registry._plugins["reinit"] = ReinitPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.initialize_plugins())
        assert len(inits) == 1

        asyncio.run(pipeline.initialize_plugins())
        assert len(inits) == 2

    def test_plugin_initialized_event_emitted(self):
        from app.event_bus import event_bus
        results = []

        async def handler(**kwargs):
            results.append(kwargs)

        event_bus.subscribe("plugins.initialized", handler)

        registry = PluginRegistry()
        registry._plugins["test"] = AIPlugin()
        pipeline = MiddlewarePipeline(registry)
        asyncio.run(pipeline.initialize_plugins())

        assert len(results) >= 1
        event_bus.unsubscribe("plugins.initialized", handler)

    def test_shutting_down_event_emitted(self):
        from app.event_bus import event_bus
        results = []

        async def handler(**kwargs):
            results.append(kwargs)

        event_bus.subscribe("plugins.shutting_down", handler)

        registry = PluginRegistry()
        registry._plugins["test"] = AIPlugin()
        pipeline = MiddlewarePipeline(registry)
        asyncio.run(pipeline.shutdown_plugins())

        assert len(results) >= 1
        event_bus.unsubscribe("plugins.shutting_down", handler)
