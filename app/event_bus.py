from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Any]


class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)
        self._history: list[dict[str, Any]] = []
        self._max_history: int = 1000

    def subscribe(self, event: str, handler: EventHandler) -> None:
        if handler not in self._subscribers[event]:
            self._subscribers[event].append(handler)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        if handler in self._subscribers.get(event, []):
            self._subscribers[event].remove(handler)

    async def emit(self, event: str, **kwargs: Any) -> list[Any]:
        results: list[Any] = []
        self._history.append({"event": event, "data": kwargs})
        if len(self._history) > self._max_history:
            self._history.pop(0)

        for handler in self._subscribers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**kwargs)
                else:
                    result = handler(**kwargs)
                results.append(result)
            except Exception as e:
                logger.exception(f"Event handler error for {event}: {e}")
        return results

    def subscribers(self, event: str) -> list[EventHandler]:
        return list(self._subscribers.get(event, []))

    def clear(self) -> None:
        self._subscribers.clear()
        self._history.clear()

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._history[-limit:])

    def event_names(self) -> list[str]:
        return list(self._subscribers.keys())


event_bus = EventBus()
