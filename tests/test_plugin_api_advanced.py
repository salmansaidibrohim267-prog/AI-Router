"""Advanced tests for plugin management API endpoints."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.event_bus import event_bus
from app.plugin.base import AIPlugin, HookResult
from app.router import router


@pytest.fixture(autouse=True)
def _ensure_plugins_loaded():
    router.plugin_registry.discover_and_load()


class TestPluginAPIAdvanced:
    def test_list_plugins_structure(self):
        client = TestClient(app)
        resp = client.get("/plugins")
        data = resp.json()
        assert "total" in data
        assert "enabled" in data
        assert "disabled" in data
        assert "plugins" in data

    def test_plugin_report_has_correct_fields(self):
        client = TestClient(app)
        resp = client.get("/plugins")
        data = resp.json()
        for name, info in data["plugins"].items():
            assert "name" in info
            assert "version" in info
            assert "enabled" in info
            assert "events" in info
            assert "hooks" in info

    def test_reload_plugins_returns_loaded_list(self):
        client = TestClient(app)
        resp = client.post("/plugins/reload")
        data = resp.json()
        assert "loaded" in data
        assert isinstance(data["loaded"], list)

    def test_enable_already_enabled_plugin(self):
        client = TestClient(app)
        router.plugin_registry.enable("logging")
        resp = client.post("/plugins/enable?name=logging")
        assert resp.status_code == 200

    def test_disable_already_disabled_plugin(self):
        client = TestClient(app)
        router.plugin_registry.disable("logging")
        resp = client.post("/plugins/disable?name=logging")
        assert resp.status_code == 200
        router.plugin_registry.enable("logging")

    def test_enable_invalid_name(self):
        client = TestClient(app)
        resp = client.post("/plugins/enable?name=")
        assert resp.status_code == 404

    def test_disable_invalid_name(self):
        client = TestClient(app)
        resp = client.post("/plugins/disable?name=")
        assert resp.status_code == 404

    def test_plugin_events_with_filter(self):
        client = TestClient(app)
        asyncio.run(event_bus.emit("test.event_a", value=1))
        asyncio.run(event_bus.emit("test.event_b", value=2))
        asyncio.run(event_bus.emit("test.event_a", value=3))

        resp = client.get("/plugins/events?limit=2")
        data = resp.json()
        assert len(data["recent"]) == 2

    def test_plugin_events_contains_expected_fields(self):
        client = TestClient(app)
        resp = client.get("/plugins/events")
        data = resp.json()
        assert "registered_events" in data
        assert "recent" in data
        assert "total_events" in data

    def test_reload_returns_loaded_list(self):
        client = TestClient(app)
        resp = client.post("/plugins/reload")
        data = resp.json()
        assert "loaded" in data
        assert isinstance(data["loaded"], list)

    def test_plugin_events_limit_negative(self):
        client = TestClient(app)
        resp = client.get("/plugins/events?limit=-1")
        assert resp.status_code == 200

    def test_plugin_events_history_has_data(self):
        client = TestClient(app)
        resp = client.get("/plugins/events")
        data = resp.json()
        assert "total_events" in data

    def test_plugin_report_after_reload(self):
        client = TestClient(app)
        client.post("/plugins/reload")
        resp = client.get("/plugins")
        data = resp.json()
        assert data["total"] >= 2
        assert "logging" in data["plugins"]

    def test_plugin_endpoints_with_disabled_plugin(self):
        client = TestClient(app)
        router.plugin_registry.disable("example")
        resp = client.get("/plugins")
        data = resp.json()
        assert data["plugins"]["example"]["enabled"] is False
        router.plugin_registry.enable("example")
