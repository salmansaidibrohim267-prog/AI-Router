"""Tests for the MiddlewarePipeline."""

import pytest

from app.plugin.base import AIPlugin, HookResult
from app.plugin.registry import PluginRegistry
from app.plugin.pipeline import MiddlewarePipeline


class TestMiddlewarePipeline:
    def test_execute_before_request_no_plugins(self):
        r = PluginRegistry()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_request("req", {}))
        assert isinstance(result, HookResult)
        assert result.should_cancel is False

    def test_execute_before_request_with_plugins(self):
        r = PluginRegistry()
        r.discover_and_load()
        p = MiddlewarePipeline(r)
        context = {}
        import asyncio
        result = asyncio.run(p.execute_before_request("req", context))
        assert isinstance(result, HookResult)
        assert context.get("example_plugin_ran") is True

    def test_execute_after_response(self):
        r = PluginRegistry()
        r.discover_and_load()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_after_response("req", "resp", {}))
        assert isinstance(result, HookResult)

    def test_execute_on_error(self):
        r = PluginRegistry()
        r.discover_and_load()
        p = MiddlewarePipeline(r)
        import asyncio
        asyncio.run(p.execute_on_error("req", Exception("test"), {}))
        # Should not raise

    def test_plugin_error_isolation(self):
        class FailingPlugin(AIPlugin):
            name = "failing"

            async def before_request(self, request, context):
                raise ValueError("plugin error")

        r = PluginRegistry()
        r._plugins["failing"] = FailingPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_request("req", {}))
        assert result.should_cancel is False

    def test_before_request_cancels_pipeline(self):
        class CancelPlugin(AIPlugin):
            name = "canceller"

            async def before_request(self, request, context):
                return HookResult(should_cancel=True, cancel_reason="denied")

        r = PluginRegistry()
        r._plugins["canceller"] = CancelPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_request("req", {}))
        assert result.should_cancel is True
        assert result.cancel_reason == "denied"

    def test_before_request_cancel_prevents_others(self):
        results = []

        class PluginA(AIPlugin):
            name = "a"
            async def before_request(self, request, context):
                return HookResult(should_cancel=True, cancel_reason="blocked")

        class PluginB(AIPlugin):
            name = "b"
            async def before_request(self, request, context):
                results.append("ran")
                return HookResult()

        r = PluginRegistry()
        r._plugins["a"] = PluginA()
        r._plugins["b"] = PluginB()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_request("req", {}))
        assert result.should_cancel is True
        assert results == []  # B never ran

    def test_after_response_modifies_aggregate(self):
        class ModPlugin(AIPlugin):
            name = "modder"

            async def after_response(self, request, response, context):
                return HookResult(modified_response="modified!")

        r = PluginRegistry()
        r._plugins["modder"] = ModPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_after_response("req", "orig", {}))
        assert result.modified_response == "modified!"

    def test_initialize_plugins(self):
        initialized = []

        class InitPlugin(AIPlugin):
            name = "init_test"
            async def initialize(self):
                initialized.append("ok")

        r = PluginRegistry()
        r._plugins["init_test"] = InitPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        asyncio.run(p.initialize_plugins())
        assert initialized == ["ok"]

    def test_shutdown_plugins(self):
        shutdown = []

        class ShutdownPlugin(AIPlugin):
            name = "shutdown_test"
            async def shutdown(self):
                shutdown.append("done")

        r = PluginRegistry()
        r._plugins["shutdown_test"] = ShutdownPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        asyncio.run(p.shutdown_plugins())
        assert shutdown == ["done"]

    def test_metadata_aggregation(self):
        class MetaPlugin(AIPlugin):
            name = "meta"

            async def before_request(self, request, context):
                return HookResult(metadata={"key1": "val1"})

        r = PluginRegistry()
        r._plugins["meta"] = MetaPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_request("req", {}))
        assert result.metadata == {"key1": "val1"}

    def test_execute_before_route(self):
        class TestPlugin(AIPlugin):
            name = "test"
            async def before_route(self, request, context):
                return HookResult(metadata={"route": True})

        r = PluginRegistry()
        r._plugins["test"] = TestPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_route("req", {}))
        assert result.metadata == {"route": True}

    def test_execute_after_route(self):
        class TestPlugin(AIPlugin):
            name = "test"
            async def after_route(self, request, context, routes):
                return HookResult(metadata={"count": len(routes)})

        r = PluginRegistry()
        r._plugins["test"] = TestPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_after_route("req", {}, [("a", "b")]))
        assert result.metadata == {"count": 1}

    def test_execute_before_provider(self):
        class TestPlugin(AIPlugin):
            name = "test"
            async def before_provider(self, request, provider_name, model, context):
                return HookResult(metadata={"provider": provider_name})

        r = PluginRegistry()
        r._plugins["test"] = TestPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_provider("req", "openai", "gpt-4", {}))
        assert result.metadata == {"provider": "openai"}

    def test_execute_after_provider(self):
        class TestPlugin(AIPlugin):
            name = "test"
            async def after_provider(self, request, response, provider_name, model, context):
                return HookResult(modified_response="augmented")

        r = PluginRegistry()
        r._plugins["test"] = TestPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_after_provider("req", "orig", "p", "m", {}))
        assert result.modified_response == "augmented"

    def test_execute_before_response(self):
        class TestPlugin(AIPlugin):
            name = "test"
            async def before_response(self, request, response, context):
                return HookResult(modified_response="final")

        r = PluginRegistry()
        r._plugins["test"] = TestPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_response("req", "resp", {}))
        assert result.modified_response == "final"

    def test_execute_before_route_cancels(self):
        class CancelPlugin(AIPlugin):
            name = "cancel"
            async def before_route(self, request, context):
                return HookResult(should_cancel=True, cancel_reason="no")

        r = PluginRegistry()
        r._plugins["cancel"] = CancelPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_route("req", {}))
        assert result.should_cancel is True

    def test_execute_after_route_with_empty_routes(self):
        class TestPlugin(AIPlugin):
            name = "test"
            async def after_route(self, request, context, routes):
                return HookResult(metadata={"empty": len(routes) == 0})

        r = PluginRegistry()
        r._plugins["test"] = TestPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_after_route("req", {}, []))
        assert result.metadata == {"empty": True}

    def test_execute_before_provider_cancels(self):
        class CancelPlugin(AIPlugin):
            name = "cancel"
            async def before_provider(self, request, provider_name, model, context):
                return HookResult(should_cancel=True, cancel_reason="blocked")

        r = PluginRegistry()
        r._plugins["cancel"] = CancelPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_provider("req", "p", "m", {}))
        assert result.should_cancel is True

    def test_execute_before_response_cancels(self):
        class CancelPlugin(AIPlugin):
            name = "cancel"
            async def before_response(self, request, response, context):
                return HookResult(should_cancel=True, cancel_reason="no response")

        r = PluginRegistry()
        r._plugins["cancel"] = CancelPlugin()
        p = MiddlewarePipeline(r)
        import asyncio
        result = asyncio.run(p.execute_before_response("req", "resp", {}))
        assert result.should_cancel is True

    def test_full_hook_chain_no_plugins(self):
        r = PluginRegistry()
        p = MiddlewarePipeline(r)
        import asyncio
        br = asyncio.run(p.execute_before_route("req", {}))
        assert br.should_cancel is False
        ar = asyncio.run(p.execute_after_route("req", {}, []))
        assert ar.should_cancel is False
        bp = asyncio.run(p.execute_before_provider("req", "p", "m", {}))
        assert bp.should_cancel is False
        ap = asyncio.run(p.execute_after_provider("req", "r", "p", "m", {}))
        assert ap.should_cancel is False
        br2 = asyncio.run(p.execute_before_response("req", "r", {}))
        assert br2.should_cancel is False
