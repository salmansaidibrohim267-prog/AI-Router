from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from app.plugin.registry import PluginRegistry


class PluginWatcher:
    def __init__(
        self,
        registry: PluginRegistry,
        plugin_dir: str = "plugins",
        interval: float = 5.0,
    ):
        self._registry = registry
        self._plugin_dir = Path(plugin_dir)
        self._interval = interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._known: dict[str, float] = {}

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._scan_once()
        self._thread = threading.Thread(target=self._run, daemon=True, name="plugin-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _scan_once(self) -> None:
        if not self._plugin_dir.is_dir():
            return
        for entry in self._plugin_dir.iterdir():
            if entry.is_dir():
                manifest = entry / "manifest.yaml"
                plugin_file = entry / "plugin.py"
                if manifest.exists() and plugin_file.exists():
                    mtime = max(
                        os.path.getmtime(manifest),
                        os.path.getmtime(plugin_file),
                    )
                    self._known[entry.name] = mtime

    def _detect_changes(self) -> list[str]:
        if not self._plugin_dir.is_dir():
            return []
        changes: list[str] = []
        current: dict[str, float] = {}
        for entry in self._plugin_dir.iterdir():
            if entry.is_dir():
                manifest = entry / "manifest.yaml"
                plugin_file = entry / "plugin.py"
                if manifest.exists() and plugin_file.exists():
                    mtime = max(
                        os.path.getmtime(manifest),
                        os.path.getmtime(plugin_file),
                    )
                    current[entry.name] = mtime
                    old = self._known.get(entry.name)
                    if old is None or mtime > old:
                        changes.append(entry.name)
        # Detect removed plugins
        for name in self._known:
            if name not in current:
                changes.append(name)
        self._known = current
        return changes

    def _run(self) -> None:
        while self._running:
            try:
                changes = self._detect_changes()
                if changes:
                    self._registry.discover_and_load()
            except Exception:
                pass
            time.sleep(self._interval)

    @property
    def is_running(self) -> bool:
        return self._running
