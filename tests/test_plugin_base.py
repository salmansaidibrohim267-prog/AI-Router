"""Tests for the AIPlugin base class and HookResult."""

import pytest

from app.plugin.base import AIPlugin, HookResult


class TestHookResult:
    def test_defaults(self):
        r = HookResult()
        assert r.should_cancel is False
        assert r.cancel_reason == ""
        assert r.modified_request is None
        assert r.modified_response is None
        assert r.metadata == {}

    def test_with_cancel(self):
        r = HookResult(should_cancel=True, cancel_reason="rate limited")
        assert r.should_cancel is True
        assert r.cancel_reason == "rate limited"

    def test_with_modifications(self):
        r = HookResult(modified_request={"key": "value"}, metadata={"plugin": "test"})
        assert r.modified_request == {"key": "value"}
        assert r.metadata == {"plugin": "test"}


class TestAIPlugin:
    def test_default_attributes(self):
        p = AIPlugin()
        assert p.name == "base"
        assert p.version == "0.1.0"
        assert p.description == ""

    def test_initialize_default(self):
        p = AIPlugin()
        result = p.initialize()
        import asyncio
        if asyncio.iscoroutine(result):
            import asyncio
            asyncio.run(result)

    def test_before_request_default(self):
        p = AIPlugin()
        import asyncio
        result = asyncio.run(p.before_request(None, {}))
        assert isinstance(result, HookResult)
        assert result.should_cancel is False

    def test_after_response_default(self):
        p = AIPlugin()
        import asyncio
        result = asyncio.run(p.after_response(None, None, {}))
        assert isinstance(result, HookResult)

    def test_on_error_default(self):
        p = AIPlugin()
        import asyncio
        result = asyncio.run(p.on_error(None, Exception("test"), {}))
        assert isinstance(result, HookResult)

    def test_shutdown_default(self):
        p = AIPlugin()
        result = p.shutdown()
        import asyncio
        if asyncio.iscoroutine(result):
            asyncio.run(result)

    def test_repr(self):
        p = AIPlugin()
        assert repr(p) == "<AIPlugin name=base v0.1.0>"

    def test_custom_plugin(self):
        class MyPlugin(AIPlugin):
            name = "my"
            version = "2.0.0"
            description = "My custom plugin"

        p = MyPlugin()
        assert p.name == "my"
        assert p.version == "2.0.0"
        assert p.description == "My custom plugin"
        assert repr(p) == "<MyPlugin name=my v2.0.0>"

    def test_before_request_cancels(self):
        class BlockPlugin(AIPlugin):
            async def before_request(self, request, context):
                return HookResult(should_cancel=True, cancel_reason="blocked")

        p = BlockPlugin()
        import asyncio
        result = asyncio.run(p.before_request(None, {}))
        assert result.should_cancel is True
        assert result.cancel_reason == "blocked"

    def test_after_response_modifies(self):
        class ModPlugin(AIPlugin):
            async def after_response(self, request, response, context):
                return HookResult(modified_response={"modified": True})

        p = ModPlugin()
        import asyncio
        result = asyncio.run(p.after_response(None, None, {}))
        assert result.modified_response == {"modified": True}

    def test_before_route_default(self):
        p = AIPlugin()
        import asyncio
        result = asyncio.run(p.before_route(None, {}))
        assert isinstance(result, HookResult)
        assert result.should_cancel is False

    def test_after_route_default(self):
        p = AIPlugin()
        import asyncio
        result = asyncio.run(p.after_route(None, {}, []))
        assert isinstance(result, HookResult)
        assert result.should_cancel is False

    def test_before_provider_default(self):
        p = AIPlugin()
        import asyncio
        result = asyncio.run(p.before_provider(None, "p", "m", {}))
        assert isinstance(result, HookResult)
        assert result.should_cancel is False

    def test_after_provider_default(self):
        p = AIPlugin()
        import asyncio
        result = asyncio.run(p.after_provider(None, None, "p", "m", {}))
        assert isinstance(result, HookResult)
        assert result.should_cancel is False

    def test_before_response_default(self):
        p = AIPlugin()
        import asyncio
        result = asyncio.run(p.before_response(None, None, {}))
        assert isinstance(result, HookResult)
        assert result.should_cancel is False

    def test_plugin_enabled_default(self):
        p = AIPlugin()
        assert p._plugin_enabled is True

    def test_before_route_cancels(self):
        class BlockPlugin(AIPlugin):
            async def before_route(self, request, context):
                return HookResult(should_cancel=True, cancel_reason="blocked route")

        p = BlockPlugin()
        import asyncio
        result = asyncio.run(p.before_route(None, {}))
        assert result.should_cancel is True
        assert result.cancel_reason == "blocked route"

    def test_before_provider_injects_metadata(self):
        class MetaPlugin(AIPlugin):
            async def before_provider(self, request, provider_name, model, context):
                return HookResult(metadata={"p": provider_name, "m": model})

        p = MetaPlugin()
        import asyncio
        result = asyncio.run(p.before_provider(None, "openai", "gpt-4", {}))
        assert result.metadata == {"p": "openai", "m": "gpt-4"}

    def test_after_route_receives_routes(self):
        received = []
        class RoutePlugin(AIPlugin):
            async def after_route(self, request, context, routes):
                received.extend(routes)
                return HookResult()

        p = RoutePlugin()
        import asyncio
        asyncio.run(p.after_route(None, {}, [("a", "b")]))
        assert received == [("a", "b")]

    def test_before_response_modifies(self):
        class ModPlugin(AIPlugin):
            async def before_response(self, request, response, context):
                return HookResult(modified_response="modified!")

        p = ModPlugin()
        import asyncio
        result = asyncio.run(p.before_response(None, None, {}))
        assert result.modified_response == "modified!"
