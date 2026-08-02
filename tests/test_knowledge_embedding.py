import asyncio
import time

import numpy as np
import pytest

from app.knowledge.embedding.batch import BatchProcessor
from app.knowledge.embedding.cache import InMemoryEmbeddingCache, _cache_key
from app.knowledge.embedding.config import EmbeddingConfig
from app.knowledge.embedding.models import EmbeddingRecord, EmbeddingResult
from app.knowledge.embedding.providers import (
    LocalEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    OllamaEmbeddingAdapter,
    create_embedding_provider,
)
from app.knowledge.embedding.statistics import EmbeddingStatistics
from app.knowledge.embedding.validation import (
    EmbeddingValidator,
    EmptyTextError,
    TextTooLongError,
    DimensionMismatchError,
    InvalidResponseError,
)
from app.knowledge.embedding.service import EmbeddingService
from app.knowledge.models import KnowledgeChunk
from app.knowledge.service import KnowledgeService
from app.knowledge.repository import InMemoryKnowledgeRepository

try:
    from app.knowledge.embedding.providers import HAS_SENTENCE_TRANSFORMERS
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    from app.knowledge.embedding.cache import HAS_REDIS
except ImportError:
    HAS_REDIS = False


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestEmbeddingModels:
    def test_embedding_result(self):
        r = EmbeddingResult(vector=[0.1, 0.2], model="m", provider="p", dimensions=2)
        d = r.to_dict()
        assert d["vector"] == [0.1, 0.2]
        assert d["dimensions"] == 2

    def test_embedding_record(self):
        r = EmbeddingRecord(
            id="e1", document_id="d1", chunk_id="c1",
            model="m", provider="p", dimensions=2,
            vector=[0.1, 0.2], token_count=5,
        )
        d = r.to_dict()
        assert d["id"] == "e1"
        assert d["vector"] == [0.1, 0.2]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestEmbeddingConfig:
    def test_default(self):
        c = EmbeddingConfig()
        assert c.provider == "local"
        assert c.batch_size == 16
        assert c.cache_enabled is True

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "8")
        c = EmbeddingConfig.from_env()
        assert c.provider == "openai"
        assert c.batch_size == 8


# ---------------------------------------------------------------------------
# Local Embedding Provider
# ---------------------------------------------------------------------------

class TestLocalEmbeddingProvider:
    @pytest.mark.asyncio
    async def test_embed_single(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        results = await provider.embed(["hello world"])
        assert len(results) == 1
        assert len(results[0].vector) == 4
        assert results[0].provider == "local"

    @pytest.mark.asyncio
    async def test_embed_multiple(self):
        provider = LocalEmbeddingAdapter(dimensions=8)
        results = await provider.embed(["hello", "world", "test"])
        assert len(results) == 3
        assert all(len(r.vector) == 8 for r in results)

    @pytest.mark.asyncio
    async def test_deterministic(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        r1 = await provider.embed(["hello"])
        r2 = await provider.embed(["hello"])
        assert r1[0].vector == r2[0].vector

    @pytest.mark.asyncio
    async def test_different_texts_different_vectors(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        r1 = await provider.embed(["hello"])
        r2 = await provider.embed(["world"])
        assert r1[0].vector != r2[0].vector

    @pytest.mark.asyncio
    async def test_normalized(self):
        provider = LocalEmbeddingAdapter(dimensions=128)
        results = await provider.embed(["hello"])
        vec = np.array(results[0].vector)
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_empty_text(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        results = await provider.embed([""])
        assert results[0].vector == [0.0, 0.0, 0.0, 0.0]

    @pytest.mark.asyncio
    async def test_token_count(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        results = await provider.embed(["hello world test"])
        assert results[0].token_count == 3

    def test_dimensions_property(self):
        provider = LocalEmbeddingAdapter(dimensions=128)
        assert provider.dimensions == 128
        assert provider.provider_name == "local"


# ---------------------------------------------------------------------------
# OpenAI Provider (mocked)
# ---------------------------------------------------------------------------

class TestOpenAIProvider:
    @pytest.mark.asyncio
    async def test_requires_api_key(self):
        provider = OpenAIEmbeddingAdapter(api_key="")
        with pytest.raises(ValueError):
            await provider.embed(["hello"])

    @pytest.mark.asyncio
    async def test_provider_name(self):
        provider = OpenAIEmbeddingAdapter(api_key="sk-test")
        assert provider.provider_name == "openai"


# ---------------------------------------------------------------------------
# Ollama Provider
# ---------------------------------------------------------------------------

class TestOllamaProvider:
    @pytest.mark.asyncio
    async def test_provider_name(self):
        provider = OllamaEmbeddingAdapter(base_url="http://localhost:11434")
        assert provider.provider_name == "ollama"

    def test_defaults(self):
        provider = OllamaEmbeddingAdapter()
        assert provider._model == "nomic-embed-text"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_create_local(self):
        p = create_embedding_provider("local")
        assert isinstance(p, LocalEmbeddingAdapter)

    def test_create_openai(self):
        p = create_embedding_provider("openai", api_key="sk-test")
        assert isinstance(p, OpenAIEmbeddingAdapter)

    def test_create_ollama(self):
        p = create_embedding_provider("ollama")
        assert isinstance(p, OllamaEmbeddingAdapter)

    def test_unknown(self):
        with pytest.raises(ValueError):
            create_embedding_provider("unknown")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class TestInMemoryCache:
    @pytest.mark.asyncio
    async def test_get_miss(self):
        cache = InMemoryEmbeddingCache()
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        cache = InMemoryEmbeddingCache()
        await cache.set("key1", [0.1, 0.2])
        result = await cache.get("key1")
        assert result == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_expiry(self):
        cache = InMemoryEmbeddingCache(ttl=0)
        await cache.set("key1", [0.1, 0.2])
        await asyncio.sleep(0.01)
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self):
        cache = InMemoryEmbeddingCache()
        await cache.set("k1", [1.0])
        await cache.clear()
        result = await cache.get("k1")
        assert result is None

    @pytest.mark.asyncio
    async def test_stats(self):
        cache = InMemoryEmbeddingCache()
        await cache.get("miss1")
        await cache.get("miss2")
        await cache.set("k1", [1.0])
        await cache.get("k1")
        stats = await cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 2
        assert stats["size"] == 1

    def test_cache_key(self):
        k1 = _cache_key("hello", "model1")
        k2 = _cache_key("hello", "model1")
        assert k1 == k2
        k3 = _cache_key("hello", "model2")
        assert k1 != k3
        assert k1.startswith("emb:")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestEmbeddingValidator:
    @pytest.mark.asyncio
    async def test_valid_text(self):
        v = EmbeddingValidator()
        result = await v.validate_text("  hello  ")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_empty_text(self):
        v = EmbeddingValidator()
        with pytest.raises(EmptyTextError):
            await v.validate_text("")
        with pytest.raises(EmptyTextError):
            await v.validate_text("   ")

    @pytest.mark.asyncio
    async def test_text_too_long(self):
        v = EmbeddingValidator()
        long_text = "x" * (EmbeddingValidator.MAX_TEXT_LENGTH + 1)
        with pytest.raises(TextTooLongError):
            await v.validate_text(long_text)

    @pytest.mark.asyncio
    async def test_validate_texts(self):
        v = EmbeddingValidator()
        result = await v.validate_texts(["a", "b"])
        assert len(result) == 2
        with pytest.raises(Exception):
            await v.validate_texts([])

    @pytest.mark.asyncio
    async def test_validate_result(self):
        v = EmbeddingValidator()
        result = await v.validate_result([0.1, 0.2], 2)
        assert result == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_validate_result_empty(self):
        v = EmbeddingValidator()
        with pytest.raises(InvalidResponseError):
            await v.validate_result([], 2)

    @pytest.mark.asyncio
    async def test_validate_result_dimension(self):
        v = EmbeddingValidator()
        with pytest.raises(DimensionMismatchError):
            await v.validate_result([0.1], 2)

    def test_exception_hierarchy(self):
        assert issubclass(EmptyTextError, ValueError)
        assert issubclass(TextTooLongError, ValueError)
        assert issubclass(DimensionMismatchError, ValueError)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestEmbeddingStatistics:
    def test_empty(self):
        s = EmbeddingStatistics()
        snap = s.snapshot()
        assert snap["total_embeddings"] == 0
        assert snap["average_latency_ms"] == 0.0

    def test_record(self):
        s = EmbeddingStatistics()
        s.record(count=5, tokens=100, latency=0.5, provider="local", batch_size=5)
        snap = s.snapshot()
        assert snap["total_embeddings"] == 5
        assert snap["total_tokens"] == 100
        assert snap["total_latency_sec"] == 0.5
        assert snap["provider_usage"] == {"local": 5}

    def test_multiple_records(self):
        s = EmbeddingStatistics()
        s.record(count=2, tokens=10, latency=0.1, provider="local", batch_size=2)
        s.record(count=3, tokens=20, latency=0.2, provider="openai", batch_size=3)
        snap = s.snapshot()
        assert snap["total_embeddings"] == 5
        assert snap["batch_count"] == 2
        assert snap["average_latency_ms"] > 0

    def test_error(self):
        s = EmbeddingStatistics()
        s.record_error()
        snap = s.snapshot()
        assert snap["errors"] == 1


# ---------------------------------------------------------------------------
# Batch Processor
# ---------------------------------------------------------------------------

class TestBatchProcessor:
    @pytest.mark.asyncio
    async def test_empty(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        bp = BatchProcessor(provider)
        results = await bp.process([])
        assert results == []

    @pytest.mark.asyncio
    async def test_single_batch(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        bp = BatchProcessor(provider, batch_size=10)
        results = await bp.process(["hello", "world"])
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_multiple_batches(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        bp = BatchProcessor(provider, batch_size=2)
        results = await bp.process(["a", "b", "c", "d", "e"])
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        class FlakyProvider:
            def __init__(self):
                self._call_count = 0

            @property
            def provider_name(self):
                return "flaky"

            @property
            def dimensions(self):
                return 4

            async def embed(self, texts, **kwargs):
                self._call_count += 1
                if self._call_count <= 2:
                    raise asyncio.TimeoutError("timeout")
                return [EmbeddingResult(vector=[0.1]*4, model="m", provider="f", dimensions=4)]

        bp = BatchProcessor(FlakyProvider(), max_retry=3, batch_size=10)
        results = await bp.process(["hello"])
        assert len(results) == 1
        assert results[0].vector == [0.1, 0.1, 0.1, 0.1]

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        class AlwaysFailProvider:
            @property
            def provider_name(self):
                return "fail"

            @property
            def dimensions(self):
                return 4

            async def embed(self, texts, **kwargs):
                raise RuntimeError("always fails")

        bp = BatchProcessor(AlwaysFailProvider(), max_retry=1)
        with pytest.raises(RuntimeError):
            await bp.process(["hello"])

    @pytest.mark.asyncio
    async def test_non_retryable_error(self):
        class BadRequestProvider:
            @property
            def provider_name(self):
                return "bad"

            @property
            def dimensions(self):
                return 4

            async def embed(self, texts, **kwargs):
                raise ValueError("invalid input")

        bp = BatchProcessor(BadRequestProvider(), max_retry=3)
        with pytest.raises(ValueError):
            await bp.process(["hello"])

    def test_make_batches(self):
        provider = LocalEmbeddingAdapter(dimensions=4)
        bp = BatchProcessor(provider, batch_size=3)
        batches = bp._make_batches(["a", "b", "c", "d", "e"], 3)
        assert len(batches) == 2
        assert batches[0] == ["a", "b", "c"]
        assert batches[1] == ["d", "e"]

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        class SlowProvider:
            @property
            def provider_name(self):
                return "slow"

            @property
            def dimensions(self):
                return 4

            async def embed(self, texts, **kwargs):
                await asyncio.sleep(10)
                return []

        bp = BatchProcessor(SlowProvider(), timeout=0.01, max_retry=0)
        with pytest.raises(RuntimeError):
            await bp.process(["hello"])


# ---------------------------------------------------------------------------
# EmbeddingService
# ---------------------------------------------------------------------------

@pytest.fixture
def svc_and_config():
    repo = InMemoryKnowledgeRepository()
    svc = KnowledgeService(repo)
    config = EmbeddingConfig(provider="local", dimensions=4, batch_size=10)
    return svc, config


class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_text(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)
        result = await es.embed_text("hello world")
        assert len(result.vector) == 4
        assert result.provider == "local"

    @pytest.mark.asyncio
    async def test_embed_texts(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)
        results = await es.embed_texts(["hello", "world"])
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_embed_text_validation(self, svc_and_config):
        svc, config = svc_and_config
        es = EmbeddingService(svc, config=config)
        with pytest.raises(Exception):
            await es.embed_text("")

    @pytest.mark.asyncio
    async def test_embed_chunks(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)

        coll = await svc.create_collection(name="c")
        doc = await svc.create_document(collection_id=coll.id, title="d", content="test content")
        chunk = KnowledgeChunk(document_id=doc.id, collection_id=coll.id, content="test content")

        records = await es.embed_chunks([chunk])
        assert len(records) == 1
        assert records[0].document_id == doc.id
        assert records[0].chunk_id == chunk.id
        assert len(records[0].vector) == 4

    @pytest.mark.asyncio
    async def test_cache_hit(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)

        r1 = await es.embed_text("hello")
        r2 = await es.embed_text("hello")
        assert r1.vector == r2.vector

    @pytest.mark.asyncio
    async def test_cache_disabled(self, svc_and_config):
        svc, config = svc_and_config
        config.cache_enabled = False
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)

        r1 = await es.embed_text("hello")
        r2 = await es.embed_text("hello")
        assert r1.vector == r2.vector

    @pytest.mark.asyncio
    async def test_get_statistics(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)

        await es.embed_text("hello")
        stats = await es.get_statistics()
        assert stats["total_embeddings"] >= 1
        assert "cache" in stats

    @pytest.mark.asyncio
    async def test_cache_stats(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)

        await es.embed_text("a")
        await es.embed_text("a")
        await es.embed_text("b")
        stats = await es.get_statistics()
        assert stats["cache"]["hits"] >= 1
        assert stats["cache"]["misses"] >= 2

    @pytest.mark.asyncio
    async def test_provider_property(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)
        assert es.provider is provider

    @pytest.mark.asyncio
    async def test_config_property(self, svc_and_config):
        svc, config = svc_and_config
        es = EmbeddingService(svc, config=config)
        assert es.config is config

    @pytest.mark.asyncio
    async def test_embed_texts_deterministic(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)

        r1 = await es.embed_texts(["hello", "world"])
        r2 = await es.embed_texts(["hello", "world"])
        assert r1[0].vector == r2[0].vector
        assert r1[1].vector == r2[1].vector


# ---------------------------------------------------------------------------
# SentenceTransformers Provider (optional)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not HAS_SENTENCE_TRANSFORMERS, reason="sentence_transformers not installed"
)
class TestSentenceTransformersProvider:
    @pytest.mark.asyncio
    async def test_embed_single(self):
        from app.knowledge.embedding.providers import SentenceTransformersAdapter
        provider = SentenceTransformersAdapter()
        results = await provider.embed(["hello world"])
        assert len(results) == 1
        assert len(results[0].vector) > 0
        assert results[0].provider == "sentence_transformers"

    @pytest.mark.asyncio
    async def test_embed_multiple(self):
        from app.knowledge.embedding.providers import SentenceTransformersAdapter
        provider = SentenceTransformersAdapter()
        results = await provider.embed(["hello", "world", "test"])
        assert len(results) == 3
        assert all(len(r.vector) > 0 for r in results)

    @pytest.mark.asyncio
    async def test_provider_name(self):
        from app.knowledge.embedding.providers import SentenceTransformersAdapter
        provider = SentenceTransformersAdapter()
        assert provider.provider_name == "sentence_transformers"

    @pytest.mark.asyncio
    async def test_factory_creates(self):
        import os
        os.environ["EMBEDDING_PROVIDER"] = "sentence_transformers"
        try:
            provider = create_embedding_provider("sentence_transformers")
            assert provider.provider_name == "sentence_transformers"
        finally:
            os.environ.pop("EMBEDDING_PROVIDER", None)

    @pytest.mark.asyncio
    async def test_raises_when_not_imported(self):
        from app.knowledge.embedding.providers import HAS_SENTENCE_TRANSFORMERS
        if HAS_SENTENCE_TRANSFORMERS:
            pytest.skip("sentence_transformers is installed")
        from app.knowledge.embedding.providers import SentenceTransformersAdapter
        provider = SentenceTransformersAdapter()
        with pytest.raises(RuntimeError):
            await provider.embed(["test"])


# ---------------------------------------------------------------------------
# Redis Embedding Cache (optional)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not HAS_REDIS, reason="redis not installed"
)
class TestRedisEmbeddingCache:
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        from app.knowledge.embedding.cache import RedisEmbeddingCache
        cache = RedisEmbeddingCache(ttl=60)
        await cache.set("k1", [0.1, 0.2, 0.3])
        val = await cache.get("k1")
        assert val == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_miss(self):
        from app.knowledge.embedding.cache import RedisEmbeddingCache
        cache = RedisEmbeddingCache(ttl=60)
        val = await cache.get("nonexistent")
        assert val is None

    @pytest.mark.asyncio
    async def test_clear(self):
        from app.knowledge.embedding.cache import RedisEmbeddingCache
        cache = RedisEmbeddingCache(ttl=60)
        await cache.set("k1", [0.1])
        await cache.clear()
        val = await cache.get("k1")
        assert val is None

    @pytest.mark.asyncio
    async def test_stats(self):
        from app.knowledge.embedding.cache import RedisEmbeddingCache
        cache = RedisEmbeddingCache(ttl=60)
        await cache.get("k1")
        stats = await cache.stats()
        assert stats["misses"] >= 1
        await cache.set("k1", [0.1])
        await cache.get("k1")
        stats = await cache.stats()
        assert stats["hits"] >= 1


# ---------------------------------------------------------------------------
# Repository embedding storage
# ---------------------------------------------------------------------------

class TestRepositoryEmbeddingStorage:
    @pytest.mark.asyncio
    async def test_save_and_get_embedding(self):
        repo = InMemoryKnowledgeRepository()
        rec = EmbeddingRecord(
            document_id="d1", chunk_id="c1",
            model="local", provider="local", dimensions=2,
            vector=[0.1, 0.2], token_count=5,
        )
        saved = await repo.save_embedding(rec)
        assert saved.id is not None
        fetched = await repo.get_embedding("c1")
        assert fetched is not None
        assert fetched.vector == [0.1, 0.2]
        assert fetched.document_id == "d1"

    @pytest.mark.asyncio
    async def test_get_missing_embedding(self):
        repo = InMemoryKnowledgeRepository()
        fetched = await repo.get_embedding("nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_embedding(self):
        repo = InMemoryKnowledgeRepository()
        rec = EmbeddingRecord(
            document_id="d1", chunk_id="c1",
            model="local", provider="local", dimensions=2,
            vector=[0.1, 0.2], token_count=5,
        )
        await repo.save_embedding(rec)
        deleted = await repo.delete_embedding("c1")
        assert deleted is True
        fetched = await repo.get_embedding("c1")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_missing(self):
        repo = InMemoryKnowledgeRepository()
        deleted = await repo.delete_embedding("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_list_embeddings(self):
        repo = InMemoryKnowledgeRepository()
        for i in range(3):
            rec = EmbeddingRecord(
                document_id="d1", chunk_id=f"c{i}",
                model="local", provider="local", dimensions=2,
                vector=[float(i), float(i)], token_count=5,
            )
            await repo.save_embedding(rec)
        all_emb = await repo.list_embeddings()
        assert len(all_emb) == 3

    @pytest.mark.asyncio
    async def test_list_embeddings_filtered(self):
        repo = InMemoryKnowledgeRepository()
        for i in range(3):
            rec = EmbeddingRecord(
                document_id=f"d{i}", chunk_id=f"c{i}",
                model="local", provider="local", dimensions=2,
                vector=[float(i), float(i)], token_count=5,
            )
            await repo.save_embedding(rec)
        filtered = await repo.list_embeddings(document_id="d1")
        assert len(filtered) == 1
        assert filtered[0].chunk_id == "c1"


# ---------------------------------------------------------------------------
# EmbeddingService get/delete delegation
# ---------------------------------------------------------------------------

class TestEmbeddingServiceDelegation:
    @pytest.mark.asyncio
    async def test_get_embedding(self, svc_and_config):
        svc, config = svc_and_config
        es = EmbeddingService(svc, config=config)
        result = await es.get_embedding("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_embedding_after_save(self, svc_and_config):
        svc, config = svc_and_config
        provider = LocalEmbeddingAdapter(dimensions=4)
        es = EmbeddingService(svc, config=config, provider=provider)
        chunk = KnowledgeChunk(
            id="test-chunk", document_id="test-doc",
            collection_id="test-coll", content="hello world",
        )
        records = await es.embed_chunks([chunk])
        assert len(records) == 1
        # Save to repo
        repo = svc._repo
        await repo.save_embedding(records[0])
        fetched = await es.get_embedding("test-chunk")
        assert fetched is not None
        assert fetched.vector == records[0].vector

    @pytest.mark.asyncio
    async def test_delete_embedding(self, svc_and_config):
        svc, config = svc_and_config
        repo = svc._repo
        rec = EmbeddingRecord(
            document_id="d1", chunk_id="c1",
            model="local", provider="local", dimensions=2,
            vector=[0.1, 0.2], token_count=5,
        )
        await repo.save_embedding(rec)
        es = EmbeddingService(svc, config=config)
        deleted = await es.delete_embedding("c1")
        assert deleted is True

    @pytest.mark.asyncio
    async def test_delete_missing(self, svc_and_config):
        svc, config = svc_and_config
        es = EmbeddingService(svc, config=config)
        deleted = await es.delete_embedding("nonexistent")
        assert deleted is False
