import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.api import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAPIHealth:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "AI Router Gateway"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_ready(self, client):
        resp = client.get("/ready")
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            assert resp.json()["status"] == "ok"
        else:
            assert resp.json()["status"] == "unavailable"

    def test_ready_reports_providers_available(self, client):
        resp = client.get("/ready")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "config_loaded" in data
        assert "providers_available" in data

    def test_metrics(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_cache_stats(self, client):
        resp = client.get("/cache/stats")
        assert resp.status_code == 200


class TestAPIEndpoints:
    def test_providers(self, client):
        resp = client.get("/providers")
        assert resp.status_code in (200, 500)

    def test_models(self, client):
        resp = client.get("/models")
        assert resp.status_code in (200, 500)

    def test_stats(self, client):
        resp = client.get("/stats")
        assert resp.status_code == 200

    def test_config(self, client):
        resp = client.get("/config")
        assert resp.status_code == 200

    def test_dashboard(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code in (200, 500)

    def test_logs(self, client):
        resp = client.get("/logs")
        assert resp.status_code == 200

    def test_costs(self, client):
        resp = client.get("/costs")
        assert resp.status_code == 200

    def test_providers_health(self, client):
        resp = client.get("/health/providers")
        assert resp.status_code in (200, 500)

    def test_stats_providers(self, client):
        resp = client.get("/stats/providers")
        assert resp.status_code == 200

    def test_stats_tasks(self, client):
        resp = client.get("/stats/tasks")
        assert resp.status_code == 200

    def test_stats_errors(self, client):
        resp = client.get("/stats/errors")
        assert resp.status_code == 200

    def test_nonexistent_provider_health(self, client):
        resp = client.get("/health/providers/nonexistent")
        assert resp.status_code == 404

    def test_nonexistent_provider_models(self, client):
        resp = client.get("/providers/nonexistent/models")
        assert resp.status_code == 404

    def test_nonexistent_task_models(self, client):
        resp = client.get("/models/nonexistent_task_xyz")
        assert resp.status_code == 404

    def test_nonexistent_stats_provider(self, client):
        resp = client.get("/stats/providers/nonexistent")
        assert resp.status_code == 404

    def test_nonexistent_model_stats(self, client):
        resp = client.get("/stats/models/nonexistent/model")
        assert resp.status_code == 404


class TestAPIErrorHandling:
    def test_rate_limit_headers(self, client):
        for _ in range(5):
            resp = client.get("/providers")
        assert "X-RateLimit-Limit" in resp.headers

    def test_request_id_header(self, client):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers


class TestAPIModels:
    def test_models_endpoint_structure(self, client):
        resp = client.get("/models")
        if resp.status_code == 200:
            data = resp.json()
            assert "models" in data
            assert "total" in data


class TestAPIReloadConfig:
    def test_reload_config(self, client):
        resp = client.post("/reload-config")
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data

    def test_clear_cache(self, client):
        resp = client.post("/cache/clear")
        assert resp.status_code == 200

    def test_reset_stats(self, client):
        resp = client.post("/stats/reset")
        assert resp.status_code == 200


class TestAPICostEndpoints:
    def test_provider_cost_not_found(self, client):
        resp = client.get("/costs/nonexistent")
        assert resp.status_code == 404

    def test_logs_by_request_id_not_found(self, client):
        resp = client.get("/logs/nonexistent-id")
        assert resp.status_code == 200
        assert resp.json() is None


class TestAPIVersion:
    def test_version_endpoint(self, client):
        resp = client.get("/version")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "git_commit" in data
        assert "build_date" in data
        assert "python_version" in data

    def test_root_includes_version(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data


class TestAPIHealthDetail:
    def test_health_includes_build_info(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "commit" in data
        assert "build_date" in data
        assert "python_version" in data
        assert "dependencies" in data
        assert "config_loaded" in data["dependencies"]

    def test_health_includes_memory(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "memory" in data

    def test_health_includes_uptime(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0

    def test_health_providers_endpoint(self, client):
        resp = client.get("/health/providers")
        assert resp.status_code in (200, 500)


class TestAPISecurity:
    def test_security_headers_present(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_request_id_header(self, client):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers

    def test_expose_headers(self, client):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers


class TestAPIRateLimit:
    def test_health_not_rate_limited(self, client):
        for _ in range(200):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_metrics_not_rate_limited(self, client):
        for _ in range(200):
            resp = client.get("/metrics")
            assert resp.status_code == 200
