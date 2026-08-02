"""Tests for the enhanced hook system (before_route, after_route, before_provider, after_provider, before_response)."""

import asyncio

import pytest

from app.plugin.base import AIPlugin, HookResult
from app.plugin.pipeline import MiddlewarePipeline
from app.plugin.registry import PluginRegistry


class TestBeforeRouteHook:
    def test_before_route_default(self):
        p = AIPlugin()
        result = asyncio.run(p.before_route(None, {}))
        assert isinstance(result, HookResult)
        assert result.should_cancel is False

    def test_before_route_cancels_request(self):
        class BlockPlugin(AIPlugin):
            async def before_route(self, request, context):
                return HookResult(should_cancel=True, cancel_reason="route blocked")

        p = BlockPlugin()
        result = asyncio.run(p.before_route(None, {}))
        assert result.should_cancel is True
        assert result.cancel_reason == "route blocked"

    def test_before_route_modifies_request(self):
        class ModPlugin(AIPlugin):
            async def before_route(self, request, context):
                return HookResult(modified_request={"modified": True})

        p = ModPlugin()
        result = asyncio.run(p.before_route(None, {}))
        assert result.modified_request == {"modified": True}

    def test_before_route_injects_metadata(self):
        class MetaPlugin(AIPlugin):
            async def before_route(self, request, context):
                return HookResult(metadata={"route_hint": "fastest"})

        p = MetaPlugin()
        result = asyncio.run(p.before_route(None, {}))
        assert result.metadata == {"route_hint": "fastest"}

    def test_before_route_pipeline_execution(self):
        results = []

        class TrackPlugin(AIPlugin):
            name = "tracker"
            async def before_route(self, request, context):
                results.append("called")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["tracker"] = TrackPlugin()
        pipeline = MiddlewarePipeline(registry)
        asyncio.run(pipeline.execute_before_route("req", {}))
        assert results == ["called"]

    def test_before_route_cancel_stops_chain(self):
        results = []

        class BlockPlugin(AIPlugin):
            name = "blocker"
            async def before_route(self, request, context):
                return HookResult(should_cancel=True, cancel_reason="nope")

        class OtherPlugin(AIPlugin):
            name = "other"
            async def before_route(self, request, context):
                results.append("should_not_run")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["blocker"] = BlockPlugin()
        registry._plugins["other"] = OtherPlugin()
        pipeline = MiddlewarePipeline(registry)
        result = asyncio.run(pipeline.execute_before_route("req", {}))
        assert result.should_cancel is True
        assert results == []


class TestAfterRouteHook:
    def test_after_route_default(self):
        p = AIPlugin()
        result = asyncio.run(p.after_route(None, {}, []))
        assert isinstance(result, HookResult)

    def test_after_route_receives_routes(self):
        received = []

        class RoutePlugin(AIPlugin):
            async def after_route(self, request, context, routes):
                received.extend(routes)
                return HookResult()

        p = RoutePlugin()
        routes = [("openai", "gpt-4o"), ("anthropic", "claude-3")]
        asyncio.run(p.after_route(None, {}, routes))
        assert received == routes

    def test_after_route_cancels(self):
        class CancelPlugin(AIPlugin):
            async def after_route(self, request, context, routes):
                return HookResult(should_cancel=True, cancel_reason="no routes")

        p = CancelPlugin()
        result = asyncio.run(p.after_route(None, {}, [("p", "m")]))
        assert result.should_cancel is True

    def test_after_route_metadata(self):
        class MetaPlugin(AIPlugin):
            async def after_route(self, request, context, routes):
                return HookResult(metadata={"route_count": len(routes)})

        p = MetaPlugin()
        result = asyncio.run(p.after_route(None, {}, [("a", "b"), ("c", "d")]))
        assert result.metadata == {"route_count": 2}

    def test_after_route_pipeline_execution(self):
        results = []

        class TrackPlugin(AIPlugin):
            name = "tracker"
            async def after_route(self, request, context, routes):
                results.append(routes)
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["tracker"] = TrackPlugin()
        pipeline = MiddlewarePipeline(registry)
        routes = [("p1", "m1")]
        asyncio.run(pipeline.execute_after_route("req", {}, routes))
        assert results == [routes]


class TestBeforeProviderHook:
    def test_before_provider_default(self):
        p = AIPlugin()
        result = asyncio.run(p.before_provider(None, "p", "m", {}))
        assert isinstance(result, HookResult)

    def test_before_provider_receives_names(self):
        received = {}

        class TrackPlugin(AIPlugin):
            async def before_provider(self, request, provider_name, model, context):
                received["provider"] = provider_name
                received["model"] = model
                return HookResult()

        p = TrackPlugin()
        asyncio.run(p.before_provider(None, "openai", "gpt-4", {}))
        assert received == {"provider": "openai", "model": "gpt-4"}

    def test_before_provider_cancels(self):
        class BlockPlugin(AIPlugin):
            async def before_provider(self, request, provider_name, model, context):
                return HookResult(should_cancel=True, cancel_reason="provider blocked")

        p = BlockPlugin()
        result = asyncio.run(p.before_provider(None, "openai", "gpt-4", {}))
        assert result.should_cancel is True

    def test_before_provider_modifies_request(self):
        class ModPlugin(AIPlugin):
            async def before_provider(self, request, provider_name, model, context):
                return HookResult(modified_request={"custom_param": 42})

        p = ModPlugin()
        result = asyncio.run(p.before_provider(None, "p", "m", {}))
        assert result.modified_request == {"custom_param": 42}

    def test_before_provider_injects_metadata(self):
        class MetaPlugin(AIPlugin):
            async def before_provider(self, request, provider_name, model, context):
                return HookResult(metadata={"provider_override": provider_name})

        p = MetaPlugin()
        result = asyncio.run(p.before_provider(None, "anthropic", "claude", {}))
        assert result.metadata == {"provider_override": "anthropic"}

    def test_before_provider_pipeline_execution(self):
        results = []

        class TrackPlugin(AIPlugin):
            name = "tracker"
            async def before_provider(self, request, provider_name, model, context):
                results.append((provider_name, model))
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["tracker"] = TrackPlugin()
        pipeline = MiddlewarePipeline(registry)
        asyncio.run(pipeline.execute_before_provider("req", "openai", "gpt-4", {}))
        assert results == [("openai", "gpt-4")]


class TestAfterProviderHook:
    def test_after_provider_default(self):
        p = AIPlugin()
        result = asyncio.run(p.after_provider(None, None, "p", "m", {}))
        assert isinstance(result, HookResult)

    def test_after_provider_receives_response(self):
        received = {}

        class TrackPlugin(AIPlugin):
            async def after_provider(self, request, response, provider_name, model, context):
                received["response"] = response
                received["provider"] = provider_name
                return HookResult()

        p = TrackPlugin()
        asyncio.run(p.after_provider(None, {"content": "hello"}, "p", "m", {}))
        assert received["response"] == {"content": "hello"}
        assert received["provider"] == "p"

    def test_after_provider_modifies_response(self):
        class ModPlugin(AIPlugin):
            async def after_provider(self, request, response, provider_name, model, context):
                return HookResult(modified_response={"augmented": True})

        p = ModPlugin()
        result = asyncio.run(p.after_provider(None, {}, "p", "m", {}))
        assert result.modified_response == {"augmented": True}

    def test_after_provider_metadata(self):
        class MetaPlugin(AIPlugin):
            async def after_provider(self, request, response, provider_name, model, context):
                return HookResult(metadata={"cost": 0.01})

        p = MetaPlugin()
        result = asyncio.run(p.after_provider(None, {}, "p", "m", {}))
        assert result.metadata == {"cost": 0.01}

    def test_after_provider_pipeline_execution(self):
        results = []

        class TrackPlugin(AIPlugin):
            name = "tracker"
            async def after_provider(self, request, response, provider_name, model, context):
                results.append(provider_name)
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["tracker"] = TrackPlugin()
        pipeline = MiddlewarePipeline(registry)
        asyncio.run(pipeline.execute_after_provider("req", "resp", "openai", "gpt-4", {}))
        assert results == ["openai"]


class TestBeforeResponseHook:
    def test_before_response_default(self):
        p = AIPlugin()
        result = asyncio.run(p.before_response(None, None, {}))
        assert isinstance(result, HookResult)

    def test_before_response_modifies_response(self):
        class ModPlugin(AIPlugin):
            async def before_response(self, request, response, context):
                return HookResult(modified_response={"final": True})

        p = ModPlugin()
        result = asyncio.run(p.before_response(None, {}, {}))
        assert result.modified_response == {"final": True}

    def test_before_response_cancels(self):
        class CancelPlugin(AIPlugin):
            async def before_response(self, request, response, context):
                return HookResult(should_cancel=True, cancel_reason="response blocked")

        p = CancelPlugin()
        result = asyncio.run(p.before_response(None, {}, {}))
        assert result.should_cancel is True

    def test_before_response_metadata(self):
        class MetaPlugin(AIPlugin):
            async def before_response(self, request, response, context):
                return HookResult(metadata={"response_size": len(str(response))})

        p = MetaPlugin()
        result = asyncio.run(p.before_response(None, {"text": "hi"}, {}))
        assert result.metadata == {"response_size": 14}

    def test_before_response_pipeline(self):
        results = []

        class TrackPlugin(AIPlugin):
            name = "tracker"
            async def before_response(self, request, response, context):
                results.append("called")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["tracker"] = TrackPlugin()
        pipeline = MiddlewarePipeline(registry)
        asyncio.run(pipeline.execute_before_response("req", "resp", {}))
        assert results == ["called"]


class TestHookPipelineIntegration:
    def test_full_hook_chain_defaults(self):
        registry = PluginRegistry()
        registry._plugins["default"] = AIPlugin()
        pipeline = MiddlewarePipeline(registry)

        br = asyncio.run(pipeline.execute_before_route("req", {}))
        assert br.should_cancel is False

        ar = asyncio.run(pipeline.execute_after_route("req", {}, [("p", "m")]))
        assert ar.should_cancel is False

        bp = asyncio.run(pipeline.execute_before_provider("req", "p", "m", {}))
        assert bp.should_cancel is False

        ap = asyncio.run(pipeline.execute_after_provider("req", "resp", "p", "m", {}))
        assert ap.should_cancel is False

        br2 = asyncio.run(pipeline.execute_before_response("req", "resp", {}))
        assert br2.should_cancel is False

    def test_hook_chain_with_custom_plugin(self):
        calls = []

        class FullPlugin(AIPlugin):
            name = "full"

            async def before_route(self, request, context):
                calls.append("before_route")
                return HookResult()

            async def after_route(self, request, context, routes):
                calls.append("after_route")
                return HookResult()

            async def before_provider(self, request, provider_name, model, context):
                calls.append("before_provider")
                return HookResult()

            async def after_provider(self, request, response, provider_name, model, context):
                calls.append("after_provider")
                return HookResult()

            async def before_response(self, request, response, context):
                calls.append("before_response")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["full"] = FullPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_route("req", {}))
        asyncio.run(pipeline.execute_after_route("req", {}, [("p", "m")]))
        asyncio.run(pipeline.execute_before_provider("req", "p", "m", {}))
        asyncio.run(pipeline.execute_after_provider("req", "resp", "p", "m", {}))
        asyncio.run(pipeline.execute_before_response("req", "resp", {}))

        assert calls == [
            "before_route",
            "after_route",
            "before_provider",
            "after_provider",
            "before_response",
        ]

    def test_disabled_plugin_does_not_run_hooks(self):
        results = []

        class DisabledPlugin(AIPlugin):
            name = "disabled_test"
            async def before_route(self, request, context):
                results.append("should_not_run")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["disabled_test"] = DisabledPlugin()
        registry.disable("disabled_test")
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_route("req", {}))
        assert results == []

    def test_metadata_aggregation_across_hooks(self):
        class PluginA(AIPlugin):
            name = "a"
            async def before_route(self, request, context):
                return HookResult(metadata={"from_a": "value_a"})

        class PluginB(AIPlugin):
            name = "b"
            async def before_route(self, request, context):
                return HookResult(metadata={"from_b": "value_b"})

        registry = PluginRegistry()
        registry._plugins["a"] = PluginA()
        registry._plugins["b"] = PluginB()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_route("req", {}))
        assert result.metadata == {"from_a": "value_a", "from_b": "value_b"}
