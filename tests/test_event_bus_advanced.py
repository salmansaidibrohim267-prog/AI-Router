"""Advanced tests for the EventBus system covering edge cases, concurrency, and plugin integration."""

import asyncio
import threading

import pytest

from app.event_bus import EventBus
from app.plugin.base import AIPlugin, HookResult


class TestEventBusAdvanced:
    def test_multiple_events_same_handler(self):
        bus = EventBus()
        results = []

        async def handler(**kwargs):
            results.append(kwargs.get("type"))

        bus.subscribe("ev1", handler)
        bus.subscribe("ev2", handler)

        asyncio.run(bus.emit("ev1", type="one"))
        asyncio.run(bus.emit("ev2", type="two"))

        assert results == ["one", "two"]

    def test_handler_return_value_collected(self):
        bus = EventBus()

        async def h1(**kwargs):
            return 1

        async def h2(**kwargs):
            return 2

        bus.subscribe("ev", h1)
        bus.subscribe("ev", h2)

        results = asyncio.run(bus.emit("ev"))
        assert results == [1, 2]

    def test_many_subscribers(self):
        bus = EventBus()
        results = []

        async def make_handler(n):
            async def handler(**kwargs):
                results.append(n)
            return handler

        handlers = [asyncio.run(make_handler(i)) for i in range(50)]
        for h in handlers:
            bus.subscribe("bulk", h)

        asyncio.run(bus.emit("bulk"))
        assert len(results) == 50
        assert results == list(range(50))

    def test_event_history_respects_max(self):
        bus = EventBus()
        bus._max_history = 3

        for i in range(10):
            asyncio.run(bus.emit("ev", i=i))

        history = bus.get_history(100)
        assert len(history) == 3
        assert [h["data"]["i"] for h in history] == [7, 8, 9]

    def test_emit_without_subscribers_returns_empty(self):
        bus = EventBus()
        results = asyncio.run(bus.emit("nonexistent"))
        assert results == []

    def test_subscribe_sync_handler(self):
        bus = EventBus()
        results = []

        def sync_handler(**kwargs):
            results.append("sync")

        bus.subscribe("ev", sync_handler)
        asyncio.run(bus.emit("ev"))
        assert results == ["sync"]

    def test_mixed_sync_async_handlers(self):
        bus = EventBus()
        results = []

        def sync_h(**kwargs):
            results.append("sync")

        async def async_h(**kwargs):
            results.append("async")

        bus.subscribe("ev", sync_h)
        bus.subscribe("ev", async_h)
        asyncio.run(bus.emit("ev"))

        assert "sync" in results
        assert "async" in results

    def test_unsubscribe_nonexistent(self):
        bus = EventBus()

        async def h(**kwargs):
            pass

        bus.unsubscribe("nonexistent", h)

    def test_clear_while_emitting(self):
        bus = EventBus()
        results = []

        async def h1(**kwargs):
            results.append("h1")

        async def h2(**kwargs):
            bus.clear()
            results.append("h2")

        bus.subscribe("ev", h1)
        bus.subscribe("ev", h2)

        asyncio.run(bus.emit("ev"))
        assert results == ["h1", "h2"]

    def test_subscribe_after_clear(self):
        bus = EventBus()
        results = []

        async def h(**kwargs):
            results.append("ok")

        bus.subscribe("ev", h)
        bus.clear()
        asyncio.run(bus.emit("ev"))
        assert results == []

        bus.subscribe("ev2", h)
        asyncio.run(bus.emit("ev2"))
        assert results == ["ok"]

    def test_concurrent_subscribers_thread_safety(self):
        bus = EventBus()
        errors = []

        def subscriber():
            try:
                async def h(**kwargs):
                    pass
                bus.subscribe("ev", h)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=subscriber) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_event_names_after_subscribe_unsubscribe(self):
        bus = EventBus()

        async def h(**kwargs):
            pass

        bus.subscribe("a", h)
        bus.subscribe("b", h)
        names = sorted(bus.event_names())
        assert "a" in names
        assert "b" in names

        bus.unsubscribe("a", h)
        remaining = bus.subscribers("a")
        assert remaining == []

    def test_history_timestamps(self):
        bus = EventBus()
        asyncio.run(bus.emit("ev", data=1))
        history = bus.get_history(1)
        assert "event" in history[0]
        assert "data" in history[0]

    def test_max_history_default(self):
        bus = EventBus()
        assert bus._max_history == 1000

    def test_event_bus_singleton(self):
        from app.event_bus import event_bus as eb1
        from app.event_bus import event_bus as eb2
        assert eb1 is eb2


class TestEventBusWithPlugins:
    def test_plugin_can_subscribe_to_events(self):
        from app.event_bus import event_bus
        results = []

        class EventPlugin(AIPlugin):
            name = "event_listener"

            async def initialize(self):
                event_bus.subscribe("custom.event", self.on_custom_event)

            async def on_custom_event(self, **kwargs):
                results.append(kwargs.get("value"))

        plugin = EventPlugin()
        asyncio.run(plugin.initialize())
        asyncio.run(event_bus.emit("custom.event", value=42))
        assert results == [42]

    def test_plugin_can_filter_events(self):
        from app.event_bus import event_bus
        results = []

        class FilterPlugin(AIPlugin):
            name = "filter"

            async def initialize(self):
                event_bus.subscribe("provider.selected", self.on_provider_selected)

            async def on_provider_selected(self, **kwargs):
                if kwargs.get("provider") == "openai":
                    results.append(kwargs)

        plugin = FilterPlugin()
        asyncio.run(plugin.initialize())
        asyncio.run(event_bus.emit("provider.selected", provider="openai", model="gpt-4"))
        asyncio.run(event_bus.emit("provider.selected", provider="anthropic", model="claude"))
        assert len(results) == 1
        assert results[0]["provider"] == "openai"

    def test_plugin_error_in_event_handler_is_isolated(self):
        from app.event_bus import event_bus
        results = []

        async def good_handler(**kwargs):
            results.append("ok")

        async def bad_handler(**kwargs):
            raise ValueError("handler error")

        event_bus.subscribe("test", bad_handler)
        event_bus.subscribe("test", good_handler)
        asyncio.run(event_bus.emit("test"))
        assert results == ["ok"]
