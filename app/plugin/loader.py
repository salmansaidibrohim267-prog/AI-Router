from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

from app.plugin.base import AIPlugin


class PluginManifest:
    def __init__(self, data: dict[str, Any]):
        self.name: str = data.get("name", "unknown")
        self.version: str = data.get("version", "0.1.0")
        self.description: str = data.get("description", "")
        self.author: str = data.get("author", "")
        self.tags: list[str] = data.get("tags", [])
        self.events: list[str] = data.get("events", [])
        self.hooks: list[str] = data.get("hooks", [])

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "events": self.events,
            "hooks": self.hooks,
        }


class PluginLoader:
    def __init__(self, plugin_dir: str = "plugins"):
        self._plugin_dir = Path(plugin_dir)

    def discover(self) -> list[tuple[str, Path]]:
        if not self._plugin_dir.is_dir():
            return []
        plugins: list[tuple[str, Path]] = []
        for entry in sorted(self._plugin_dir.iterdir()):
            if entry.is_dir():
                plugin_file = entry / "plugin.py"
                manifest_file = entry / "manifest.yaml"
                if plugin_file.exists() and manifest_file.exists():
                    plugins.append((entry.name, entry))
        return plugins

    def load_manifest(self, plugin_path: Path) -> PluginManifest | None:
        manifest_file = plugin_path / "manifest.yaml"
        if not manifest_file.exists():
            return None
        with open(manifest_file) as f:
            data = yaml.safe_load(f) or {}
        return PluginManifest(data)

    def load_plugin(self, plugin_path: Path) -> AIPlugin | None:
        plugin_file = plugin_path / "plugin.py"
        if not plugin_file.exists():
            return None

        module_name = f"_plugin_{plugin_path.name}"
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        if not spec or not spec.loader:
            return None

        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, AIPlugin) and attr is not AIPlugin:
                    instance = attr()
                    manifest = self.load_manifest(plugin_path)
                    if manifest:
                        instance.name = getattr(instance, "name", manifest.name)
                    return instance
        except Exception:
            import traceback

            traceback.print_exc()
        return None

    def load_all(self) -> list[AIPlugin]:
        plugins: list[AIPlugin] = []
        for _, path in self.discover():
            try:
                plugin = self.load_plugin(path)
                if plugin:
                    plugins.append(plugin)
            except Exception:
                import traceback

                traceback.print_exc()
        return plugins
