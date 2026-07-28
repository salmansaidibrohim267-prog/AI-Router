"""Tests for the PluginWatcher hot reload system."""

import time
from pathlib import Path

import pytest

from app.plugin.registry import PluginRegistry
from app.plugin.watcher import PluginWatcher


class TestPluginWatcher:
    def test_watcher_initial_state(self):
        r = PluginRegistry()
        w = PluginWatcher(r)
        assert w.is_running is False

    def test_watcher_start_stop(self):
        r = PluginRegistry()
        w = PluginWatcher(r)
        w.start()
        assert w.is_running is True
        w.stop()
        assert w.is_running is False

    def test_watcher_start_twice(self):
        r = PluginRegistry()
        w = PluginWatcher(r)
        w.start()
        w.start()  # Should not raise
        w.stop()

    def test_watcher_detect_no_changes(self):
        r = PluginRegistry()
        w = PluginWatcher(r, interval=0.1)
        w._scan_once()
        changes = w._detect_changes()
        assert changes == []

    def test_watcher_detect_new_plugin(self, tmp_path):
        r = PluginRegistry()
        w = PluginWatcher(r, plugin_dir=str(tmp_path), interval=0.1)

        w._scan_once()

        # Create a plugin AFTER initial scan
        plugin_dir = tmp_path / "new_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text("name: new_plugin\nversion: 1.0.0\ndescription: ''\nevents: []\nhooks: []\n")
        (plugin_dir / "plugin.py").write_text("from app.plugin.base import AIPlugin\nclass NewPlugin(AIPlugin):\n    name = 'new_plugin'\n")

        import time
        time.sleep(0.05)
        changes = w._detect_changes()
        assert "new_plugin" in changes

    def test_watcher_detect_modified_plugin(self, tmp_path):
        r = PluginRegistry()
        plugin_dir = tmp_path / "existing"
        plugin_dir.mkdir()
        manifest_file = plugin_dir / "manifest.yaml"
        manifest_file.write_text("name: existing\nversion: 1.0.0\n")
        plugin_file = plugin_dir / "plugin.py"
        plugin_file.write_text("# v1\n")

        w = PluginWatcher(r, plugin_dir=str(tmp_path), interval=0.1)
        w._scan_once()

        time.sleep(0.05)
        plugin_file.write_text("# v2 modified\n")
        time.sleep(0.05)

        changes = w._detect_changes()
        assert "existing" in changes

    def test_watcher_scan_nonexistent_dir(self):
        r = PluginRegistry()
        w = PluginWatcher(r, plugin_dir="/nonexistent")
        w._scan_once()  # Should not raise

    def test_watcher_continuous_scanning(self, tmp_path):
        r = PluginRegistry()
        w = PluginWatcher(r, plugin_dir=str(tmp_path), interval=0.1)
        w.start()
        time.sleep(0.3)
        w.stop()
        # Should not raise
