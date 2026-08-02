"""Advanced tests for plugin hot-reload system."""

import os
import time
from pathlib import Path

import pytest

from app.plugin.base import AIPlugin, HookResult
from app.plugin.registry import PluginRegistry
from app.plugin.watcher import PluginWatcher


def _touch(path: Path) -> None:
    path.touch(exist_ok=True)
    time.sleep(0.05)


class TestHotReloadAdvanced:
    def test_watcher_detects_new_plugin_dir(self, tmp_path):
        registry = PluginRegistry()
        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)

        watcher._scan_once()

        plugin_dir = tmp_path / "new_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text(
            "name: new_plugin\nversion: 1.0.0\ndescription: ''\nevents: []\nhooks: []\n"
        )
        (plugin_dir / "plugin.py").write_text(
            "from app.plugin.base import AIPlugin\nclass NewPlugin(AIPlugin):\n    name = 'new_plugin'\n"
        )

        time.sleep(0.05)
        changes = watcher._detect_changes()
        assert "new_plugin" in changes

    def test_watcher_detects_modified_manifest(self, tmp_path):
        registry = PluginRegistry()
        plugin_dir = tmp_path / "test_mod"
        plugin_dir.mkdir()
        manifest_file = plugin_dir / "manifest.yaml"
        manifest_file.write_text("name: test_mod\nversion: 1.0.0\ndescription: v1\n")
        plugin_file = plugin_dir / "plugin.py"
        plugin_file.write_text(
            "from app.plugin.base import AIPlugin\nclass TestPlugin(AIPlugin):\n    name = 'test_mod'\n"
        )

        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)
        watcher._scan_once()

        time.sleep(0.05)
        manifest_file.write_text("name: test_mod\nversion: 2.0.0\ndescription: v2\n")
        time.sleep(0.05)

        changes = watcher._detect_changes()
        assert "test_mod" in changes

    def test_watcher_detects_deleted_plugin(self, tmp_path):
        registry = PluginRegistry()
        plugin_dir = tmp_path / "delete_me"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text("name: delete_me\nversion: 1.0.0\n")
        (plugin_dir / "plugin.py").write_text(
            "from app.plugin.base import AIPlugin\nclass DelPlugin(AIPlugin):\n    name = 'delete_me'\n"
        )

        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)
        watcher._scan_once()

        import shutil
        shutil.rmtree(plugin_dir)

        changes = watcher._detect_changes()
        assert "delete_me" in changes

    def test_watcher_detects_no_changes_with_unchanged_files(self, tmp_path):
        registry = PluginRegistry()
        plugin_dir = tmp_path / "stable"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text("name: stable\nversion: 1.0.0\n")
        (plugin_dir / "plugin.py").write_text(
            "from app.plugin.base import AIPlugin\nclass StablePlugin(AIPlugin):\n    name = 'stable'\n"
        )

        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)
        watcher._scan_once()

        time.sleep(0.05)
        changes = watcher._detect_changes()
        assert changes == []

    def test_watcher_multiple_plugin_changes(self, tmp_path):
        registry = PluginRegistry()
        p1 = tmp_path / "plugin_a"
        p2 = tmp_path / "plugin_b"
        p1.mkdir()
        p2.mkdir()
        for p in [p1, p2]:
            (p / "manifest.yaml").write_text(f"name: {p.name}\nversion: 1.0.0\n")
            (p / "plugin.py").write_text(
                f"from app.plugin.base import AIPlugin\nclass P(AIPlugin):\n    name = '{p.name}'\n"
            )

        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)
        watcher._scan_once()

        time.sleep(0.05)
        (p1 / "plugin.py").write_text(
            "from app.plugin.base import AIPlugin\nclass P(AIPlugin):\n    name = 'plugin_a_v2'\n"
        )
        (p2 / "manifest.yaml").write_text("name: plugin_b\nversion: 2.0.0\n")
        time.sleep(0.05)

        changes = watcher._detect_changes()
        assert "plugin_a" in changes
        assert "plugin_b" in changes

    def test_watcher_discover_and_load_on_change(self, tmp_path):
        registry = PluginRegistry()
        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)
        watcher._scan_once()

        plugin_dir = tmp_path / "auto_load"
        plugin_dir.mkdir()
        _touch(plugin_dir / "manifest.yaml")
        (plugin_dir / "manifest.yaml").write_text(
            "name: auto_load\nversion: 1.0.0\ndescription: ''\nevents: []\nhooks: []\n"
        )
        _touch(plugin_dir / "plugin.py")
        (plugin_dir / "plugin.py").write_text(
            "from app.plugin.base import AIPlugin\nclass AutoLoad(AIPlugin):\n    name = 'auto_load'\n"
        )
        _touch(plugin_dir / "plugin.py")

        changes = watcher._detect_changes()
        assert "auto_load" in changes

    def test_watcher_ignores_non_plugin_files(self, tmp_path):
        registry = PluginRegistry()
        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)

        (tmp_path / "not_a_plugin.txt").write_text("not a plugin")
        (tmp_path / "README.md").write_text("# readme")
        os.makedirs(tmp_path / "__pycache__", exist_ok=True)

        watcher._scan_once()
        assert len(watcher._known) == 0

    def test_watcher_handles_invalid_plugin_gracefully(self, tmp_path):
        registry = PluginRegistry()
        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)

        plugin_dir = tmp_path / "broken"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text("not: valid: yaml: [[[")
        (plugin_dir / "plugin.py").write_text("this is not valid python {{{")

        watcher._scan_once()
        assert "broken" in watcher._known

    def test_watcher_restart(self, tmp_path):
        registry = PluginRegistry()
        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)

        watcher.start()
        assert watcher.is_running is True
        watcher.stop()
        assert watcher.is_running is False
        watcher.start()
        assert watcher.is_running is True
        watcher.stop()

    def test_watcher_stop_without_start(self):
        registry = PluginRegistry()
        watcher = PluginWatcher(registry)
        watcher.stop()

    def test_watcher_nonexistent_dir_no_error(self):
        registry = PluginRegistry()
        watcher = PluginWatcher(registry, plugin_dir="/definitely/does/not/exist")
        watcher._scan_once()
        changes = watcher._detect_changes()
        assert changes == []

    def test_watcher_reloads_plugin_registry(self, tmp_path):
        registry = PluginRegistry()
        watcher = PluginWatcher(registry, plugin_dir=str(tmp_path), interval=0.1)
        watcher._scan_once()

        plugin_dir = tmp_path / "reload_test"
        plugin_dir.mkdir()
        _touch(plugin_dir / "manifest.yaml")
        (plugin_dir / "manifest.yaml").write_text(
            "name: reload_test\nversion: 1.0.0\ndescription: ''\nevents: []\nhooks: []\n"
        )
        _touch(plugin_dir / "plugin.py")
        (plugin_dir / "plugin.py").write_text(
            "from app.plugin.base import AIPlugin\nclass ReloadPlugin(AIPlugin):\n    name = 'reload_test'\n"
        )
        _touch(plugin_dir / "plugin.py")

        changes = watcher._detect_changes()
        assert "reload_test" in changes

        loaded = registry.discover_and_load()
        assert registry.get("logging") is not None
        assert "logging" in loaded
