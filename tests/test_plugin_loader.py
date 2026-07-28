"""Tests for PluginLoader manifest discovery and loading."""

import tempfile
from pathlib import Path

import pytest

from app.plugin.base import AIPlugin
from app.plugin.loader import PluginLoader, PluginManifest


class TestPluginManifest:
    def test_manifest_defaults(self):
        m = PluginManifest({})
        assert m.name == "unknown"
        assert m.version == "0.1.0"
        assert m.tags == []

    def test_manifest_full(self):
        m = PluginManifest({
            "name": "test",
            "version": "2.0.0",
            "description": "Test plugin",
            "author": "me",
            "tags": ["test", "demo"],
            "events": ["request.started"],
            "hooks": ["before_request"],
        })
        assert m.name == "test"
        assert m.version == "2.0.0"
        assert m.description == "Test plugin"
        assert m.author == "me"
        assert m.tags == ["test", "demo"]
        assert m.events == ["request.started"]
        assert m.hooks == ["before_request"]

    def test_to_dict(self):
        data = {"name": "test", "version": "1.0.0", "description": "", "author": "", "tags": [], "events": [], "hooks": []}
        m = PluginManifest(data)
        d = m.to_dict()
        assert d["name"] == "test"
        assert d["version"] == "1.0.0"


class TestPluginLoader:
    def test_discover_nonexistent_dir(self):
        loader = PluginLoader("/nonexistent/path")
        assert loader.discover() == []

    def test_discover_empty_dir(self, tmp_path):
        loader = PluginLoader(str(tmp_path))
        assert loader.discover() == []

    def test_load_manifest_from_example(self):
        loader = PluginLoader("plugins")
        manifest = loader.load_manifest(Path("plugins/example"))
        assert manifest is not None
        assert manifest.name == "example"
        assert manifest.version == "1.0.0"
        assert "before_request" in manifest.hooks

    def test_load_plugin_example(self):
        loader = PluginLoader("plugins")
        plugin = loader.load_plugin(Path("plugins/example"))
        assert plugin is not None
        assert plugin.name == "example"
        assert plugin.version == "1.0.0"

    def test_load_all_plugins(self):
        loader = PluginLoader("plugins")
        plugins = loader.load_all()
        assert len(plugins) >= 2  # example and logging

    def test_loaded_plugin_is_aiplugin(self):
        loader = PluginLoader("plugins")
        plugin = loader.load_plugin(Path("plugins/example"))
        assert isinstance(plugin, AIPlugin)

    def test_loaded_plugin_has_methods(self):
        loader = PluginLoader("plugins")
        plugin = loader.load_plugin(Path("plugins/example"))
        assert hasattr(plugin, "before_request")
        assert hasattr(plugin, "after_response")
        assert hasattr(plugin, "on_error")
        assert hasattr(plugin, "initialize")
        assert hasattr(plugin, "shutdown")

    def test_load_plugin_with_invalid_path(self, tmp_path):
        loader = PluginLoader(str(tmp_path))
        plugin = loader.load_plugin(tmp_path / "nonexistent")
        assert plugin is None

    def test_load_missing_manifest_is_none(self, tmp_path):
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text("class FakePlugin: pass\n")
        loader = PluginLoader(str(tmp_path))
        manifest = loader.load_manifest(plugin_dir)
        assert manifest is None

    def test_logging_plugin_loaded(self):
        loader = PluginLoader("plugins")
        plugin = loader.load_plugin(Path("plugins/logging"))
        assert plugin is not None
        assert plugin.name == "logging"
        assert plugin.version == "1.0.0"
