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
