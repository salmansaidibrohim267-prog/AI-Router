"""Tests for middleware hook ordering and execution sequence."""

import asyncio

import pytest

from app.plugin.base import AIPlugin, HookResult
from app.plugin.pipeline import MiddlewarePipeline
from app.plugin.registry import PluginRegistry


class TestHookOrdering:
    def test_hooks_execute_in_registration_order(self):
        order = []

        class PluginA(AIPlugin):
            name = "a"
            async def before_route(self, request, context):
                order.append("a")
                return HookResult()

        class PluginB(AIPlugin):
            name = "b"
            async def before_route(self, request, context):
                order.append("b")
                return HookResult()

        class PluginC(AIPlugin):
            name = "c"
            async def before_route(self, request, context):
                order.append("c")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["a"] = PluginA()
        registry._plugins["b"] = PluginB()
        registry._plugins["c"] = PluginC()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_route("req", {}))
        assert order == ["a", "b", "c"]

    def test_before_route_then_after_route_ordering(self):
        order = []

        class TrackPlugin(AIPlugin):
            name = "track"
            async def before_route(self, request, context):
                order.append("before_route")
                return HookResult()
            async def after_route(self, request, context, routes):
                order.append("after_route")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["track"] = TrackPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_route("req", {}))
        asyncio.run(pipeline.execute_after_route("req", {}, []))
        assert order == ["before_route", "after_route"]

    def test_provider_hook_ordering(self):
        order = []

        class TrackPlugin(AIPlugin):
            name = "track"
            async def before_provider(self, request, provider_name, model, context):
                order.append("before_provider")
                return HookResult()
            async def after_provider(self, request, response, provider_name, model, context):
                order.append("after_provider")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["track"] = TrackPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_provider("req", "p", "m", {}))
        asyncio.run(pipeline.execute_after_provider("req", "resp", "p", "m", {}))
        assert order == ["before_provider", "after_provider"]

    def test_all_hook_types_ordered_correctly(self):
        order = []

        class FullPlugin(AIPlugin):
            name = "full"
            async def before_request(self, request, context):
                order.append("before_request")
                return HookResult()
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

        registry = PluginRegistry()
        registry._plugins["full"] = FullPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_request("req", {}))
        asyncio.run(pipeline.execute_before_route("req", {}))
        asyncio.run(pipeline.execute_after_route("req", {}, [("p", "m")]))
        asyncio.run(pipeline.execute_before_provider("req", "p", "m", {}))
        asyncio.run(pipeline.execute_after_provider("req", "resp", "p", "m", {}))
        asyncio.run(pipeline.execute_before_response("req", "resp", {}))
        asyncio.run(pipeline.execute_after_response("req", "resp", {}))

        assert order == [
            "before_request",
            "before_route",
            "after_route",
            "before_provider",
            "after_provider",
            "before_response",
            "after_response",
        ]


class TestHookCancellation:
    def test_before_route_cancels_before_provider(self):
        order = []

        class BlockPlugin(AIPlugin):
            name = "block"
            async def before_route(self, request, context):
                order.append("blocked")
                return HookResult(should_cancel=True, cancel_reason="stop")
            async def before_provider(self, request, provider_name, model, context):
                order.append("should_not_run")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["block"] = BlockPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_route("req", {}))
        assert result.should_cancel is True

    def test_cancel_does_not_affect_other_plugins_same_hook(self):
        order = []

        class BlockPlugin(AIPlugin):
            name = "block"
            async def before_route(self, request, context):
                order.append("block")
                return HookResult(should_cancel=True, cancel_reason="stop")

        class AfterPlugin(AIPlugin):
            name = "after"
            async def before_route(self, request, context):
                order.append("after")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["block"] = BlockPlugin()
        registry._plugins["after"] = AfterPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_route("req", {}))
        assert result.should_cancel is True
        assert order == ["block"]

    def test_cancel_in_before_provider_stops_request(self):
        class CancelPlugin(AIPlugin):
            name = "cancel"
            async def before_provider(self, request, provider_name, model, context):
                return HookResult(should_cancel=True, cancel_reason="provider blocked")

        registry = PluginRegistry()
        registry._plugins["cancel"] = CancelPlugin()
        pipeline = MiddlewarePipeline(registry)

        result = asyncio.run(pipeline.execute_before_provider("req", "openai", "gpt-4", {}))
        assert result.should_cancel is True
        assert result.cancel_reason == "provider blocked"


class TestHookModifications:
    def test_request_modification_chain(self):
        class ModPlugin(AIPlugin):
            name = "mod"
            async def before_route(self, request, context):
                return HookResult(modified_request={"step": "route"})
            async def before_provider(self, request, provider_name, model, context):
                return HookResult(modified_request={"step": "provider"})

        registry = PluginRegistry()
        registry._plugins["mod"] = ModPlugin()
        pipeline = MiddlewarePipeline(registry)

        br = asyncio.run(pipeline.execute_before_route("req", {}))
        assert br.modified_request == {"step": "route"}

        bp = asyncio.run(pipeline.execute_before_provider("req", "p", "m", {}))
        assert bp.modified_request == {"step": "provider"}

    def test_response_modification_chain(self):
        class ModPlugin(AIPlugin):
            name = "mod"
            async def after_provider(self, request, response, provider_name, model, context):
                return HookResult(modified_response={"stage": "provider"})
            async def before_response(self, request, response, context):
                return HookResult(modified_response={"stage": "final"})

        registry = PluginRegistry()
        registry._plugins["mod"] = ModPlugin()
        pipeline = MiddlewarePipeline(registry)

        ap = asyncio.run(pipeline.execute_after_provider("req", {}, "p", "m", {}))
        assert ap.modified_response == {"stage": "provider"}

        br = asyncio.run(pipeline.execute_before_response("req", {}, {}))
        assert br.modified_response == {"stage": "final"}


class TestBackwardCompatibility:
    def test_old_before_request_still_works(self):
        results = []

        class LegacyPlugin(AIPlugin):
            name = "legacy"
            async def before_request(self, request, context):
                results.append("legacy_before_request")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["legacy"] = LegacyPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_request("req", {}))
        assert results == ["legacy_before_request"]

    def test_old_after_response_still_works(self):
        results = []

        class LegacyPlugin(AIPlugin):
            name = "legacy"
            async def after_response(self, request, response, context):
                results.append("legacy_after_response")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["legacy"] = LegacyPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_after_response("req", "resp", {}))
        assert results == ["legacy_after_response"]

    def test_both_old_and_new_hooks_run(self):
        results = []

        class HybridPlugin(AIPlugin):
            name = "hybrid"
            async def before_request(self, request, context):
                results.append("old")
                return HookResult()
            async def before_route(self, request, context):
                results.append("new")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["hybrid"] = HybridPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_request("req", {}))
        asyncio.run(pipeline.execute_before_route("req", {}))
        assert results == ["old", "new"]

    def test_plugin_with_only_new_hooks(self):
        results = []

        class NewPlugin(AIPlugin):
            name = "new"
            async def before_route(self, request, context):
                results.append("new_only")
                return HookResult()

        registry = PluginRegistry()
        registry._plugins["new"] = NewPlugin()
        pipeline = MiddlewarePipeline(registry)

        asyncio.run(pipeline.execute_before_route("req", {}))
        assert results == ["new_only"]
