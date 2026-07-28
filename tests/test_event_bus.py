"""Tests for the EventBus system."""

import pytest

from app.event_bus import EventBus


class TestEventBus:
    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []

        async def handler(data):
            received.append(data)

        bus.subscribe("test.event", handler)
        import asyncio
        asyncio.run(bus.emit("test.event", data="hello"))

        assert len(received) == 1
        assert received[0] == "hello"

    def test_multiple_subscribers(self):
        bus = EventBus()
        results = []

        async def h1(**kwargs):
            results.append("h1")

        async def h2(**kwargs):
            results.append("h2")

        bus.subscribe("test.event", h1)
        bus.subscribe("test.event", h2)
        import asyncio
        asyncio.run(bus.emit("test.event"))

        assert results == ["h1", "h2"]

    def test_unsubscribe(self):
        bus = EventBus()
        results = []

        async def handler(**kwargs):
            results.append("called")

        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        import asyncio
        asyncio.run(bus.emit("test.event"))

        assert results == []

    def test_no_subscribers(self):
        bus = EventBus()
        import asyncio
        asyncio.run(bus.emit("nonexistent.event"))
        # Should not raise

    def test_error_isolation(self):
        bus = EventBus()
        results = []

        async def failing_handler(**kwargs):
            raise ValueError("oops")

        async def good_handler(**kwargs):
            results.append("ok")

        bus.subscribe("test.event", failing_handler)
        bus.subscribe("test.event", good_handler)
        import asyncio
        asyncio.run(bus.emit("test.event"))

        assert results == ["ok"]

    def test_sync_handler(self):
        bus = EventBus()
        results = []

        def sync_handler(**kwargs):
            results.append("sync")

        bus.subscribe("test.event", sync_handler)
        import asyncio
        asyncio.run(bus.emit("test.event"))

        assert results == ["sync"]

    def test_event_history(self):
        bus = EventBus()
        import asyncio
        asyncio.run(bus.emit("event1", foo=1))
        asyncio.run(bus.emit("event2", bar=2))

        history = bus.get_history(limit=10)
        assert len(history) == 2
        assert history[0]["event"] == "event1"
        assert history[0]["data"]["foo"] == 1
        assert history[1]["event"] == "event2"

    def test_history_limit(self):
        bus = EventBus()
        bus._max_history = 5
        import asyncio
        for i in range(10):
            asyncio.run(bus.emit("ev", i=i))

        assert len(bus.get_history(100)) == 5

    def test_event_names(self):
        bus = EventBus()

        async def h(**kwargs):
            pass

        bus.subscribe("a", h)
        bus.subscribe("b", h)
        assert sorted(bus.event_names()) == ["a", "b"]

    def test_clear(self):
        bus = EventBus()

        async def h(**kwargs):
            pass

        bus.subscribe("test", h)
        import asyncio
        asyncio.run(bus.emit("test"))
        bus.clear()
        assert bus.event_names() == []
        assert bus.get_history() == []

    def test_subscribers_list(self):
        bus = EventBus()

        async def h(**kwargs):
            pass

        bus.subscribe("test", h)
        subs = bus.subscribers("test")
        assert h in subs
        assert bus.subscribers("nonexistent") == []

    def test_double_subscribe(self):
        bus = EventBus()
        results = []

        async def h(**kwargs):
            results.append("x")

        bus.subscribe("test", h)
        bus.subscribe("test", h)  # Duplicate
        import asyncio
        asyncio.run(bus.emit("test"))

        assert results == ["x"]  # Called once

    def test_emit_returns_results(self):
        bus = EventBus()

        async def h(**kwargs):
            return 42

        bus.subscribe("test", h)
        import asyncio
        results = asyncio.run(bus.emit("test"))
        assert results == [42]
