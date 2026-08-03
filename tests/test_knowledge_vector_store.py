from __future__ import annotations

import math
import time

import pytest

from app.knowledge.vector_store.config import VectorStoreConfig
from app.knowledge.vector_store.models import (
    DistanceMetric,
    SearchResult,
    VectorCollection,
    VectorRecord,
    VectorStoreStats,
)
from app.knowledge.vector_store.exceptions import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    DuplicateIdError,
    InvalidMetadataError,
    InvalidNamespaceError,
    InvalidScoreError,
    VectorDimensionError,
    VectorStoreError,
)
from app.knowledge.vector_store.protocol import VectorStore
from app.knowledge.vector_store.validation import VectorStoreValidator
from app.knowledge.vector_store.statistics import VectorStoreStatistics
from app.knowledge.vector_store.service import VectorStoreService
from app.knowledge.vector_store.providers import InMemoryVectorStore
from app.knowledge.vector_store.providers.qdrant import HAS_QDRANT
from app.knowledge.vector_store.providers.chroma import HAS_CHROMA
from app.knowledge.vector_store.providers.pgvector import HAS_PGVECTOR
from app.knowledge.vector_store.providers.redis_vector import HAS_REDIS, RedisVectorStore
from app.knowledge.vector_store import create_vector_store

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestVectorStoreModels:
    def test_vector_collection_to_dict(self):
        c = VectorCollection(name="test", dimensions=384)
        d = c.to_dict()
        assert d["name"] == "test"
        assert d["dimensions"] == 384

    def test_vector_record_to_dict(self):
        r = VectorRecord(id="r1", vector=[0.1, 0.2], metadata={"key": "val"})
        d = r.to_dict()
        assert d["id"] == "r1"
        assert d["vector"] == [0.1, 0.2]
        assert d["metadata"]["key"] == "val"

    def test_search_result_to_dict(self):
        r = SearchResult(id="r1", score=0.95, metadata={"k": "v"}, namespace="ns1")
        d = r.to_dict()
        assert d["id"] == "r1"
        assert d["score"] == 0.95
        assert "vector" not in d
        d2 = r.to_dict(include_vector=True)
        assert d2["vector"] is None

    def test_vector_store_stats_to_dict(self):
        s = VectorStoreStats(total_collections=2, total_vectors=100)
        d = s.to_dict()
        assert d["total_collections"] == 2
        assert d["total_vectors"] == 100

    def test_distance_metric_values(self):
        assert DistanceMetric.COSINE.value == "cosine"
        assert DistanceMetric.EUCLIDEAN.value == "euclidean"
        assert DistanceMetric.DOT_PRODUCT.value == "dot_product"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestVectorStoreConfig:
    def test_default(self):
        c = VectorStoreConfig()
        assert c.backend == "memory"
        assert c.dimensions == 384

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "qdrant")
        monkeypatch.setenv("VECTOR_DIMENSIONS", "768")
        monkeypatch.setenv("VECTOR_COLLECTION", "my_coll")
        c = VectorStoreConfig.from_env()
        assert c.backend == "qdrant"
        assert c.dimensions == 768
        assert c.collection == "my_coll"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestVectorStoreValidation:
    def setup_method(self):
        self.v = VectorStoreValidator(dimensions=4)

    def test_validate_collection_name(self):
        assert self.v.validate_collection_name("my-coll") == "my-coll"
        assert self.v.validate_collection_name(" my_coll ") == "my_coll"

    def test_validate_collection_name_empty(self):
        with pytest.raises(InvalidNamespaceError):
            self.v.validate_collection_name("")

    def test_validate_collection_name_invalid_chars(self):
        with pytest.raises(InvalidNamespaceError):
            self.v.validate_collection_name("bad name!")

    def test_validate_namespace(self):
        assert self.v.validate_namespace("ns1") == "ns1"

    def test_validate_namespace_empty(self):
        with pytest.raises(InvalidNamespaceError):
            self.v.validate_namespace("")

    def test_validate_vector(self):
        assert self.v.validate_vector([0.1, 0.2, 0.3, 0.4]) == [0.1, 0.2, 0.3, 0.4]

    def test_validate_vector_empty(self):
        with pytest.raises(InvalidNamespaceError):
            self.v.validate_vector([])

    def test_validate_vector_wrong_dim(self):
        with pytest.raises(VectorDimensionError):
            self.v.validate_vector([0.1, 0.2])

    def test_validate_score(self):
        assert self.v.validate_score(0.5) == 0.5

    def test_validate_score_invalid(self):
        with pytest.raises(InvalidScoreError):
            self.v.validate_score(1.5)

    def test_validate_metadata(self):
        assert self.v.validate_metadata({"key": "val"}) == {"key": "val"}
        assert self.v.validate_metadata(None) == {}

    def test_validate_metadata_bad_type(self):
        with pytest.raises(InvalidMetadataError):
            self.v.validate_metadata("not a dict")

    def test_validate_metadata_bad_key(self):
        with pytest.raises(InvalidMetadataError):
            self.v.validate_metadata({"": "val"})

    def test_check_collection_exists(self):
        with pytest.raises(CollectionNotFoundError):
            self.v.check_collection_exists("missing", False)

    def test_check_duplicate_ids(self):
        result = self.v.check_duplicate_ids(["a", "b"])
        assert set(result) == {"a", "b"}
        assert len(result) == 2

    def test_check_duplicate_ids_raises(self):
        with pytest.raises(DuplicateIdError):
            self.v.check_duplicate_ids(["a", "a"])

# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestVectorStoreStatistics:
    def test_snapshot_empty(self):
        s = VectorStoreStatistics()
        stats = s.snapshot()
        assert stats.total_vectors == 0
        assert stats.average_search_latency == 0.0

    def test_record_search(self):
        s = VectorStoreStatistics()
        s.record_search(0.1)
        s.record_search(0.2)
        stats = s.snapshot()
        assert stats.average_search_latency == 0.15

    def test_record_upsert(self):
        s = VectorStoreStatistics()
        s.record_upsert(5)
        s.record_upsert(3)
        stats = s.snapshot()
        assert stats.total_vectors == 8
        assert stats.batch_throughput == 4.0

    def test_record_delete(self):
        s = VectorStoreStatistics()
        s.record_upsert(10)
        s.record_delete(3)
        stats = s.snapshot()
        assert stats.total_vectors == 7

    def test_set_collections(self):
        s = VectorStoreStatistics()
        s.set_collections(5)
        stats = s.snapshot()
        assert stats.total_collections == 5

    def test_set_provider(self):
        s = VectorStoreStatistics()
        s.set_provider("memory")
        stats = s.snapshot()
        assert stats.provider == "memory"

# ---------------------------------------------------------------------------
# InMemory Vector Store
# ---------------------------------------------------------------------------

class TestInMemoryVectorStore:
    @pytest.fixture
    def store(self):
        return InMemoryVectorStore(dimensions=4)

    @pytest.mark.asyncio
    async def test_create_collection(self, store):
        coll = await store.create_collection("test", dimensions=4)
        assert coll.name == "test"
        assert coll.dimensions == 4

    @pytest.mark.asyncio
    async def test_create_collection_duplicate(self, store):
        await store.create_collection("test")
        with pytest.raises(CollectionAlreadyExistsError):
            await store.create_collection("test")

    @pytest.mark.asyncio
    async def test_list_collections(self, store):
        await store.create_collection("a")
        await store.create_collection("b")
        colls = await store.list_collections()
        assert len(colls) == 2

    @pytest.mark.asyncio
    async def test_collection_exists(self, store):
        assert not await store.collection_exists("test")
        await store.create_collection("test")
        assert await store.collection_exists("test")

    @pytest.mark.asyncio
    async def test_delete_collection(self, store):
        await store.create_collection("test")
        assert await store.delete_collection("test") is True
        assert not await store.collection_exists("test")

    @pytest.mark.asyncio
    async def test_delete_collection_missing(self, store):
        with pytest.raises(CollectionNotFoundError):
            await store.delete_collection("missing")

    @pytest.mark.asyncio
    async def test_upsert(self, store):
        rec = VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4], metadata={"key": "val"})
        result = await store.upsert(rec)
        assert result.id == "r1"
        assert result.vector == [0.1, 0.2, 0.3, 0.4]

    @pytest.mark.asyncio
    async def test_upsert_batch(self, store):
        records = [
            VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]),
            VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8]),
        ]
        results = await store.upsert_batch(records)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_upsert_wrong_dimension(self, store):
        rec = VectorRecord(id="r1", vector=[0.1, 0.2])
        with pytest.raises(VectorDimensionError):
            await store.upsert(rec)

    @pytest.mark.asyncio
    async def test_search(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        await store.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8]))
        results = await store.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 2
        assert results[0].id == "r1"
        assert results[0].score >= 0.99

    @pytest.mark.asyncio
    async def test_search_with_threshold(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        await store.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8]))
        results = await store.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5, score_threshold=0.999)
        assert len(results) == 1
        assert results[0].id == "r1"

    @pytest.mark.asyncio
    async def test_search_with_filter(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4], metadata={"type": "a"}))
        await store.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8], metadata={"type": "b"}))
        results = await store.search(vector=[0.1, 0.2, 0.3, 0.4], filter={"type": "a"})
        assert len(results) == 1
        assert results[0].id == "r1"

    @pytest.mark.asyncio
    async def test_search_with_namespace(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4], namespace="ns1"))
        await store.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8], namespace="ns2"))
        results = await store.search(vector=[0.1, 0.2, 0.3, 0.4], namespace="ns1")
        assert len(results) == 1
        assert results[0].id == "r1"

    @pytest.mark.asyncio
    async def test_search_include_vector(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        results = await store.search(vector=[0.1, 0.2, 0.3, 0.4], include_vector=True)
        assert results[0].vector == [0.1, 0.2, 0.3, 0.4]

    @pytest.mark.asyncio
    async def test_delete_by_ids(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        await store.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8]))
        count = await store.delete(ids=["r1"])
        assert count == 1
        results = await store.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_delete_by_filter(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4], metadata={"type": "a"}))
        await store.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8], metadata={"type": "b"}))
        count = await store.delete(filter={"type": "a"})
        assert count == 1

    @pytest.mark.asyncio
    async def test_clear(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        await store.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8]))
        count = await store.clear()
        assert count == 2
        results = await store.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_statistics(self, store):
        await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        await store.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8]))
        stats = await store.statistics()
        assert stats.total_vectors == 2
        assert stats.provider == "memory"

    @pytest.mark.asyncio
    async def test_rename_collection(self, store):
        await store.create_collection("old")
        coll = await store.rename_collection("old", "new")
        assert coll.name == "new"
        assert await store.collection_exists("new")
        assert not await store.collection_exists("old")

    @pytest.mark.asyncio
    async def test_euclidean_distance(self):
        store = InMemoryVectorStore(dimensions=4, distance=DistanceMetric.EUCLIDEAN)
        await store.upsert(VectorRecord(id="r1", vector=[0.0, 0.0, 0.0, 0.0]))
        await store.upsert(VectorRecord(id="r2", vector=[1.0, 1.0, 1.0, 1.0]))
        results = await store.search(vector=[0.0, 0.0, 0.0, 0.0], top_k=2)
        assert results[0].id == "r1"
        assert results[0].score > results[1].score

    @pytest.mark.asyncio
    async def test_dot_product_distance(self):
        store = InMemoryVectorStore(dimensions=4, distance=DistanceMetric.DOT_PRODUCT)
        await store.upsert(VectorRecord(id="r1", vector=[1.0, 0.0, 0.0, 0.0]))
        await store.upsert(VectorRecord(id="r2", vector=[0.0, 1.0, 0.0, 0.0]))
        results = await store.search(vector=[1.0, 0.0, 0.0, 0.0], top_k=2)
        assert results[0].id == "r1"

    @pytest.mark.asyncio
    async def test_provider_name(self, store):
        assert store.provider_name == "memory"

# ---------------------------------------------------------------------------
# VectorStoreService
# ---------------------------------------------------------------------------

class TestVectorStoreService:
    @pytest.fixture
    def svc(self):
        store = InMemoryVectorStore(dimensions=4)
        return VectorStoreService(store=store)

    @pytest.mark.asyncio
    async def test_create_collection(self, svc):
        coll = await svc.create_collection("test", dimensions=4)
        assert coll.name == "test"

    @pytest.mark.asyncio
    async def test_list_collections(self, svc):
        await svc.create_collection("a")
        await svc.create_collection("b")
        colls = await svc.list_collections()
        assert len(colls) == 2

    @pytest.mark.asyncio
    async def test_delete_collection(self, svc):
        await svc.create_collection("test")
        assert await svc.delete_collection("test") is True

    @pytest.mark.asyncio
    async def test_upsert(self, svc):
        rec = VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4])
        result = await svc.upsert(rec)
        assert result.id == "r1"

    @pytest.mark.asyncio
    async def test_upsert_batch(self, svc):
        records = [
            VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]),
            VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8]),
        ]
        results = await svc.upsert_batch(records)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search(self, svc):
        await svc.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        await svc.upsert(VectorRecord(id="r2", vector=[0.5, 0.6, 0.7, 0.8]))
        results = await svc.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 2
        assert results[0].id == "r1"

    @pytest.mark.asyncio
    async def test_delete(self, svc):
        await svc.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        count = await svc.delete(ids=["r1"])
        assert count == 1

    @pytest.mark.asyncio
    async def test_clear(self, svc):
        await svc.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        count = await svc.clear()
        assert count == 1

    @pytest.mark.asyncio
    async def test_statistics(self, svc):
        await svc.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
        stats = await svc.statistics()
        assert stats.total_vectors >= 1

    @pytest.mark.asyncio
    async def test_store_property(self, svc):
        assert svc.store is not None

# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestCreateVectorStore:
    def test_default_memory(self):
        store = create_vector_store(VectorStoreConfig(backend="memory"))
        assert store.provider_name == "memory"

    def test_qdrant_config(self, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "qdrant")
        store = create_vector_store()
        assert store.provider_name == "qdrant"

    def test_chroma_config(self, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "chroma")
        store = create_vector_store()
        assert store.provider_name == "chroma"

    def test_pgvector_config(self, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "pgvector")
        store = create_vector_store()
        assert store.provider_name == "pgvector"

    def test_redis_vector_config(self, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "redis_vector")
        store = create_vector_store()
        assert store.provider_name == "redis_vector"

# ---------------------------------------------------------------------------
# Qdrant adapter tests (skipped if not installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_QDRANT, reason="qdrant_client not installed")
class TestQdrantVectorStore:
    @pytest.fixture
    def store(self):
        return QdrantVectorStore(dimensions=4)

    @pytest.mark.asyncio
    async def test_provider_name(self, store):
        assert store.provider_name == "qdrant"

    @pytest.mark.asyncio
    async def test_create_collection(self, store):
        try:
            coll = await store.create_collection("test_qdrant", dimensions=4)
            assert coll.name == "test_qdrant"
        except Exception as e:
            if "Connection refused" in str(e) or "connect" in str(e).lower():
                pytest.skip("Qdrant not running")
            raise

    @pytest.mark.asyncio
    async def test_upsert(self, store):
        try:
            rec = VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4])
            result = await store.upsert(rec)
            assert result.id == "r1"
        except Exception as e:
            if "Connection refused" in str(e) or "connect" in str(e).lower():
                pytest.skip("Qdrant not running")
            raise

    @pytest.mark.asyncio
    async def test_search(self, store):
        try:
            await store.upsert(VectorRecord(id="r1", vector=[0.1, 0.2, 0.3, 0.4]))
            results = await store.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
            assert len(results) >= 1
        except Exception as e:
            if "Connection refused" in str(e) or "connect" in str(e).lower():
                pytest.skip("Qdrant not running")
            raise

# ---------------------------------------------------------------------------
# Chroma adapter tests (skipped if not installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_CHROMA, reason="chromadb not installed")
class TestChromaVectorStore:
    @pytest.fixture
    def store(self):
        return ChromaVectorStore(dimensions=4)

    @pytest.mark.asyncio
    async def test_provider_name(self, store):
        assert store.provider_name == "chroma"

# ---------------------------------------------------------------------------
# pgvector adapter tests (skipped if not installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_PGVECTOR, reason="asyncpg not installed")
class TestPgVectorStore:
    @pytest.fixture
    def store(self):
        return PgVectorStore(dimensions=4)

    @pytest.mark.asyncio
    async def test_provider_name(self, store):
        assert store.provider_name == "pgvector"

# ---------------------------------------------------------------------------
# Redis Vector adapter tests (skipped if not installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_REDIS, reason="redis not installed")
class TestRedisVectorStore:
    @pytest.fixture
    def store(self):
        return RedisVectorStore(dimensions=4)

    @pytest.mark.asyncio
    async def test_provider_name(self, store):
        assert store.provider_name == "redis_vector"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TestVectorStoreExceptions:
    def test_collection_not_found(self):
        e = CollectionNotFoundError("test")
        assert "test" in str(e)

    def test_collection_already_exists(self):
        e = CollectionAlreadyExistsError("test")
        assert "test" in str(e)

    def test_vector_dimension_error(self):
        e = VectorDimensionError(384, 128)
        assert "384" in str(e)
        assert "128" in str(e)

    def test_invalid_namespace(self):
        e = InvalidNamespaceError("bad!")
        assert "bad!" in str(e)

    def test_invalid_metadata(self):
        e = InvalidMetadataError()
        assert str(e)

    def test_duplicate_id(self):
        e = DuplicateIdError("dup")
        assert "dup" in str(e)

    def test_invalid_score(self):
        e = InvalidScoreError(2.0)
        assert "2.0" in str(e)

# ---------------------------------------------------------------------------
# Integration: VectorStoreService + InMemory (end-to-end)
# ---------------------------------------------------------------------------

class TestVectorStoreIntegration:
    @pytest.fixture
    def svc(self):
        store = InMemoryVectorStore(dimensions=4)
        return VectorStoreService(store=store)

    @pytest.mark.asyncio
    async def test_full_flow(self, svc):
        # Create collection
        coll = await svc.create_collection("test", dimensions=4)
        assert coll.name == "test"

        # Upsert vectors
        v1 = await svc.upsert(VectorRecord(id="v1", vector=[0.1, 0.2, 0.3, 0.4], metadata={"tag": "a"}))
        v2 = await svc.upsert(VectorRecord(id="v2", vector=[0.5, 0.6, 0.7, 0.8], metadata={"tag": "b"}))
        assert v1.id == "v1"
        assert v2.id == "v2"

        # Search
        results = await svc.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 2
        assert results[0].id == "v1"

        # Filter search
        results = await svc.search(vector=[0.1, 0.2, 0.3, 0.4], filter={"tag": "a"})
        assert len(results) == 1

        # Score threshold
        results = await svc.search(vector=[0.1, 0.2, 0.3, 0.4], score_threshold=0.99)
        assert len(results) == 1

        # Include vector
        results = await svc.search(vector=[0.1, 0.2, 0.3, 0.4], include_vector=True)
        assert results[0].vector == [0.1, 0.2, 0.3, 0.4]

        # Delete
        count = await svc.delete(ids=["v1"])
        assert count == 1
        results = await svc.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 1

        # Clear
        await svc.upsert(VectorRecord(id="v3", vector=[0.1, 0.2, 0.3, 0.4]))
        count = await svc.clear()
        assert count >= 1
        results = await svc.search(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
        assert len(results) == 0

        # Statistics
        stats = await svc.statistics()
        assert stats.total_vectors == 0
