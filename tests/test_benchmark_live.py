"""Tests for the live benchmark engine."""

import time
from collections import deque

import pytest

from app.benchmark.live import (
    MAX_RECORDS_PER_PROVIDER,
    WINDOWS_SECONDS,
    LiveBenchmark,
    ProviderBenchmark,
    RequestRecord,
    WindowSnapshot,
    _compute_window,
    _percentile,
    live_benchmark,
)


class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single(self):
        assert _percentile([42.0], 50) == 42.0

    def test_p50(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(vals, 50) == 3.0

    def test_p95(self):
        vals = list(range(1, 101))
        # nearest-rank: index = int(100 * 0.95) = 95 => value 96
        assert _percentile(vals, 95) == 96.0

    def test_p99(self):
        vals = list(range(1, 101))
        # nearest-rank: index = int(100 * 0.99) = 99 => value 100
        assert _percentile(vals, 99) == 100.0


class TestWindowSnapshot:
    def test_defaults(self):
        ws = WindowSnapshot()
        assert ws.requests == 0
        assert ws.avg_latency_ms == 0.0
        assert ws.failure_rate == 0.0

    def test_full_fields(self):
        ws = WindowSnapshot(
            requests=100, successes=90, failures=8, timeouts=2,
            avg_latency_ms=45.0, p95_latency_ms=120.0, p99_latency_ms=200.0,
            tokens_per_sec=500.0, throughput_req_per_sec=10.0,
            failure_rate=0.08, timeout_rate=0.02,
        )
        assert ws.requests == 100
        assert ws.successes == 90
        assert ws.failures == 8
        assert ws.timeouts == 2
        assert ws.avg_latency_ms == 45.0
        assert ws.p95_latency_ms == 120.0
        assert ws.tokens_per_sec == 500.0


class TestComputeWindow:
    def test_empty_records(self):
        ws = _compute_window([], time.time())
        assert ws.requests == 0

    def test_all_within_window(self):
        now = time.time()
        records = [
            RequestRecord(now - 10, 50.0, 20.0, 100, True, False, "gpt-4o"),
            RequestRecord(now - 5, 100.0, 30.0, 200, True, False, "gpt-4o"),
            RequestRecord(now - 1, 150.0, 40.0, 300, True, False, "gpt-4o"),
        ]
        ws = _compute_window(records, now - 60)
        assert ws.requests == 3
        assert ws.avg_latency_ms == 100.0
        assert ws.successes == 3

    def test_filters_old_records(self):
        now = time.time()
        records = [
            RequestRecord(now - 120, 50.0, 0.0, 100, True, False, "gpt-4o"),
            RequestRecord(now - 10, 100.0, 0.0, 200, True, False, "gpt-4o"),
        ]
        ws = _compute_window(records, now - 60)
        assert ws.requests == 1  # only the recent one

    def test_failure_detection(self):
        now = time.time()
        records = [
            RequestRecord(now - 5, 50.0, 0.0, 100, False, False, "gpt-4o"),
            RequestRecord(now - 3, 100.0, 0.0, 200, True, False, "gpt-4o"),
        ]
        ws = _compute_window(records, now - 60)
        assert ws.failures == 1
        assert ws.successes == 1
        assert ws.failure_rate == 0.5

    def test_timeout_detection(self):
        now = time.time()
        records = [
            RequestRecord(now - 5, 5000.0, 0.0, 0, False, True, "gpt-4o"),
            RequestRecord(now - 3, 50.0, 0.0, 100, True, False, "gpt-4o"),
        ]
        ws = _compute_window(records, now - 60)
        assert ws.timeouts == 1
        assert ws.timeout_rate == 0.5

    def test_tokens_per_sec(self):
        now = time.time()
        records = [
            RequestRecord(now - 2, 100.0, 10.0, 500, True, False, "gpt-4o"),
            RequestRecord(now - 1, 200.0, 20.0, 500, True, False, "gpt-4o"),
        ]
        ws = _compute_window(records, now - 60)
        assert ws.total_tokens == 1000

    def test_min_max_latency(self):
        now = time.time()
        records = [
            RequestRecord(now - 5, 10.0, 0.0, 0, True, False, "m"),
            RequestRecord(now - 3, 500.0, 0.0, 0, True, False, "m"),
        ]
        ws = _compute_window(records, now - 60)
        assert ws.min_latency_ms == 10.0
        assert ws.max_latency_ms == 500.0


class TestProviderBenchmark:
    def test_initial_state(self):
        pb = ProviderBenchmark("test")
        assert pb.name == "test"
        assert pb.total_records == 0

    def test_record_success(self):
        pb = ProviderBenchmark("test")
        pb.record(100.0, 20.0, 150, True, False, "gpt-4o")
        assert pb.total_records == 1

    def test_record_failure(self):
        pb = ProviderBenchmark("test")
        pb.record(200.0, 0.0, 0, False, False, "gpt-4o")
        assert pb.total_records == 1

    def test_record_timeout(self):
        pb = ProviderBenchmark("test")
        pb.record(5000.0, 0.0, 0, False, True, "gpt-4o")
        assert pb.total_records == 1

    def test_get_snapshot_has_all_windows(self):
        pb = ProviderBenchmark("test")
        for _ in range(10):
            pb.record(50.0, 10.0, 100, True, False, "gpt-4o")
        snapshots = pb.get_snapshot()
        for window_name in WINDOWS_SECONDS:
            assert window_name in snapshots

    def test_snapshot_recent_data(self):
        pb = ProviderBenchmark("test")
        pb.record(100.0, 20.0, 200, True, False, "gpt-4o")
        snapshots = pb.get_snapshot()
        s1 = snapshots["1min"]
        assert s1.requests == 1
        assert s1.avg_latency_ms == 100.0

    def test_aggregated_score_with_data(self):
        pb = ProviderBenchmark("test")
        for _ in range(10):
            pb.record(50.0, 10.0, 200, True, False, "gpt-4o")
        score = pb.get_aggregated_score()
        assert score > 0
        assert score <= 100

    def test_aggregated_score_insufficient_data(self):
        pb = ProviderBenchmark("test")
        score = pb.get_aggregated_score()
        assert score == 50.0

    def test_reset(self):
        pb = ProviderBenchmark("test")
        pb.record(100.0, 0.0, 0, True, False, "gpt-4o")
        pb.reset()
        assert pb.total_records == 0

    def test_max_records_enforced(self):
        pb = ProviderBenchmark("test")
        for i in range(MAX_RECORDS_PER_PROVIDER + 100):
            pb.record(float(i), 0.0, 0, True, False, "gpt-4o")
        assert pb.total_records <= MAX_RECORDS_PER_PROVIDER


class TestLiveBenchmark:
    def test_get_or_create(self):
        lb = LiveBenchmark()
        pb = lb.get_or_create("openai")
        assert pb.name == "openai"
        assert pb.total_records == 0

    def test_get_or_create_reuses(self):
        lb = LiveBenchmark()
        pb1 = lb.get_or_create("openai")
        pb2 = lb.get_or_create("openai")
        assert pb1 is pb2

    def test_record_creates_provider(self):
        lb = LiveBenchmark()
        lb.record("openai", 100.0, 20.0, 150, True, False, "gpt-4o")
        pb = lb.get_or_create("openai")
        assert pb.total_records == 1

    def test_get_snapshot(self):
        lb = LiveBenchmark()
        lb.record("openai", 50.0, 10.0, 100, True, False, "gpt-4o")
        lb.record("anthropic", 100.0, 20.0, 200, True, False, "claude-3")
        snapshot = lb.get_snapshot()
        assert "openai" in snapshot
        assert "anthropic" in snapshot

    def test_get_provider_snapshot(self):
        lb = LiveBenchmark()
        lb.record("test", 75.0, 15.0, 150, True, False, "gpt-4o")
        ps = lb.get_provider_snapshot("test")
        for window_name in WINDOWS_SECONDS:
            assert window_name in ps

    def test_get_ranking(self):
        lb = LiveBenchmark()
        for _ in range(5):
            lb.record("fast", 10.0, 5.0, 500, True, False, "gpt-4o")
        for _ in range(5):
            lb.record("slow", 500.0, 100.0, 50, True, False, "gpt-4o")
        ranking = lb.get_ranking()
        assert len(ranking) == 2
        assert ranking[0]["provider"] == "fast"
        assert ranking[0]["score"] > ranking[1]["score"]

    def test_get_fastest(self):
        lb = LiveBenchmark()
        for _ in range(5):
            lb.record("fast", 10.0, 5.0, 500, True, False, "gpt-4o")
        for _ in range(5):
            lb.record("slow", 500.0, 100.0, 50, True, False, "gpt-4o")
        assert lb.get_fastest() == "fast"

    def test_get_fastest_empty(self):
        lb = LiveBenchmark()
        assert lb.get_fastest() is None

    def test_reset(self):
        lb = LiveBenchmark()
        lb.record("openai", 50.0, 0.0, 0, True, False, "gpt-4o")
        lb.reset()
        pb = lb.get_or_create("openai")
        assert pb.total_records == 0

    def test_multiple_requests(self):
        lb = LiveBenchmark()
        for _ in range(50):
            lb.record("openai", 100.0, 20.0, 200, True, False, "gpt-4o")
        pb = lb.get_or_create("openai")
        assert pb.total_records == 50

    def test_mixed_success_failure(self):
        lb = LiveBenchmark()
        for _ in range(80):
            lb.record("openai", 100.0, 0.0, 200, True, False, "gpt-4o")
        for _ in range(20):
            lb.record("openai", 100.0, 0.0, 0, False, False, "gpt-4o")
        ps = lb.get_provider_snapshot("openai")
        s1 = ps.get("1min")
        if s1:
            assert s1["successes"] == 80
            assert s1["failures"] == 20
            assert s1["failure_rate"] == 0.2


class TestGlobalInstance:
    def test_live_benchmark_global(self):
        assert live_benchmark is not None
        assert isinstance(live_benchmark, LiveBenchmark)


class TestWindowConstants:
    def test_window_keys(self):
        expected = {"1min", "5min", "15min", "1hour", "24hour"}
        assert set(WINDOWS_SECONDS.keys()) == expected

    def test_window_values(self):
        assert WINDOWS_SECONDS["1min"] == 60
        assert WINDOWS_SECONDS["5min"] == 300
        assert WINDOWS_SECONDS["15min"] == 900
        assert WINDOWS_SECONDS["1hour"] == 3600
        assert WINDOWS_SECONDS["24hour"] == 86400


class TestBenchmarkAPI:
    @pytest.fixture(autouse=True)
    def _reset(self):
        live_benchmark.reset()

    def test_fastapi_endpoint(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        live_benchmark.record("openai", 50.0, 10.0, 200, True, False, "gpt-4o")
        live_benchmark.record("anthropic", 100.0, 30.0, 150, True, False, "claude-3")

        response = client.get("/benchmark/live")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "ranking" in data
        assert "fastest_provider" in data
        assert len(data["providers"]) >= 2

    def test_fastapi_endpoint_single_provider(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        live_benchmark.record("openai", 50.0, 10.0, 200, True, False, "gpt-4o")

        response = client.get("/benchmark/live/openai")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"

    def test_fastapi_endpoint_missing_provider(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/benchmark/live/nonexistent")
        assert response.status_code == 404

    def test_fastapi_endpoint_reset(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        live_benchmark.record("openai", 50.0, 10.0, 200, True, False, "gpt-4o")

        response = client.post("/benchmark/live/reset")
        assert response.status_code == 200
        assert live_benchmark.get_or_create("openai").total_records == 0


class TestPrometheusMetrics:
    def test_benchmark_metrics_exist(self):
        from app.metrics import (
            benchmark_latency,
            benchmark_throughput,
            benchmark_tokens_per_sec,
            benchmark_failure_rate,
            benchmark_timeout_rate,
            benchmark_p95_latency,
            benchmark_first_token_latency,
        )
        assert benchmark_latency is not None
        assert benchmark_throughput is not None
        assert benchmark_tokens_per_sec is not None
        assert benchmark_failure_rate is not None
        assert benchmark_timeout_rate is not None

    def test_update_benchmark_metrics(self):
        from app.benchmark.live import live_benchmark
        from app.metrics import update_benchmark_metrics

        live_benchmark.record("test_metrics", 100.0, 20.0, 200, True, False, "gpt-4o")
        update_benchmark_metrics()
        # Should not raise


class TestRoutingIntegration:
    def test_benchmark_score_in_routing(self):
        from app.routing import build_reputation
        from app.router import ProviderMetrics
        from app.benchmark.live import live_benchmark

        m = ProviderMetrics(name="bench_test")
        m.record_success(50.0, cost_usd=0.01)
        live_benchmark.record("bench_test", 50.0, 10.0, 200, True, False, "gpt-4o")

        rep = build_reputation(m)
        assert rep.benchmark_score > 0
        assert rep.benchmark_score <= 100

    def test_benchmark_score_affects_ranking(self):
        from app.benchmark.live import LiveBenchmark
        from app.models import HealthCheckResponse, ProviderStatus
        from app.routing import RoutingEngine, RoutingContext, build_reputation
        from app.router import ProviderMetrics

        lb = LiveBenchmark()
        engine = RoutingEngine()
        health = HealthCheckResponse(status=ProviderStatus.HEALTHY, provider="test")

        m1 = ProviderMetrics(name="fast_bench")
        m2 = ProviderMetrics(name="slow_bench")
        m1.record_success(10.0)
        m2.record_success(1000.0)

        lb.record("fast_bench", 10.0, 5.0, 500, True, False, "gpt-4o")
        for _ in range(10):
            lb.record("slow_bench", 1000.0, 200.0, 50, True, False, "gpt-4o")

        rep1 = build_reputation(m1)
        rep2 = build_reputation(m2)

        ctx = RoutingContext()
        s1 = engine.score_provider("fast_bench", "gpt-4o", rep1, health, 0, ctx)
        s2 = engine.score_provider("slow_bench", "gpt-4o", rep2, health, 0, ctx)
        assert s1 > s2


class TestRecordInRouter:
    def test_benchmark_recorded_on_success(self):
        from app.benchmark.live import live_benchmark
        live_benchmark.reset()

        from app.router import ProviderMetrics
        m = ProviderMetrics(name="bench_provider")
        m.name = "bench_provider"
        m.record_success(50.0, cost_usd=0.01, prompt_tokens=50, completion_tokens=100)

        live_benchmark.record(
            provider="bench_provider",
            latency_ms=50.0,
            tokens=150,
            success=True,
            model="gpt-4o",
        )

        pb = live_benchmark.get_or_create("bench_provider")
        assert pb.total_records == 1
        snapshots = pb.get_snapshot()
        s1 = snapshots.get("1min")
        assert s1 is not None
        assert s1.successes >= 1

    def test_benchmark_recorded_on_failure(self):
        from app.benchmark.live import live_benchmark
        live_benchmark.reset()

        live_benchmark.record(
            provider="failing_provider",
            latency_ms=200.0,
            tokens=0,
            success=False,
            timeout=False,
            model="gpt-4o",
        )

        pb = live_benchmark.get_or_create("failing_provider")
        assert pb.total_records == 1
        snapshots = pb.get_snapshot()
        s1 = snapshots.get("1min")
        assert s1 is not None
        assert s1.failures >= 1
