import pytest
from app.metrics import (
    record_request,
    record_success,
    record_failure,
    record_latency,
    record_cache_hit,
    record_cache_miss,
    set_provider_health,
    set_provider_latency,
    update_uptime,
    get_metrics,
)


class TestMetrics:
    def test_record_request(self):
        record_request("test_provider", "test_model", "chat")

    def test_record_success(self):
        record_success("test_provider", "test_model")

    def test_record_failure(self):
        record_failure("test_provider", "test_model", "timeout")

    def test_record_latency(self):
        record_latency("test_provider", "test_model", 100.0)

    def test_record_cache_hit(self):
        record_cache_hit("responses")

    def test_record_cache_miss(self):
        record_cache_miss("responses")

    def test_set_provider_health(self):
        set_provider_health("test_provider", True)
        set_provider_health("test_provider", False)

    def test_set_provider_latency(self):
        set_provider_latency("test_provider", 50.0)

    def test_update_uptime(self):
        update_uptime()

    def test_get_metrics_returns_bytes(self):
        data = get_metrics()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_metrics_contain_expected_counters(self):
        data = get_metrics().decode()
        assert "ai_router_request_total" in data
        assert "ai_router_request_success" in data
        assert "ai_router_request_failed" in data
        assert "ai_router_provider_latency_seconds" in data
        assert "ai_router_provider_requests_total" in data
        assert "ai_router_provider_failure_total" in data
        assert "ai_router_cache_hit" in data
        assert "ai_router_cache_miss" in data
        assert "ai_router_provider_health" in data
        assert "ai_router_uptime_seconds" in data
