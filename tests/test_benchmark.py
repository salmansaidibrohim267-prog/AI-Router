"""Tests for benchmark functionality."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.models import BenchmarkRequest, BenchmarkResponse


class TestBenchmarkModels:
    def test_benchmark_request_defaults(self):
        req = BenchmarkRequest()
        assert req.model == "gpt-4o-mini"
        assert req.num_requests == 10
        assert req.concurrency == 5
        assert req.stream is False
        assert req.prompt == "Say hello in one word"

    def test_benchmark_request_custom(self):
        req = BenchmarkRequest(model="gpt-4", num_requests=20, concurrency=10, stream=True, prompt="Test")
        assert req.model == "gpt-4"
        assert req.num_requests == 20
        assert req.concurrency == 10
        assert req.stream is True
        assert req.prompt == "Test"

    def test_benchmark_request_with_provider(self):
        req = BenchmarkRequest(provider="openai")
        assert req.provider == "openai"

    def test_benchmark_response_defaults(self):
        resp = BenchmarkResponse(
            num_requests=10,
            concurrency=5,
            stream=False,
            duration_seconds=1.0,
            average_latency_ms=100.0,
            p95_latency_ms=150.0,
            p99_latency_ms=200.0,
            throughput_reqs_per_sec=10.0,
            success_rate=1.0,
            errors=0,
            fallback_count=0,
        )
        assert resp.num_requests == 10
        assert resp.success_rate == 1.0

    def test_benchmark_response_with_provider_stats(self):
        resp = BenchmarkResponse(
            num_requests=10,
            concurrency=5,
            stream=False,
            duration_seconds=1.0,
            average_latency_ms=100.0,
            p95_latency_ms=150.0,
            p99_latency_ms=200.0,
            throughput_reqs_per_sec=10.0,
            success_rate=0.9,
            errors=1,
            fallback_count=0,
            provider_success={"openai": 9},
            provider_failure={"openai": 1},
        )
        assert resp.provider_success["openai"] == 9
        assert resp.provider_failure["openai"] == 1

    def test_benchmark_response_json(self):
        resp = BenchmarkResponse(
            num_requests=5,
            concurrency=5,
            stream=True,
            duration_seconds=2.0,
            average_latency_ms=200.0,
            p95_latency_ms=300.0,
            p99_latency_ms=400.0,
            throughput_reqs_per_sec=2.5,
            success_rate=1.0,
            errors=0,
            fallback_count=0,
        )
        data = resp.model_dump()
        assert data["num_requests"] == 5
        assert data["stream"] is True


@pytest.mark.asyncio
async def test_benchmark_runner_result():
    from benchmarks.runner import BenchmarkResult

    result = BenchmarkResult(target="internal", num_requests=10, concurrency=5, stream=False)
    result.latencies_ms = [100, 200, 150, 300, 250, 180, 120, 220, 170, 140]
    result.start_time = 1000.0
    result.end_time = 1010.0

    assert result.average_latency_ms == 183.0
    assert result.p95_latency_ms > 0
    assert result.p99_latency_ms > 0
    assert result.throughput_reqs_per_sec == 1.0
    assert result.success_rate == 1.0

    data = result.to_dict()
    assert data["num_requests"] == 10
    assert "average_latency_ms" in data
    assert "p95_latency_ms" in data
    assert "p99_latency_ms" in data
    assert "throughput_reqs_per_sec" in data
    assert "success_rate" in data


@pytest.mark.asyncio
async def test_benchmark_result_with_errors():
    from benchmarks.runner import BenchmarkResult

    result = BenchmarkResult(target="internal", num_requests=10, concurrency=5, stream=False, errors=2)
    result.latencies_ms = [100] * 8
    result.start_time = 1000.0
    result.end_time = 1005.0

    assert result.success_rate == 0.8
    assert result.errors == 2


@pytest.mark.asyncio
async def test_benchmark_result_empty_latencies():
    from benchmarks.runner import BenchmarkResult

    result = BenchmarkResult(target="internal", num_requests=0, concurrency=1, stream=False)
    assert result.average_latency_ms == 0.0
    assert result.p95_latency_ms == 0.0
    assert result.p99_latency_ms == 0.0
    assert result.throughput_reqs_per_sec == 0.0


@pytest.mark.asyncio
async def test_benchmark_result_provider_stats():
    from benchmarks.runner import BenchmarkResult

    result = BenchmarkResult(target="internal", num_requests=10, concurrency=5, stream=False)
    result.provider_success = {"openai": 8}
    result.provider_failure = {"openai": 2}
    data = result.to_dict()
    assert data["provider_success"]["openai"] == 8
    assert data["provider_failure"]["openai"] == 2


@pytest.mark.asyncio
async def test_benchmark_endpoint():
    client = TestClient(app)

    with (
        patch("app.api.router.initialize", AsyncMock()),
        patch("benchmarks.runner.run_benchmark") as mock_run,
    ):
        from benchmarks.runner import BenchmarkResult

        result = BenchmarkResult(
            target="internal",
            num_requests=5,
            concurrency=2,
            stream=False,
            latencies_ms=[100, 200, 150],
            start_time=1000.0,
            end_time=1005.0,
        )
        result.provider_success = {"openai": 3}
        mock_run.return_value = result

        response = client.get(
            "/benchmark?model=gpt-4o-mini&num_requests=5&concurrency=2&stream=false",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["num_requests"] == 5
        assert data["concurrency"] == 2
        assert "average_latency_ms" in data
        assert "p95_latency_ms" in data
        assert "p99_latency_ms" in data
        assert "throughput_reqs_per_sec" in data
        assert data["provider_success"]["openai"] == 3


@pytest.mark.asyncio
async def test_benchmark_endpoint_streaming():
    client = TestClient(app)

    with (
        patch("app.api.router.initialize", AsyncMock()),
        patch("benchmarks.runner.run_benchmark") as mock_run,
    ):
        from benchmarks.runner import BenchmarkResult

        result = BenchmarkResult(
            target="internal",
            num_requests=5,
            concurrency=2,
            stream=True,
            latencies_ms=[150, 250],
            start_time=1000.0,
            end_time=1006.0,
        )
        mock_run.return_value = result

        response = client.get(
            "/benchmark?model=gpt-4o-mini&num_requests=5&concurrency=2&stream=true",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stream"] is True


@pytest.mark.asyncio
async def test_get_system_metrics():
    from benchmarks.runner import get_system_metrics

    with (
        patch("app.stats.stats.summary") as mock_summary,
        patch("app.cache.cache_manager.get_all_stats") as mock_cache,
    ):
        from app.stats import StatsSummary

        mock_summary.return_value = StatsSummary(
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            success_rate=0.95,
            provider_usage={"openai": 80},
            model_usage={"gpt-4": 80},
            task_usage={"chat": 100},
            average_latency_ms=200.0,
        )
        mock_cache.return_value = {"responses": {"hits": 50, "misses": 50, "size": 100}}

        metrics = await get_system_metrics()
        assert metrics["total_requests"] == 100
        assert metrics["success_rate"] == 0.95
        assert metrics["cache_hit_ratio"] == 0.5


@pytest.mark.asyncio
async def test_get_system_metrics_empty_cache():
    from benchmarks.runner import get_system_metrics

    with (
        patch("app.stats.stats.summary") as mock_summary,
        patch("app.cache.cache_manager.get_all_stats") as mock_cache,
    ):
        from app.stats import StatsSummary

        mock_summary.return_value = StatsSummary()
        mock_cache.return_value = {}

        metrics = await get_system_metrics()
        assert metrics["cache_hit_ratio"] == 0.0
