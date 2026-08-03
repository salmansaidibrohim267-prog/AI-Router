from __future__ import annotations

import threading
from typing import Any

from app.plugin.base import AIPlugin
from app.plugin.loader import PluginLoader, PluginManifest


class PluginRegistry:
    def __init__(self):
        self._plugins: dict[str, AIPlugin] = {}
        self._manifests: dict[str, PluginManifest] = {}
        self._disabled: set[str] = set()
        self._lock = threading.RLock()
        self._loader = PluginLoader()

    def discover_and_load(self) -> list[str]:
        with self._lock:
            loaded: list[str] = []
            for name, path in self._loader.discover():
                manifest = self._loader.load_manifest(path)
                plugin = self._loader.load_plugin(path)
                if plugin and manifest:
                    self._plugins[name] = plugin
                    self._manifests[name] = manifest
                    self._disabled.discard(name)
                    loaded.append(name)
            return loaded

    def get(self, name: str) -> AIPlugin | None:
        return self._plugins.get(name)

    def get_manifest(self, name: str) -> PluginManifest | None:
        return self._manifests.get(name)

    def get_all(self) -> dict[str, AIPlugin]:
        return dict(self._plugins)

    def get_enabled(self) -> list[AIPlugin]:
        return [p for name, p in self._plugins.items() if name not in self._disabled]

    def is_enabled(self, name: str) -> bool:
        return name in self._plugins and name not in self._disabled

    def enable(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        with self._lock:
            self._disabled.discard(name)
        return True

    def disable(self, name: str) -> bool:
        if name not in self._plugins:
            return False
        with self._lock:
            self._disabled.add(name)
        return True

    @property
    def disabled(self) -> set[str]:
        return set(self._disabled)

    @property
    def names(self) -> list[str]:
        return list(self._plugins.keys())

    @property
    def manifest(self) -> dict[str, Any]:
        return {name: m.to_dict() for name, m in self._manifests.items()}

    def get_report(self) -> dict[str, Any]:
        return {
            "total": len(self._plugins),
            "enabled": len(self.get_enabled()),
            "disabled": len(self._disabled),
            "plugins": {
                name: {
                    "name": name,
                    "version": self._manifests[name].version if name in self._manifests else "unknown",
                    "description": self._manifests[name].description if name in self._manifests else "",
                    "enabled": name not in self._disabled,
                    "events": self._manifests[name].events if name in self._manifests else [],
                    "hooks": self._manifests[name].hooks if name in self._manifests else [],
                }
                for name in self._plugins
            },
        }

    def shutdown_all(self) -> None:
        for plugin in self._plugins.values():
            try:
                import asyncio

                if asyncio.iscoroutinefunction(plugin.shutdown):
                    import asyncio

                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(plugin.shutdown())
                        else:
                            loop.run_until_complete(plugin.shutdown())
                    except RuntimeError:
                        pass
            except Exception:
                pass
