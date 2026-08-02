from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from .exceptions import PluginError
from .logging import PluginLogger


@dataclass
class HookResult:
    should_cancel: bool = False
    cancel_reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_cancel": self.should_cancel,
            "cancel_reason": self.cancel_reason,
            "payload": self.payload,
        }


class HookSystem:
    """Registry and dispatcher for platform hook points (Observer pattern).

    Listeners may be sync callables or coroutines; exceptions raised by a
    listener are captured (never propagated) so one bad plugin cannot break
    the chain. A listener returning ``HookResult(should_cancel=True)`` stops
    the chain.
    """

    def __init__(self, logger: PluginLogger | None = None) -> None:
        self._logger = logger or PluginLogger()
        self._listeners: dict[str, list[tuple[str, Callable[..., Any]]]] = {}
        self._lock = threading.Lock()

    def register(self, hook_name: str, listener: Callable[..., Any], plugin: str = "") -> None:
        with self._lock:
            self._listeners.setdefault(hook_name, []).append((plugin, listener))

    def unregister(self, hook_name: str, listener: Callable[..., Any]) -> bool:
        with self._lock:
            listeners = self._listeners.get(hook_name, [])
            for index, (_, registered) in enumerate(listeners):
                if registered is listener:
                    del listeners[index]
                    return True
        return False

    def unregister_plugin(self, plugin: str) -> int:
        removed = 0
        with self._lock:
            for hook_name, listeners in list(self._listeners.items()):
                before = len(listeners)
                listeners[:] = [(name, fn) for name, fn in listeners if name != plugin]
                removed += before - len(listeners)
                if not listeners:
                    self._listeners.pop(hook_name, None)
        return removed

    def listeners(self, hook_name: str) -> list[tuple[str, Callable[..., Any]]]:
        with self._lock:
            return list(self._listeners.get(hook_name, []))

    def hook_names(self) -> list[str]:
        with self._lock:
            return list(self._listeners.keys())

    def has_listener(self, hook_name: str) -> bool:
        return bool(self.listeners(hook_name))

    async def dispatch(
        self,
        hook_name: str,
        *args: Any,
        context: dict[str, Any] | None = None,
        plugins: set[str] | None = None,
        **kwargs: Any,
    ) -> HookResult:
        result = HookResult()
        self._logger.log_event("hook.dispatched", hook=hook_name)
        for plugin, listener in self.listeners(hook_name):
            if plugins is not None and plugin and plugin not in plugins:
                continue
            try:
                if inspect.iscoroutinefunction(listener):
                    output = await listener(*args, **kwargs)
                else:
                    output = listener(*args, **kwargs)
                if isinstance(output, HookResult):
                    result.payload.update(output.payload)
                    if output.should_cancel:
                        result.should_cancel = True
                        result.cancel_reason = output.cancel_reason or f"cancelled by {plugin or 'listener'}"
                        break
            except Exception as exc:
                self._logger.log_event("hook.listener_error", hook=hook_name, plugin=plugin, error=str(exc))
        return result

    def dispatch_sync(self, hook_name: str, *args: Any, **kwargs: Any) -> HookResult:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            from threading import Thread

            holder: dict[str, HookResult] = {}

            def _dispatch_in_thread() -> None:
                holder["result"] = asyncio.run(self.dispatch(hook_name, *args, **kwargs))

            thread = Thread(target=_dispatch_in_thread, daemon=True)
            thread.start()
            thread.join()
            return holder["result"]
        return asyncio.run(self.dispatch(hook_name, *args, **kwargs))
