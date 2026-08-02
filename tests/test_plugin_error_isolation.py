"""Tests for error isolation in plugin hooks - failures in one plugin should not affect others."""

import asyncio

import pytest

from app.plugin.base import AIPlugin, HookResult
from app.plugin.pipeline import MiddlewarePipeline
from app.plugin.registry import PluginRegistry


class FailingPlugin(AIPlugin):
    name = "failing"

    async def before_route(self, request, context):
        raise ValueError("plugin crashed")

    async def after_route(self, request, context, routes):
        raise RuntimeError("runtime error")

    async def before_provider(self, request, provider_name, model, context):
        raise Exception("generic error")

    async def after_provider(self, request, response, provider_name, model, context):
                raise ValueError("after_provider crash")

    async def before_response(self, request, response, context):
                raise Exception("before_response crash")

    async def after_response(self, request, response, context):
                raise Exception("after_response crash")

    async def before_request(self, request, context):
                raise ValueError("before_request crash")

    async def on_error(self, request, error, context):
                raise Exception("error handler crashed")


class WellBehavedPlugin(AIPlugin):
    name = "well_behaved"
    calls = []

    async def before_route(self, request, context):
        self.calls.append("before_route")
        return HookResult(metadata={"ok": True})

    async def after_route(self, request, context, routes):
        self.calls.append("after_route")
        return HookResult(metadata={"routes": len(routes)})

    async def before_provider(self, request, provider_name, model, context):
        self.calls.append("before_provider")
        return HookResult()

    async def after_provider(self, request, response, provider_name, model, context):
        self.calls.append("after_provider")
        return HookResult()

    async def before_response(self, request, response, context):
        self.calls.append("before_response")
        return HookResult()

    async def after_response(self, request, response, context):
        self.calls.append("after_response")
        return HookResult()

    async def before_request(self, request, context):
        self.calls.append("before_request")
        return HookResult()


class TestErrorIsolation:
    def setup_method(self):
        WellBehavedPlugin.calls = []

    def test_failing_before_route_does_not_break_others(self):
        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        registry._plugins["good"] = WellBehavedPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_route("req", {}))
        assert WellBehavedPlugin.calls == ["before_route"]
        assert result.metadata == {"ok": True}

    def test_failing_after_route_does_not_break_others(self):
        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        registry._plugins["good"] = WellBehavedPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_after_route("req", {}, [("p", "m")]))
        assert WellBehavedPlugin.calls == ["after_route"]
        assert result.metadata == {"routes": 1}

    def test_failing_before_provider_does_not_break_others(self):
        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        registry._plugins["good"] = WellBehavedPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_provider("req", "p", "m", {}))
        assert WellBehavedPlugin.calls == ["before_provider"]

    def test_failing_after_provider_does_not_break_others(self):
        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        registry._plugins["good"] = WellBehavedPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_after_provider("req", "resp", "p", "m", {}))
        assert WellBehavedPlugin.calls == ["after_provider"]

    def test_failing_before_response_does_not_break_others(self):
        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        registry._plugins["good"] = WellBehavedPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_response("req", "resp", {}))
        assert WellBehavedPlugin.calls == ["before_response"]

    def test_failing_after_response_does_not_break_others(self):
        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        registry._plugins["good"] = WellBehavedPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_after_response("req", "resp", {}))
        assert WellBehavedPlugin.calls == ["after_response"]

    def test_failing_before_request_does_not_break_others(self):
        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        registry._plugins["good"] = WellBehavedPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_request("req", {}))
        assert WellBehavedPlugin.calls == ["before_request"]

    def test_failing_on_error_does_not_propagate(self):
        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_on_error("req", ValueError("original"), {}))
        assert True

    def test_multiple_failing_plugins_isolated(self):
        calls = []

        class GoodPlugin(AIPlugin):
            name = "good"
            async def before_route(self, request, context):
                calls.append("good")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["fail1"] = FailingPlugin()
        registry._plugins["good"] = GoodPlugin()
        registry._plugins["fail2"] = FailingPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_route("req", {}))
        assert calls == ["good"]

    def test_hook_result_unaffected_by_errors(self):
        class MetaPlugin(AIPlugin):
            name = "meta"
            async def before_route(self, request, context):
                return HookResult(metadata={"survived": True})

        registry = PluginRegistry()
        registry._plugins["failing"] = FailingPlugin()
        registry._plugins["meta"] = MetaPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_route("req", {}))
        assert result.metadata == {"survived": True}

    def test_plugin_error_does_not_crash_pipeline(self):
        class ExplodingPlugin(AIPlugin):
            name = "explode"
            async def before_route(self, request, context):
                raise SystemError("catastrophic")

        registry = PluginRegistry()
        registry._plugins["explode"] = ExplodingPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_route("req", {}))
        assert result.should_cancel is False
