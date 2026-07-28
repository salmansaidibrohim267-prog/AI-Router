"""Tests for PluginRegistry."""

import pytest

from app.plugin.base import AIPlugin, HookResult
from app.plugin.registry import PluginRegistry


class TestPluginRegistry:
    def test_initial_empty(self):
        r = PluginRegistry()
        assert r.get_all() == {}
        assert r.get_enabled() == []
        assert r.names == []
        assert r.disabled == set()

    def test_discover_and_load(self):
        r = PluginRegistry()
        loaded = r.discover_and_load()
        assert len(loaded) >= 2
        assert "example" in loaded
        assert "logging" in loaded

    def test_get_loaded_plugin(self):
        r = PluginRegistry()
        r.discover_and_load()
        p = r.get("example")
        assert p is not None
        assert p.name == "example"

    def test_get_nonexistent(self):
        r = PluginRegistry()
        assert r.get("nonexistent") is None

    def test_enable_disable(self):
        r = PluginRegistry()
        r.discover_and_load()
        assert r.is_enabled("example") is True

        r.disable("example")
        assert r.is_enabled("example") is False
        assert "example" in r.disabled

        r.enable("example")
        assert r.is_enabled("example") is True
        assert "example" not in r.disabled

    def test_disable_nonexistent(self):
        r = PluginRegistry()
        assert r.disable("nonexistent") is False

    def test_enable_nonexistent(self):
        r = PluginRegistry()
        assert r.enable("nonexistent") is False

    def test_get_enabled_filters_disabled(self):
        r = PluginRegistry()
        r.discover_and_load()
        r.disable("example")
        enabled = r.get_enabled()
        names = [p.name for p in enabled]
        assert "example" not in names
        assert "logging" in names

    def test_get_manifest(self):
        r = PluginRegistry()
        r.discover_and_load()
        m = r.get_manifest("example")
        assert m is not None
        assert m.name == "example"

    def test_get_manifest_nonexistent(self):
        r = PluginRegistry()
        assert r.get_manifest("nonexistent") is None

    def test_get_report(self):
        r = PluginRegistry()
        r.discover_and_load()
        report = r.get_report()
        assert report["total"] >= 2
        assert "example" in report["plugins"]
        assert report["plugins"]["example"]["enabled"] is True
        assert report["plugins"]["example"]["version"] == "1.0.0"

    def test_manifest_property(self):
        r = PluginRegistry()
        r.discover_and_load()
        m = r.manifest
        assert "example" in m
        assert "logging" in m

    def test_shutdown_all(self):
        r = PluginRegistry()
        r.discover_and_load()
        r.shutdown_all()
        # Should not raise

    def test_concurrent_enable_disable(self):
        r = PluginRegistry()
        r.discover_and_load()
        import threading
        def toggle():
            for _ in range(10):
                r.disable("example")
                r.enable("example")
        threads = [threading.Thread(target=toggle) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert r.is_enabled("example") is True
