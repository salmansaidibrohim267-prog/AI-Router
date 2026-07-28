"""Tests for the storage layer."""

import time

import pytest

from app.router import ProviderMetrics
from app.storage import InMemoryBackend, ProviderStats, StorageBackend


class TestProviderStats:
    def test_defaults(self):
        s = ProviderStats(name="test")
        assert s.name == "test"
        assert s.total_requests == 0
        assert s.successful_requests == 0
        assert s.failed_requests == 0
        assert s.ewma_latency == 0.0

    def test_fields(self):
        s = ProviderStats(
            name="openai",
            total_requests=100,
            successful_requests=90,
            failed_requests=10,
            total_latency=5000.0,
            ewma_latency=42.5,
            total_cost=1.23,
            first_seen=1000.0,
            last_seen=2000.0,
        )
        assert s.total_requests == 100
        assert s.successful_requests == 90
        assert s.failed_requests == 10


class TestInMemoryBackend:
    @pytest.mark.asyncio
    async def test_save_and_load(self):
        backend = InMemoryBackend()
        stats = ProviderStats(name="test_provider", total_requests=42)
        await backend.save_provider(stats)
        loaded = await backend.load_provider("test_provider")
        assert loaded is not None
        assert loaded.total_requests == 42

    @pytest.mark.asyncio
    async def test_load_missing(self):
        backend = InMemoryBackend()
        result = await backend.load_provider("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_load_all_providers(self):
        backend = InMemoryBackend()
        await backend.save_provider(ProviderStats(name="a"))
        await backend.save_provider(ProviderStats(name="b"))
        all_stats = await backend.load_all_providers()
        assert len(all_stats) == 2

    @pytest.mark.asyncio
    async def test_delete_provider(self):
        backend = InMemoryBackend()
        await backend.save_provider(ProviderStats(name="delete_me"))
        await backend.delete_provider("delete_me")
        assert await backend.load_provider("delete_me") is None

    @pytest.mark.asyncio
    async def test_close(self):
        backend = InMemoryBackend()
        await backend.close()
        assert backend._data == {}

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self):
        backend = InMemoryBackend()
        await backend.save_provider(ProviderStats(name="x", total_requests=1))
        await backend.save_provider(ProviderStats(name="x", total_requests=99))
        loaded = await backend.load_provider("x")
        assert loaded.total_requests == 99

    @pytest.mark.asyncio
    async def test_empty_load_all(self):
        backend = InMemoryBackend()
        assert await backend.load_all_providers() == []

    @pytest.mark.asyncio
    async def test_round_trip_full_stats(self):
        backend = InMemoryBackend()
        original = ProviderStats(
            name="full_test",
            total_requests=100,
            successful_requests=80,
            failed_requests=20,
            total_latency=5000.0,
            ewma_latency=45.0,
            total_cost=2.50,
            total_prompt_tokens=5000,
            total_completion_tokens=3000,
            uptime_seconds=3600.0,
            first_seen=100.0,
            last_seen=200.0,
            consecutive_failures=2,
            consecutive_success=5,
        )
        await backend.save_provider(original)
        loaded = await backend.load_provider("full_test")
        assert loaded.total_requests == 100
        assert loaded.successful_requests == 80
        assert loaded.total_cost == 2.50
        assert loaded.total_prompt_tokens == 5000
        assert loaded.ewma_latency == 45.0

    @pytest.mark.asyncio
    async def test_storage_backend_abc(self):
        """Verify StorageBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            StorageBackend()  # type: ignore


class TestProviderMetricsConversion:
    def test_to_storage(self):
        m = ProviderMetrics(name="test_provider")
        m.total_requests = 50
        m.successful_requests = 40
        m.failed_requests = 10
        m.total_latency = 2000.0
        m.ewma_latency = 42.0
        m.total_cost = 1.00
        m.consecutive_success = 5
        m.consecutive_failures = 1

        s = m.to_storage()
        assert s.name == "test_provider"
        assert s.total_requests == 50
        assert s.successful_requests == 40
        assert s.total_latency == 2000.0
        assert s.ewma_latency == 42.0
        assert s.consecutive_success == 5
        assert s.consecutive_failures == 1
        assert s.first_seen == m._start_time
        assert s.last_seen > 0

    def test_from_storage(self):
        s = ProviderStats(
            name="restored",
            total_requests=100,
            successful_requests=80,
            failed_requests=20,
            total_latency=4000.0,
            ewma_latency=35.0,
            total_cost=5.00,
            total_prompt_tokens=10000,
            total_completion_tokens=5000,
            uptime_seconds=7200.0,
            first_seen=100.0,
            last_seen=200.0,
            consecutive_failures=3,
            consecutive_success=7,
        )
        m = ProviderMetrics.from_storage(s)
        assert m.name == "restored"
        assert m.total_requests == 100
        assert m.successful_requests == 80
        assert m.ewma_latency == 35.0
        assert m.consecutive_success == 7
        assert m.consecutive_failures == 3
        assert m.total_prompt_tokens == 10000
        assert m.total_completion_tokens == 5000

    def test_from_storage_empty(self):
        s = ProviderStats(name="empty")
        m = ProviderMetrics.from_storage(s)
        assert m.name == "empty"
        assert m.total_requests == 0
        assert m._start_time > 0

    def test_to_storage_empty_metrics(self):
        m = ProviderMetrics(name="fresh")
        s = m.to_storage()
        assert s.name == "fresh"
        assert s.total_requests == 0
        assert s.total_latency == 0.0

    def test_round_trip_metrics(self):
        m1 = ProviderMetrics(name="roundtrip")
        m1.record_success(100.0, cost_usd=0.05, prompt_tokens=50, completion_tokens=100)
        m1.record_success(200.0, cost_usd=0.10, prompt_tokens=100, completion_tokens=200)
        m1.record_failure(50.0)

        s = m1.to_storage()
        m2 = ProviderMetrics.from_storage(s)

        assert m2.name == "roundtrip"
        assert m2.total_requests == 3
        assert m2.successful_requests == 2
        assert m2.failed_requests == 1
        assert abs(m2.total_cost - 0.15) < 0.001
        assert m2.consecutive_success == 0
        assert m2.consecutive_failures == 1


class TestPersistenceOnRequest:
    @pytest.mark.asyncio
    async def test_metrics_persisted_after_success(self):
        from app.router import AIRouter
        from app.storage import InMemoryBackend

        storage = InMemoryBackend()
        router = AIRouter(storage_backend=storage)
        router._initialized = True

        m = ProviderMetrics(name="test_provider")
        router.metrics["test_provider"] = m

        m.record_success(100.0, cost_usd=0.05, prompt_tokens=50, completion_tokens=100)

        await router._persist_all_metrics()

        loaded = await storage.load_provider("test_provider")
        assert loaded is not None
        assert loaded.total_requests == 1
        assert loaded.total_latency == 100.0

    @pytest.mark.asyncio
    async def test_load_persisted_metrics_on_init(self):
        from app.router import AIRouter
        from app.storage import InMemoryBackend

        storage = InMemoryBackend()
        s = ProviderStats(
            name="preloaded",
            total_requests=50,
            successful_requests=40,
            failed_requests=10,
            ewma_latency=30.0,
            total_latency=2000.0,
            first_seen=100.0,
            last_seen=200.0,
        )
        await storage.save_provider(s)

        router = AIRouter(storage_backend=storage)
        await router._load_persisted_metrics()

        assert "preloaded" in router.metrics
        assert router.metrics["preloaded"].total_requests == 50
        assert router.metrics["preloaded"].ewma_latency == 30.0

    @pytest.mark.asyncio
    async def test_load_persisted_empty_backend(self):
        from app.router import AIRouter
        from app.storage import InMemoryBackend

        router = AIRouter(storage_backend=InMemoryBackend())
        await router._load_persisted_metrics()
        assert len(router.metrics) == 0

    @pytest.mark.asyncio
    async def test_persist_all_handles_empty_metrics(self):
        from app.router import AIRouter
        from app.storage import InMemoryBackend

        storage = InMemoryBackend()
        router = AIRouter(storage_backend=storage)

        # Should not raise
        await router._persist_all_metrics()
        assert await storage.load_all_providers() == []

    @pytest.mark.asyncio
    async def test_metrics_survive_restart(self):
        from app.router import AIRouter, ProviderMetrics
        from app.storage import InMemoryBackend

        storage = InMemoryBackend()
        router1 = AIRouter(storage_backend=storage)
        router1._initialized = True

        m = ProviderMetrics(name="survivor")
        m.record_success(50.0, cost_usd=0.01)
        m.record_failure(100.0)
        router1.metrics["survivor"] = m
        await router1._persist_all_metrics()

        router2 = AIRouter(storage_backend=storage)
        await router2._load_persisted_metrics()

        loaded = router2.metrics.get("survivor")
        assert loaded is not None
        assert loaded.total_requests == 2
        assert loaded.successful_requests == 1
        assert loaded.failed_requests == 1
        assert loaded.ewma_latency == 50.0
