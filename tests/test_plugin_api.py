"""Tests for the plugin management API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.router import router


@pytest.fixture(autouse=True)
def _ensure_plugins_loaded():
    router.plugin_registry.discover_and_load()


class TestPluginAPI:
    def test_list_plugins(self):
        client = TestClient(app)
        resp = client.get("/plugins")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert "example" in data["plugins"]
        assert "logging" in data["plugins"]

    def test_plugin_status(self):
        client = TestClient(app)
        resp = client.get("/plugins")
        data = resp.json()
        assert data["plugins"]["example"]["enabled"] is True
        assert data["plugins"]["example"]["version"] == "1.0.0"

    def test_enable_plugin(self):
        client = TestClient(app)
        router.plugin_registry.disable("example")

        resp = client.post("/plugins/enable?name=example")
        assert resp.status_code == 200
        assert router.plugin_registry.is_enabled("example") is True

    def test_enable_nonexistent_plugin(self):
        client = TestClient(app)
        resp = client.post("/plugins/enable?name=nonexistent")
        assert resp.status_code == 404

    def test_disable_plugin(self):
        client = TestClient(app)
        resp = client.post("/plugins/disable?name=example")
        assert resp.status_code == 200
        assert router.plugin_registry.is_enabled("example") is False

        router.plugin_registry.enable("example")

    def test_disable_nonexistent_plugin(self):
        client = TestClient(app)
        resp = client.post("/plugins/disable?name=nonexistent")
        assert resp.status_code == 404

    def test_reload_plugins(self):
        client = TestClient(app)
        resp = client.post("/plugins/reload")
        assert resp.status_code == 200
        data = resp.json()
        assert "loaded" in data

    def test_plugin_events_endpoint(self):
        client = TestClient(app)
        from app.event_bus import event_bus
        import asyncio
        asyncio.run(event_bus.emit("test.event", foo=1))

        resp = client.get("/plugins/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "registered_events" in data
        assert "recent" in data
        assert len(data["recent"]) >= 1

    def test_custom_providers_endpoint(self):
        client = TestClient(app)
        resp = client.get("/providers/custom")
        assert resp.status_code == 200

    def test_classifier_endpoint(self):
        client = TestClient(app)
        resp = client.get("/classifier")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "active" in data
