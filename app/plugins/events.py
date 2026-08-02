from __future__ import annotations

import asyncio
from typing import Any

from app.event_bus import EventBus, logger

PLUGIN_INSTALLED = "plugin.installed"
PLUGIN_UNINSTALLED = "plugin.uninstalled"
PLUGIN_ENABLED = "plugin.enabled"
PLUGIN_DISABLED = "plugin.disabled"
PLUGIN_RELOADED = "plugin.reloaded"
PLUGIN_UPGRADED = "plugin.upgraded"
PLUGIN_FAILED = "plugin.failed"
PLUGIN_VERIFIED = "plugin.verified"
PLUGIN_EVENT = "plugin.event"
HOOK_DISPATCHED = "hook.dispatched"


class PluginEventBus(EventBus):
    """Event bus for the plugin platform, built on the shared core EventBus.

    Adds plugin-scoped helpers so platform components can publish lifecycle
    events and plugins can listen for any platform event. ``emit`` is
    overridden as a synchronous dispatch so it can be called from both sync
    and async plugin code; coroutine handlers are awaited via ``asyncio.run``
    when no loop is running and scheduled on the running loop otherwise.
    """

    def emit(self, event: str, **data: Any) -> list[Any]:
        results: list[Any] = []
        self._history.append({"event": event, "data": data})
        if len(self._history) > self._max_history:
            self._history.pop(0)

        for handler in self._subscribers.get(event, []):
            try:
                result = handler(**data)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop is None:
                        results.append(asyncio.run(result))
                    else:
                        loop.create_task(result)
                else:
                    results.append(result)
            except Exception as exc:
                logger.exception(f"Event handler error for {event}: {exc}")
        return results

    def emit_plugin_event(self, event: str, plugin: str = "", **data: Any) -> list[Any]:
        payload = dict(data)
        if plugin:
            payload["plugin"] = plugin
        return self.emit(event, **payload)

    async def emit_plugin_event_async(self, event: str, plugin: str = "", **data: Any) -> list[Any]:
        return self.emit_plugin_event(event, plugin=plugin, **data)


def create_plugin_event_bus() -> PluginEventBus:
    return PluginEventBus()
