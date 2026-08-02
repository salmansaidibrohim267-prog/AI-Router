from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.memory.config import MemoryVectorConfig, MEMORY_TYPE_TTL_DAYS
from app.memory.dedup import MemoryDeduplicator
from app.memory.exceptions import (
    MemoryDuplicateError,
    MemoryError,
    MemoryExtractionError,
    MemoryLifecycleError,
    MemoryNotFoundError,
    MemoryScoringError,
    MemoryStorageError,
    MemorySummarizationError,
    MemoryTenantError,
    MemoryValidationError,
)
from app.memory.extractor import MemoryExtractor
from app.memory.lifecycle import MemoryLifecycleManager
from app.memory.logging import MemoryLogger
from app.memory.manager import MemoryManager
from app.memory.models import (
    ExtractedMemory,
    MemoryCategory,
    MemoryEventType,
    MemoryItem,
    MemoryMetrics,
    MemoryQuery,
    MemoryScope,
    MemorySearchResult,
    MemorySummary,
    MemoryType,
)
from app.memory.repository import MemoryRepository
from app.memory.scoring import MemoryScorer
from app.memory.statistics import MemoryMetricsTracker
from app.memory.summarizer import MemorySummarizer


# ============================================================
# Config
# ============================================================
class TestConfig:
    def test_defaults(self):
        c = MemoryVectorConfig()
        assert c.similarity_weight == 0.4
        assert c.namespace == "memory"
        assert c.max_entries == 10000

    def test_from_env(self):
        os.environ["MEMORY_NAMESPACE"] = "custom_ns"
        os.environ["MEMORY_TOP_K"] = "25"
        os.environ["MEMORY_ENABLE_TTL"] = "0"
        try:
            c = MemoryVectorConfig.from_env()
            assert c.namespace == "custom_ns"
            assert c.default_top_k == 25
            assert c.enable_ttl is False
        finally:
            for k in ["MEMORY_NAMESPACE", "MEMORY_TOP_K", "MEMORY_ENABLE_TTL"]:
                os.environ.pop(k, None)

    def test_type_ttl_map(self):
        assert MEMORY_TYPE_TTL_DAYS["persistent"] is None
        assert MEMORY_TYPE_TTL_DAYS["short_term"] == 1.0
        assert MEMORY_TYPE_TTL_DAYS["semantic"] == 180.0


# ============================================================
# Models
# ============================================================
class TestModels:
    def test_memory_type_values(self):
        assert MemoryType.SHORT_TERM.value == "short_term"
        assert MemoryType.SEMANTIC.value == "semantic"

    def test_memory_category_values(self):
        assert MemoryCategory.PREFERENCE.value == "preference"
        assert MemoryCategory.GENERAL.value == "general"

    def test_scope_filter_empty(self):
        s = MemoryScope()
        assert s.filter() == {}

    def test_scope_filter_full(self):
        s = MemoryScope(tenant_id="t1", workspace_id="w1", user_id="u1", session_id="s1")
        f = s.filter()
        assert f["tenant_id"] == "t1"
        assert f["user_id"] == "u1"

    def test_scope_bool(self):
        assert not MemoryScope()
        assert MemoryScope(user_id="u1")

    def test_scope_is_isolated(self):
        scope = MemoryScope(tenant_id="t1", user_id="u1")
        item = MemoryItem(id="x", content="c", tenant_id="t1", user_id="u1")
        assert scope.is_isolated(item)

    def test_scope_is_isolated_tenant_mismatch(self):
        scope = MemoryScope(tenant_id="t1")
        item = MemoryItem(id="x", content="c", tenant_id="t2")
        assert not scope.is_isolated(item)

    def test_memory_item_defaults(self):
        item = MemoryItem(content="hello")
        assert item.id
        assert item.memory_type == MemoryType.SHORT_TERM
        assert item.category == MemoryCategory.GENERAL
        assert item.importance == 0.5
        assert item.created_at > 0
        assert item.deleted is False

    def test_memory_item_to_dict(self):
        item = MemoryItem(id="abc", content="hello", memory_type=MemoryType.LONG_TERM, category=MemoryCategory.GOAL)
        d = item.to_dict()
        assert d["id"] == "abc"
        assert d["memory_type"] == "long_term"
        assert d["category"] == "goal"

    def test_memory_item_from_dict(self):
        data = {
            "id": "abc",
            "content": "hello",
            "memory_type": "episodic",
            "category": "task",
            "created_at": 123.0,
            "last_accessed_at": 124.0,
            "last_updated_at": 125.0,
        }
        item = MemoryItem.from_dict(data)
        assert item.id == "abc"
        assert item.memory_type == MemoryType.EPISODIC
        assert item.category == MemoryCategory.TASK
        assert item.created_at == 123.0

    def test_memory_item_touch(self):
        item = MemoryItem(content="c")
        item.touch()
        assert item.access_count == 1

    def test_extracted_memory_to_dict(self):
        em = ExtractedMemory(content="x", category=MemoryCategory.GOAL, confidence=0.9)
        d = em.to_dict()
        assert d["category"] == "goal"
        assert d["confidence"] == 0.9

    def test_memory_query_defaults(self):
        q = MemoryQuery()
        assert q.top_k == 10
        assert q.memory_types == []

    def test_memory_search_result_to_dict(self):
        r = MemorySearchResult(item=MemoryItem(content="c"), score=0.5, similarity=0.4)
        d = r.to_dict()
        assert d["score"] == 0.5
        assert d["components"]["similarity"] == 0.4

    def test_memory_summary_to_dict(self):
        s = MemorySummary(text="summary", entries_count=3, categories={"fact": 2})
        d = s.to_dict()
        assert d["entries_count"] == 3

    def test_memory_metrics_to_dict(self):
        m = MemoryMetrics(total_ops=5)
        d = m.to_dict()
        assert d["total_ops"] == 5


# ============================================================
# Exceptions
# ============================================================
class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(MemoryNotFoundError, MemoryError)
        assert issubclass(MemoryValidationError, MemoryError)
        assert issubclass(MemoryStorageError, MemoryError)
        assert issubclass(MemoryExtractionError, MemoryError)
        assert issubclass(MemoryScoringError, MemoryError)
        assert issubclass(MemoryLifecycleError, MemoryError)
        assert issubclass(MemorySummarizationError, MemoryError)
        assert issubclass(MemoryDuplicateError, MemoryError)
        assert issubclass(MemoryTenantError, MemoryError)


# ============================================================
# MemoryExtractor
# ============================================================
class TestExtractor:
    def test_extract_empty(self):
        ex = MemoryExtractor()
        assert ex.extract("") == []
        assert ex.extract("   ") == []

    def test_extract_preference(self):
        ex = MemoryExtractor()
        memories = ex.extract("I like dark chocolate")
        assert any(m.category == MemoryCategory.PREFERENCE for m in memories)

    def test_extract_goal(self):
        ex = MemoryExtractor()
        memories = ex.extract("I want to learn piano")
        assert any(m.category == MemoryCategory.GOAL for m in memories)

    def test_extract_fact(self):
        ex = MemoryExtractor()
        memories = ex.extract("My name is Alice")
        assert any(m.category == MemoryCategory.FACT for m in memories)

    def test_extract_decision(self):
        ex = MemoryExtractor()
        memories = ex.extract("I decided to buy a house")
        assert any(m.category == MemoryCategory.DECISION for m in memories)

    def test_extract_constraint(self):
        ex = MemoryExtractor()
        memories = ex.extract("I cannot eat gluten")
        assert any(m.category == MemoryCategory.CONSTRAINT for m in memories)

    def test_extract_task(self):
        ex = MemoryExtractor()
        memories = ex.extract("I need to submit the report")
        assert any(m.category == MemoryCategory.TASK for m in memories)

    def test_extract_entity(self):
        ex = MemoryExtractor()
        memories = ex.extract("Alice works at Acme Corp")
        entities = [m for m in memories if m.category == MemoryCategory.ENTITY]
        assert any("Alice" in e.content for e in entities)

    def test_extract_entity_excludes_stopwords(self):
        ex = MemoryExtractor()
        memories = ex.extract("The quick brown fox")
        entities = [m for m in memories if m.category == MemoryCategory.ENTITY]
        assert not any("The" in e.content for e in entities)

    def test_extract_multiple(self):
        ex = MemoryExtractor()
        memories = ex.extract("I prefer coffee. I want to travel to Japan. I decided to move.")
        categories = {m.category for m in memories}
        assert MemoryCategory.PREFERENCE in categories
        assert MemoryCategory.GOAL in categories
        assert MemoryCategory.DECISION in categories

    def test_extract_with_custom_func(self):
        ex = MemoryExtractor(extraction_func=lambda text: [ExtractedMemory(content="custom", category=MemoryCategory.FACT)])
        memories = ex.extract("anything")
        assert len(memories) == 1
        assert memories[0].content == "custom"

    def test_extract_with_custom_func_str(self):
        ex = MemoryExtractor(extraction_func=lambda text: "just a string")
        memories = ex.extract("anything")
        assert len(memories) == 1
        assert memories[0].content == "just a string"

    def test_extract_with_custom_func_dict(self):
        ex = MemoryExtractor(
            extraction_func=lambda text: [{"content": "d", "category": "goal", "confidence": 0.7, "importance": 0.6}]
        )
        memories = ex.extract("anything")
        assert memories[0].category == MemoryCategory.GOAL
        assert memories[0].confidence == 0.7

    def test_extract_custom_func_error(self):
        ex = MemoryExtractor(extraction_func=lambda text: 1 / 0)
        with pytest.raises(MemoryExtractionError):
            ex.extract("anything")

    def test_extract_importance_by_category(self):
        ex = MemoryExtractor()
        goal = ex._importance_for(MemoryCategory.GOAL)
        general = ex._importance_for(MemoryCategory.GENERAL)
        assert goal > general

    def test_extract_confidence_by_category(self):
        ex = MemoryExtractor()
        decision = ex._confidence_for(MemoryCategory.DECISION)
        general = ex._confidence_for(MemoryCategory.GENERAL)
        assert decision > general


# ============================================================
# MemoryScorer
# ============================================================
class TestScorer:
    def test_score_basic(self):
        scorer = MemoryScorer()
        item = MemoryItem(content="c")
        result = scorer.score(item, similarity=0.9)
        assert result.score > 0
        assert result.similarity == 0.9
        assert result.importance == 0.5

    def test_recency_score_fresh(self):
        scorer = MemoryScorer()
        item = MemoryItem(content="c")
        assert scorer.recency_score(item) > 0.9

    def test_recency_score_old(self):
        scorer = MemoryScorer()
        item = MemoryItem(content="c")
        item.last_accessed_at = time.time() - 30 * 86400
        score = scorer.recency_score(item, time.time())
        assert score < 0.1

    def test_recency_score_halflife_zero(self):
        scorer = MemoryScorer(config=MemoryVectorConfig(recency_halflife_days=0))
        item = MemoryItem(content="c")
        assert scorer.recency_score(item) == 1.0

    def test_access_score_zero(self):
        scorer = MemoryScorer()
        item = MemoryItem(content="c")
        assert scorer.access_score(item) == 0.0

    def test_access_score_growth(self):
        scorer = MemoryScorer()
        item = MemoryItem(content="c", access_count=100)
        assert scorer.access_score(item) > 0.9

    def test_combine_weighted(self):
        scorer = MemoryScorer()
        result = MemorySearchResult(
            item=MemoryItem(content="c"),
            similarity=1.0, recency=1.0, access=1.0, importance=1.0, confidence=1.0,
        )
        assert scorer.combine(result) == pytest.approx(1.0)

    def test_combine_zero_weights(self):
        scorer = MemoryScorer(config=MemoryVectorConfig(
            similarity_weight=0, recency_weight=0, access_weight=0,
            importance_weight=0, confidence_weight=0,
        ))
        result = MemorySearchResult(item=MemoryItem(content="c"))
        assert scorer.combine(result) == 0.0

    def test_boost(self):
        scorer = MemoryScorer()
        item = MemoryItem(content="c", importance=0.5)
        boosted = scorer.boost(item, 1.5)
        assert boosted.importance == 0.75

    def test_boost_caps_at_one(self):
        scorer = MemoryScorer()
        item = MemoryItem(content="c", importance=0.9)
        boosted = scorer.boost(item, 2.0)
        assert boosted.importance == 1.0

    def test_decay(self):
        scorer = MemoryScorer()
        item = MemoryItem(content="c", importance=0.8, confidence=0.9)
        decayed = scorer.decay(item, 0.5)
        assert decayed.importance == 0.4
        assert decayed.confidence == 0.45

    def test_score_error_wrapped(self):
        scorer = MemoryScorer()
        with patch.object(scorer, "recency_score", side_effect=ValueError("boom")):
            with pytest.raises(MemoryScoringError):
                scorer.score(MemoryItem(content="c"))


# ============================================================
# MemoryDeduplicator
# ============================================================
class TestDedup:
    def make_item(self, content):
        return MemoryItem(content=content)

    def test_find_duplicate(self):
        d = MemoryDeduplicator(config=MemoryVectorConfig(dedup_similarity_threshold=0.5))
        candidates = [self.make_item("the quick brown fox jumps")]
        dup = d.find_duplicate("the quick brown fox jumps", candidates)
        assert dup is not None

    def test_find_duplicate_none(self):
        d = MemoryDeduplicator()
        candidates = [self.make_item("completely different topic")]
        dup = d.find_duplicate("totally unrelated subject", candidates)
        assert dup is None

    def test_find_duplicate_empty_content(self):
        d = MemoryDeduplicator()
        assert d.find_duplicate("", [self.make_item("x")]) is None

    def test_deduplicate_removes(self):
        d = MemoryDeduplicator(config=MemoryVectorConfig(dedup_similarity_threshold=0.5))
        items = [
            self.make_item("the quick brown fox jumps over"),
            self.make_item("the quick brown fox jumps over the dog"),
            self.make_item("unrelated memory here"),
        ]
        unique = d.deduplicate(items)
        assert len(unique) == 2

    def test_deduplicate_enforce_raises(self):
        d = MemoryDeduplicator(config=MemoryVectorConfig(dedup_similarity_threshold=0.5))
        items = [
            self.make_item("the quick brown fox"),
            self.make_item("the quick brown fox runs"),
        ]
        with pytest.raises(MemoryDuplicateError):
            d.deduplicate(items, enforce=True)

    def test_overlap(self):
        d = MemoryDeduplicator()
        assert d._overlap({"a", "b"}, "a b c") == 1.0
        assert d._overlap({"a", "b"}, "c d") == 0.0
        assert d._overlap({"a", "b"}, "") == 0.0


# ============================================================
# MemoryRepository
# ============================================================
class TestRepository:
    def make_item(self, cid, content, tenant="t1", user="u1", session="s1"):
        return MemoryItem(
            id=cid, content=content,
            tenant_id=tenant, user_id=user, session_id=session,
        )

    @pytest.mark.asyncio
    async def test_store_and_get(self):
        repo = MemoryRepository()
        item = self.make_item("m1", "hello")
        await repo.store(item)
        assert repo.get("m1").content == "hello"

    @pytest.mark.asyncio
    async def test_store_empty_content_raises(self):
        repo = MemoryRepository()
        with pytest.raises(MemoryStorageError):
            await repo.store(MemoryItem(id="m1", content="  "))

    @pytest.mark.asyncio
    async def test_store_batch(self):
        repo = MemoryRepository()
        items = [self.make_item(f"m{i}", f"content {i}") for i in range(3)]
        results = await repo.store_batch(items)
        assert len(results) == 3

    def test_get_missing(self):
        repo = MemoryRepository()
        assert repo.get("nope") is None

    def test_get_deleted(self):
        repo = MemoryRepository()
        item = self.make_item("m1", "hello")
        repo._items["m1"] = item
        item.deleted = True
        assert repo.get("m1") is None

    def test_list_scope_isolation(self):
        repo = MemoryRepository()
        repo._items["m1"] = self.make_item("m1", "a", tenant="t1")
        repo._items["m2"] = self.make_item("m2", "b", tenant="t2")
        scope = MemoryScope(tenant_id="t1")
        items = repo.list(scope)
        assert len(items) == 1
        assert items[0].id == "m1"

    def test_list_memory_types(self):
        repo = MemoryRepository()
        repo._items["m1"] = MemoryItem(id="m1", content="a", memory_type=MemoryType.LONG_TERM)
        repo._items["m2"] = MemoryItem(id="m2", content="b", memory_type=MemoryType.SESSION)
        items = repo.list(MemoryScope(), memory_types=[MemoryType.LONG_TERM])
        assert len(items) == 1

    def test_list_sorted_by_access(self):
        repo = MemoryRepository()
        item_a = self.make_item("a", "x")
        item_b = self.make_item("b", "y")
        item_a.last_accessed_at = 100.0
        item_b.last_accessed_at = 200.0
        repo._items["a"] = item_a
        repo._items["b"] = item_b
        items = repo.list(MemoryScope())
        assert items[0].id == "b"

    def test_all(self):
        repo = MemoryRepository()
        repo._items["m1"] = self.make_item("m1", "a")
        repo._items["m2"] = self.make_item("m2", "b")
        assert len(repo.all()) == 2

    def test_count(self):
        repo = MemoryRepository()
        repo._items["m1"] = self.make_item("m1", "a")
        repo._items["m2"] = self.make_item("m2", "b", tenant="t2")
        assert repo.count(MemoryScope(tenant_id="t1")) == 1
        assert repo.count() == 2

    @pytest.mark.asyncio
    async def test_update(self):
        repo = MemoryRepository()
        item = self.make_item("m1", "hello")
        await repo.store(item)
        item.content = "updated"
        await repo.update(item)
        assert repo.get("m1").content == "updated"

    @pytest.mark.asyncio
    async def test_update_missing(self):
        repo = MemoryRepository()
        with pytest.raises(MemoryStorageError):
            await repo.update(self.make_item("ghost", "x"))

    @pytest.mark.asyncio
    async def test_update_tenant_change(self):
        repo = MemoryRepository()
        item = self.make_item("m1", "hello", tenant="t1")
        await repo.store(item)
        item.tenant_id = "t2"
        with pytest.raises(MemoryTenantError):
            await repo.update(item)

    @pytest.mark.asyncio
    async def test_delete(self):
        repo = MemoryRepository()
        item = self.make_item("m1", "hello")
        await repo.store(item)
        assert await repo.delete("m1") is True
        assert repo.get("m1") is None

    @pytest.mark.asyncio
    async def test_delete_missing(self):
        repo = MemoryRepository()
        assert await repo.delete("ghost") is False

    @pytest.mark.asyncio
    async def test_search_metadata_only(self):
        repo = MemoryRepository()
        await repo.store_batch([
            self.make_item("m1", "user loves coffee"),
            self.make_item("m2", "user hates tea"),
        ])
        results = await repo.search("coffee", MemoryScope(tenant_id="t1"), top_k=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_with_embedder(self):
        repo = MemoryRepository()
        repo._embedder = AsyncMock(return_value=[0.1] * 4)
        repo._items["m1"] = self.make_item("m1", "a", tenant="t1")
        repo._items["m1"].embedding = [0.1] * 4
        results = await repo.search("q", MemoryScope(tenant_id="t1"), top_k=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_with_vector_store(self):
        vs = AsyncMock()
        vs.search = AsyncMock(return_value=[
            MagicMock(id="m1", score=0.9),
        ])
        repo = MemoryRepository(vector_store=vs)
        repo._embedder = AsyncMock(return_value=[0.5] * 4)
        repo._items["m1"] = self.make_item("m1", "a", tenant="t1")
        results = await repo.search("q", MemoryScope(tenant_id="t1"), top_k=5)
        assert len(results) == 1
        assert results[0].similarity == 0.9

    @pytest.mark.asyncio
    async def test_search_with_vector_store_error(self):
        vs = AsyncMock()
        vs.search = AsyncMock(side_effect=ValueError("vs down"))
        repo = MemoryRepository(vector_store=vs)
        repo._embedder = AsyncMock(return_value=[0.5] * 4)
        repo._items["m1"] = self.make_item("m1", "a", tenant="t1")
        results = await repo.search("q", MemoryScope(tenant_id="t1"), top_k=5)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_memory_types_filter(self):
        repo = MemoryRepository()
        await repo.store_batch([
            MemoryItem(id="m1", content="a", memory_type=MemoryType.LONG_TERM),
            MemoryItem(id="m2", content="b", memory_type=MemoryType.SESSION),
        ])
        results = await repo.search("x", MemoryScope(), top_k=5, memory_types=[MemoryType.LONG_TERM])
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_embedder_error(self):
        repo = MemoryRepository()
        repo._embedder = AsyncMock(side_effect=ValueError("no embed"))
        repo._items["m1"] = self.make_item("m1", "a", tenant="t1")
        results = await repo.search("q", MemoryScope(tenant_id="t1"), top_k=5)
        assert len(results) == 1

    def test_find_duplicate_repo(self):
        repo = MemoryRepository()
        repo._items["m1"] = self.make_item("m1", "the quick brown fox")
        dup = repo.find_duplicate("the quick brown fox")
        assert dup is not None
        assert dup.id == "m1"

    def test_find_duplicate_none(self):
        repo = MemoryRepository()
        repo._items["m1"] = self.make_item("m1", "alpha beta")
        assert repo.find_duplicate("gamma delta") is None

    @pytest.mark.asyncio
    async def test_store_with_vector_store(self):
        vs = AsyncMock()
        vs.upsert = AsyncMock(return_value=None)
        repo = MemoryRepository(vector_store=vs)
        item = self.make_item("m1", "hello")
        item.embedding = [0.1, 0.2]
        await repo.store(item)
        vs.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_vector_store_error(self):
        vs = AsyncMock()
        vs.upsert = AsyncMock(side_effect=ValueError("up down"))
        repo = MemoryRepository(vector_store=vs)
        item = self.make_item("m1", "hello")
        item.embedding = [0.1, 0.2]
        await repo.store(item)
        assert repo.get("m1") is not None


# ============================================================
# Lifecycle
# ============================================================
class TestLifecycle:
    def make_repo(self):
        return MemoryRepository()

    @pytest.mark.asyncio
    async def test_check_ttl_expired(self):
        lc = MemoryLifecycleManager()
        item = MemoryItem(content="c", memory_type=MemoryType.SHORT_TERM)
        item.created_at = time.time() - 5 * 86400
        assert await lc.check_ttl(item) is True

    @pytest.mark.asyncio
    async def test_check_ttl_fresh(self):
        lc = MemoryLifecycleManager()
        item = MemoryItem(content="c", memory_type=MemoryType.LONG_TERM)
        item.created_at = time.time()
        assert await lc.check_ttl(item) is False

    @pytest.mark.asyncio
    async def test_check_ttl_persistent_never(self):
        lc = MemoryLifecycleManager()
        item = MemoryItem(content="c", memory_type=MemoryType.PERSISTENT)
        item.created_at = time.time() - 9999 * 86400
        assert await lc.check_ttl(item) is False

    @pytest.mark.asyncio
    async def test_check_ttl_disabled(self):
        lc = MemoryLifecycleManager(config=MemoryVectorConfig(enable_ttl=False))
        item = MemoryItem(content="c", memory_type=MemoryType.SHORT_TERM)
        item.created_at = time.time() - 999 * 86400
        assert await lc.check_ttl(item) is False

    @pytest.mark.asyncio
    async def test_check_ttl_metadata_override(self):
        lc = MemoryLifecycleManager()
        item = MemoryItem(content="c", memory_type=MemoryType.LONG_TERM, metadata={"ttl_days": 0.0001})
        item.created_at = time.time() - 86400
        assert await lc.check_ttl(item) is True

    @pytest.mark.asyncio
    async def test_run_maintenance_expires(self):
        repo = self.make_repo()
        lc = MemoryLifecycleManager(repository=repo)
        item = MemoryItem(id="m1", content="c", memory_type=MemoryType.SHORT_TERM)
        item.created_at = time.time() - 5 * 86400
        repo._items["m1"] = item
        result = await lc.run_maintenance(MemoryScope())
        assert "m1" in result["expired"]
        assert item.deleted is True

    @pytest.mark.asyncio
    async def test_run_maintenance_archives(self):
        repo = self.make_repo()
        lc = MemoryLifecycleManager(repository=repo)
        item = MemoryItem(id="m1", content="c", memory_type=MemoryType.PERSISTENT)
        item.last_accessed_at = time.time() - 200 * 86400
        repo._items["m1"] = item
        result = await lc.run_maintenance(MemoryScope())
        assert "m1" in result["archived"]
        assert item.archived is True

    @pytest.mark.asyncio
    async def test_run_maintenance_prunes(self):
        repo = self.make_repo()
        lc = MemoryLifecycleManager(
            repository=repo,
            config=MemoryVectorConfig(max_entries=2, prune_batch_size=10),
        )
        for i in range(5):
            item = MemoryItem(id=f"m{i}", content=f"c{i}", importance=0.1 + i * 0.01)
            repo._items[f"m{i}"] = item
        result = await lc.run_maintenance(MemoryScope())
        assert len(result["pruned"]) == 3
        assert "m0" in result["pruned"]

    @pytest.mark.asyncio
    async def test_run_maintenance_gc_archived(self):
        repo = self.make_repo()
        lc = MemoryLifecycleManager(repository=repo)
        item = MemoryItem(id="m1", content="c")
        item.last_accessed_at = time.time() - 400 * 86400
        repo._items["m1"] = item
        result = await lc.run_maintenance(MemoryScope())
        assert "m1" in result["archived"]
        assert "m1" not in repo._items

    def test_prune_under_limit(self):
        lc = MemoryLifecycleManager()
        items = [MemoryItem(id=f"m{i}", content=f"c{i}") for i in range(3)]
        assert lc._prune(items) == []

    def test_prune_disabled(self):
        lc = MemoryLifecycleManager(config=MemoryVectorConfig(enable_pruning=False))
        items = [MemoryItem(id=f"m{i}", content=f"c{i}") for i in range(5)]
        assert lc._prune(items) == []

    @pytest.mark.asyncio
    async def test_compact_merges(self):
        repo = self.make_repo()
        lc = MemoryLifecycleManager(repository=repo)
        repo._items["a"] = MemoryItem(id="a", content="the quick brown fox jumps", importance=0.5)
        repo._items["b"] = MemoryItem(id="b", content="the quick brown fox runs fast", importance=0.6)
        repo._items["c"] = MemoryItem(id="c", content="completely unrelated", importance=0.9)
        merged = await lc.compact(MemoryScope(), threshold=0.5)
        assert len(merged) == 2

    @pytest.mark.asyncio
    async def test_compact_disabled(self):
        lc = MemoryLifecycleManager(config=MemoryVectorConfig(enable_compaction=False))
        assert await lc.compact(MemoryScope()) == []

    def test_similarity(self):
        lc = MemoryLifecycleManager()
        assert lc._similarity("a b c", "a b c d") == 1.0
        assert lc._similarity("a b c", "d e f") == 0.0
        assert lc._similarity("", "x") == 0.0

    def test_merge(self):
        lc = MemoryLifecycleManager()
        a = MemoryItem(id="a", content="first", importance=0.5, confidence=0.5, access_count=1)
        b = MemoryItem(id="b", content="second", importance=0.9, confidence=0.8, access_count=3)
        merged = lc._merge(a, b)
        assert merged.id == "a"
        assert "first" in merged.content and "second" in merged.content
        assert merged.importance == 0.9
        assert merged.access_count == 4

    @pytest.mark.asyncio
    async def test_run_maintenance_error_wrapped(self):
        repo = MagicMock()
        repo.list = MagicMock(side_effect=ValueError("boom"))
        lc = MemoryLifecycleManager(repository=repo)
        with pytest.raises(MemoryLifecycleError):
            await lc.run_maintenance(MemoryScope())


# ============================================================
# MemorySummarizer
# ============================================================
class TestSummarizer:
    def make_items(self):
        return [
            MemoryItem(content="user likes coffee", category=MemoryCategory.PREFERENCE, importance=0.7),
            MemoryItem(content="user wants a dog", category=MemoryCategory.GOAL, importance=0.9),
            MemoryItem(content="project deadline is Friday", category=MemoryCategory.FACT, importance=0.6),
        ]

    @pytest.mark.asyncio
    async def test_summarize_empty(self):
        s = MemorySummarizer()
        assert await s.summarize([]) == ""

    @pytest.mark.asyncio
    async def test_summarize_concise(self):
        s = MemorySummarizer()
        text = await s.summarize(self.make_items())
        assert "coffee" in text
        assert "dog" in text

    @pytest.mark.asyncio
    async def test_summarize_key_points(self):
        s = MemorySummarizer()
        text = await s.summarize(self.make_items(), style="key_points")
        assert "Key memories" in text

    @pytest.mark.asyncio
    async def test_summarize_grouped(self):
        s = MemorySummarizer()
        text = await s.summarize(self.make_items(), style="grouped")
        assert "Preference" in text
        assert "Goal" in text

    @pytest.mark.asyncio
    async def test_summarize_custom_sync_func(self):
        s = MemorySummarizer(summarizer_func=lambda items, style="concise": "custom summary")
        text = await s.summarize(self.make_items())
        assert text == "custom summary"

    @pytest.mark.asyncio
    async def test_summarize_custom_async_func(self):
        async def func(items, style="concise"):
            return "async summary"

        s = MemorySummarizer(summarizer_func=func)
        text = await s.summarize(self.make_items())
        assert text == "async summary"

    @pytest.mark.asyncio
    async def test_summarize_error_wrapped(self):
        s = MemorySummarizer(summarizer_func=lambda items, style="concise": 1 / 0)
        with pytest.raises(MemorySummarizationError):
            await s.summarize(self.make_items())

    @pytest.mark.asyncio
    async def test_summarize_sorts_by_importance(self):
        s = MemorySummarizer()
        text = await s.summarize(self.make_items())
        assert text.index("dog") < text.index("coffee")


# ============================================================
# MemoryLogger
# ============================================================
class TestLogger:
    def test_log_event(self, caplog):
        import logging
        logger = MemoryLogger("test_mem_logger")
        logger._logger.setLevel(logging.INFO)
        logger.log_event(MemoryEventType.STORE, MemoryItem(content="c"))
        assert len(caplog.records) >= 0

    def test_log_event_without_item(self, caplog):
        import logging
        logger = MemoryLogger("test_mem_logger2")
        logger._logger.setLevel(logging.INFO)
        logger.log_event(MemoryEventType.RETRIEVE)
        assert len(caplog.records) >= 0

    def test_log_error(self, caplog):
        import logging
        logger = MemoryLogger("test_mem_logger3")
        logger._logger.setLevel(logging.INFO)
        logger.log_error(ValueError("boom"), "store")
        assert len(caplog.records) >= 0

    def test_log_disabled(self):
        import logging
        logger = MemoryLogger("test_disabled_mem")
        logger._logger.setLevel(logging.WARNING)
        logger.log_event(MemoryEventType.STORE, MemoryItem(content="c"))


# ============================================================
# MemoryMetricsTracker
# ============================================================
class TestMetrics:
    def test_initial(self):
        mt = MemoryMetricsTracker()
        assert mt.get_metrics().total_ops == 0

    def test_record_store(self):
        mt = MemoryMetricsTracker()
        mt.record(MemoryEventType.STORE, 10.0)
        m = mt.get_metrics()
        assert m.total_stores == 1
        assert m.stored_items == 1
        assert m.total_latency_ms == 10.0

    def test_record_delete(self):
        mt = MemoryMetricsTracker()
        mt.record(MemoryEventType.STORE)
        mt.record(MemoryEventType.DELETE)
        assert mt.get_metrics().total_deletes == 1
        assert mt.get_metrics().stored_items == 0

    def test_record_retrieve_update(self):
        mt = MemoryMetricsTracker()
        mt.record(MemoryEventType.RETRIEVE)
        mt.record(MemoryEventType.UPDATE)
        m = mt.get_metrics()
        assert m.total_retrieves == 1
        assert m.total_updates == 1

    def test_record_archive_prune_compact(self):
        mt = MemoryMetricsTracker()
        mt.record(MemoryEventType.ARCHIVE)
        mt.record(MemoryEventType.PRUNE)
        mt.record(MemoryEventType.COMPACT)
        m = mt.get_metrics()
        assert m.total_archives == 1
        assert m.total_prunes == 1
        assert m.total_compactions == 1

    def test_record_search(self):
        mt = MemoryMetricsTracker()
        mt.record_search(5.0)
        assert mt.get_metrics().total_searches == 1

    def test_record_extraction_summarization(self):
        mt = MemoryMetricsTracker()
        mt.record_extraction()
        mt.record_summarization()
        m = mt.get_metrics()
        assert m.total_extractions == 1
        assert m.total_summarizations == 1

    def test_record_error(self):
        mt = MemoryMetricsTracker()
        mt.record_error()
        assert mt.get_metrics().errors == 1

    def test_get_metrics_dict(self):
        mt = MemoryMetricsTracker()
        mt.record(MemoryEventType.STORE)
        d = mt.get_metrics_dict()
        assert d["total_stores"] == 1

    def test_reset(self):
        mt = MemoryMetricsTracker()
        mt.record(MemoryEventType.STORE)
        mt.reset()
        assert mt.get_metrics().total_ops == 0

    def test_uptime(self):
        mt = MemoryMetricsTracker()
        assert mt.uptime_seconds() >= 0


# ============================================================
# MemoryManager
# ============================================================
class TestManager:
    def make_scope(self, **kwargs):
        defaults = dict(tenant_id="t1", user_id="u1")
        defaults.update(kwargs)
        return MemoryScope(**defaults)

    @pytest.mark.asyncio
    async def test_store(self):
        mgr = MemoryManager()
        item = await mgr.store("user loves coffee", scope=self.make_scope())
        assert item.id
        assert item.tenant_id == "t1"

    @pytest.mark.asyncio
    async def test_store_empty_raises(self):
        mgr = MemoryManager()
        with pytest.raises(MemoryValidationError):
            await mgr.store("   ", scope=self.make_scope())

    @pytest.mark.asyncio
    async def test_store_dedup_merges(self):
        mgr = MemoryManager()
        await mgr.store("the user loves coffee in the morning", scope=self.make_scope())
        item2 = await mgr.store("the user loves coffee in the morning every day", scope=self.make_scope())
        assert mgr._repository.count() == 1
        assert item2.id

    @pytest.mark.asyncio
    async def test_store_with_embedder(self):
        mgr = MemoryManager()
        mgr._repository._embedder = AsyncMock(return_value=[0.1] * 4)
        item = await mgr.store("hello", scope=self.make_scope())
        assert item.embedding == [0.1] * 4

    @pytest.mark.asyncio
    async def test_store_with_embedder_error(self):
        mgr = MemoryManager()
        mgr._repository._embedder = AsyncMock(side_effect=ValueError("embed fail"))
        item = await mgr.store("hello", scope=self.make_scope())
        assert item.embedding is None

    @pytest.mark.asyncio
    async def test_store_clamps_importance(self):
        mgr = MemoryManager()
        item = await mgr.store("x", scope=self.make_scope(), importance=5.0)
        assert item.importance == 1.0

    @pytest.mark.asyncio
    async def test_retrieve(self):
        mgr = MemoryManager()
        await mgr.store("a", scope=self.make_scope())
        await mgr.store("b", scope=self.make_scope())
        items = await mgr.retrieve(self.make_scope())
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_retrieve_scoped(self):
        mgr = MemoryManager()
        await mgr.store("a", scope=self.make_scope())
        await mgr.store("b", scope=self.make_scope(user_id="u2"))
        items = await mgr.retrieve(self.make_scope())
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_retrieve_touches(self):
        mgr = MemoryManager()
        await mgr.store("a", scope=self.make_scope())
        item = (await mgr.retrieve(self.make_scope()))[0]
        assert item.access_count == 1

    @pytest.mark.asyncio
    async def test_retrieve_memory_types(self):
        mgr = MemoryManager()
        await mgr.store("a", scope=self.make_scope(), memory_type=MemoryType.LONG_TERM)
        await mgr.store("b", scope=self.make_scope(), memory_type=MemoryType.SESSION)
        items = await mgr.retrieve(self.make_scope(), memory_types=[MemoryType.LONG_TERM])
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_update(self):
        mgr = MemoryManager()
        item = await mgr.store("original", scope=self.make_scope())
        updated = await mgr.update(item.id, content="new content", importance=0.9)
        assert updated.content == "new content"
        assert updated.importance == 0.9

    @pytest.mark.asyncio
    async def test_update_missing(self):
        mgr = MemoryManager()
        with pytest.raises(MemoryNotFoundError):
            await mgr.update("ghost", content="x")

    @pytest.mark.asyncio
    async def test_update_empty_content(self):
        mgr = MemoryManager()
        item = await mgr.store("x", scope=self.make_scope())
        with pytest.raises(MemoryValidationError):
            await mgr.update(item.id, content="  ")

    @pytest.mark.asyncio
    async def test_update_metadata(self):
        mgr = MemoryManager()
        item = await mgr.store("x", scope=self.make_scope())
        updated = await mgr.update(item.id, metadata={"extra": "value"})
        assert updated.metadata["extra"] == "value"

    @pytest.mark.asyncio
    async def test_delete(self):
        mgr = MemoryManager()
        item = await mgr.store("x", scope=self.make_scope())
        assert await mgr.delete(item.id) is True
        assert await mgr.retrieve(self.make_scope()) == []

    @pytest.mark.asyncio
    async def test_delete_missing(self):
        mgr = MemoryManager()
        assert await mgr.delete("ghost") is False

    @pytest.mark.asyncio
    async def test_summarize(self):
        mgr = MemoryManager()
        await mgr.store("user likes coffee", scope=self.make_scope(), category=MemoryCategory.PREFERENCE)
        await mgr.store("user wants a dog", scope=self.make_scope(), category=MemoryCategory.GOAL)
        summary = await mgr.summarize(self.make_scope())
        assert isinstance(summary, MemorySummary)
        assert summary.entries_count == 2
        assert "coffee" in summary.text
        assert summary.categories["preference"] == 1

    @pytest.mark.asyncio
    async def test_summarize_empty(self):
        mgr = MemoryManager()
        summary = await mgr.summarize(self.make_scope())
        assert summary.entries_count == 0

    @pytest.mark.asyncio
    async def test_search(self):
        mgr = MemoryManager()
        await mgr.store("user loves coffee", scope=self.make_scope())
        results = await mgr.search(text="coffee", scope=self.make_scope())
        assert len(results) >= 1
        assert results[0].item.content == "user loves coffee"

    @pytest.mark.asyncio
    async def test_search_with_min_score(self):
        mgr = MemoryManager()
        await mgr.store("user loves coffee", scope=self.make_scope())
        results = await mgr.search(
            MemoryQuery(text="coffee", scope=self.make_scope(), min_score=0.99)
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_search_touches(self):
        mgr = MemoryManager()
        await mgr.store("user loves coffee", scope=self.make_scope())
        results = await mgr.search(text="coffee", scope=self.make_scope())
        assert results[0].item.access_count == 1

    @pytest.mark.asyncio
    async def test_batch_store(self):
        mgr = MemoryManager()
        items = await mgr.batch_store([
            {"content": "one", "memory_type": "long_term"},
            {"content": "two", "memory_type": "session"},
        ], scope=self.make_scope())
        assert len(items) == 2
        assert items[0].memory_type == MemoryType.LONG_TERM

    @pytest.mark.asyncio
    async def test_batch_retrieve(self):
        mgr = MemoryManager()
        item = await mgr.store("x", scope=self.make_scope())
        items = await mgr.batch_retrieve([item.id], scope=self.make_scope())
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_batch_retrieve_scope_isolation(self):
        mgr = MemoryManager()
        item = await mgr.store("x", scope=self.make_scope())
        items = await mgr.batch_retrieve([item.id], scope=self.make_scope(user_id="other"))
        assert items == []

    @pytest.mark.asyncio
    async def test_extract(self):
        mgr = MemoryManager()
        extracted = await mgr.extract("I like pizza and I want to travel")
        categories = {m.category for m in extracted}
        assert MemoryCategory.PREFERENCE in categories
        assert MemoryCategory.GOAL in categories

    @pytest.mark.asyncio
    async def test_extract_auto_store(self):
        mgr = MemoryManager()
        await mgr.extract("I like pizza", scope=self.make_scope(), auto_store=True)
        items = await mgr.retrieve(self.make_scope())
        assert len(items) >= 1

    @pytest.mark.asyncio
    async def test_run_maintenance(self):
        mgr = MemoryManager()
        item = MemoryItem(
            id="old", content="stale", memory_type=MemoryType.SHORT_TERM,
            tenant_id="t1", user_id="u1",
        )
        item.created_at = time.time() - 10 * 86400
        mgr._repository._items["old"] = item
        result = await mgr.run_maintenance(self.make_scope())
        assert "old" in result["expired"]

    @pytest.mark.asyncio
    async def test_compact(self):
        mgr = MemoryManager()
        mgr._config.enable_compaction = True
        mgr._repository._items["a"] = MemoryItem(id="a", content="the quick brown fox jumps", tenant_id="t1", user_id="u1")
        mgr._repository._items["b"] = MemoryItem(id="b", content="the quick brown fox runs fast", tenant_id="t1", user_id="u1")
        merged = await mgr.compact(self.make_scope(), threshold=0.5)
        assert len(merged) == 1

    def test_get_metrics(self):
        mgr = MemoryManager()
        assert mgr.get_metrics().total_ops == 0

    @pytest.mark.asyncio
    async def test_observer_sync(self):
        mgr = MemoryManager()
        events = []

        def observer(event, item, extra):
            events.append(event)

        mgr.subscribe(observer)
        await mgr.store("x", scope=self.make_scope())
        assert MemoryEventType.STORE in events
        mgr.unsubscribe(observer)

    @pytest.mark.asyncio
    async def test_observer_async(self):
        mgr = MemoryManager()
        events = []

        async def observer(event, item, extra):
            events.append(event)

        mgr.subscribe(observer)
        await mgr.delete("ghost")
        mgr.unsubscribe(observer)
        assert MemoryEventType.DELETE in events

    @pytest.mark.asyncio
    async def test_observer_error_swallowed(self):
        mgr = MemoryManager()
        mgr.subscribe(lambda e, i, x: 1 / 0)
        item = await mgr.store("x", scope=self.make_scope())
        assert item.id

    @pytest.mark.asyncio
    async def test_unsubscribe_absent(self):
        mgr = MemoryManager()

        def observer(e, i, x):
            pass

        mgr.subscribe(observer)
        mgr.unsubscribe(observer)
        mgr.unsubscribe(observer)


# ============================================================
# Factory
# ============================================================
class TestFactory:
    def test_create_default(self):
        from app.memory import create_memory_manager
        mgr = create_memory_manager()
        assert isinstance(mgr, MemoryManager)

    def test_create_with_config(self):
        from app.memory import create_memory_manager
        mgr = create_memory_manager(config=MemoryVectorConfig(default_top_k=50))
        assert mgr._config.default_top_k == 50


# ============================================================
# Coverage edge cases
# ============================================================
class TestRepositoryEdgeCases:
    @pytest.mark.asyncio
    async def test_update_vector_store_upsert_failure_swallowed(self):
        vs = MagicMock()
        vs.upsert = AsyncMock(side_effect=RuntimeError("boom"))
        repo = MemoryRepository(vector_store=vs)
        item = MemoryItem(id="m1", content="hello", embedding=[0.1, 0.2])
        await repo.store(item)
        item.content = "hello world"
        result = await repo.update(item)
        assert result.content == "hello world"

    @pytest.mark.asyncio
    async def test_delete_vector_store_failure_swallowed(self):
        vs = MagicMock()
        vs.delete = AsyncMock(side_effect=RuntimeError("boom"))
        repo = MemoryRepository(vector_store=vs)
        await repo.store(MemoryItem(id="m1", content="hello"))
        assert await repo.delete("m1") is True

    @pytest.mark.asyncio
    async def test_search_embedder_object_vector(self):
        repo = MemoryRepository()
        await repo.store(MemoryItem(id="m1", content="gold price rally"))
        async def emb(q):
            return MagicMock(vector=[0.1, 0.2, 0.3])
        repo._embedder = emb
        results = await repo.search("gold", MemoryScope())
        assert any(r.item.id == "m1" for r in results)

    @pytest.mark.asyncio
    async def test_search_embedder_raising(self):
        repo = MemoryRepository()
        await repo.store(MemoryItem(id="m1", content="gold price rally"))
        repo._embedder = AsyncMock(side_effect=RuntimeError("no emb"))
        results = await repo.search("gold", MemoryScope())
        assert any(r.item.id == "m1" for r in results)

    def test_find_duplicate_skips_deleted_and_empty(self):
        repo = MemoryRepository()
        repo._items["d"] = MemoryItem(id="d", content="deleted entry", deleted=True)
        repo._items["e"] = MemoryItem(id="e", content="")
        repo._items["f"] = MemoryItem(id="f", content="gold price rally today")
        hit = repo.find_duplicate("gold price rally today", threshold=0.8)
        assert hit is not None and hit.id == "f"
        assert repo.find_duplicate("", threshold=0.5) is None
        assert repo.find_duplicate("zzz", threshold=0.99) is None


class TestExtractorEdgeCases:
    def test_custom_extractor_reraises_extraction_error(self):
        from app.memory.exceptions import MemoryExtractionError

        def boom(text):
            raise MemoryExtractionError("nope")

        ex = MemoryExtractor(extraction_func=boom)
        with pytest.raises(MemoryExtractionError):
            ex.extract("hello")

    def test_custom_extractor_list_of_plain_values(self):
        ex = MemoryExtractor(extraction_func=lambda text: ["raw one", "raw two"])
        out = ex.extract("hello")
        assert len(out) == 2
        assert all(isinstance(m, ExtractedMemory) for m in out)

    def test_patterns_skip_empty_after_clean(self):
        ex = MemoryExtractor(extraction_func=None)
        ex.PATTERNS = [(r"[^\w\s]+", MemoryCategory.GENERAL)]
        out = ex.extract("!!!")
        assert out == []


class TestScopeEdgeCases:
    def test_filter_user_mismatch(self):
        scope = MemoryScope(tenant_id="t1", user_id="u1")
        assert not scope.is_isolated(MemoryItem(id="x", content="c", tenant_id="t1", user_id="u2"))

    def test_filter_session_mismatch(self):
        scope = MemoryScope(tenant_id="t1", user_id="u1", session_id="s1")
        assert not scope.is_isolated(MemoryItem(id="x", content="c", tenant_id="t1", user_id="u1", session_id="s2"))

    def test_filter_workspace_mismatch(self):
        scope = MemoryScope(tenant_id="t1", workspace_id="w1")
        assert not scope.is_isolated(MemoryItem(id="x", content="c", tenant_id="t1", workspace_id="w2"))

    def test_scope_bool_empty(self):
        assert not bool(MemoryScope())
        assert bool(MemoryScope(tenant_id="t1"))


class TestLifecycleEdgeCases:
    @pytest.mark.asyncio
    async def test_run_maintenance_reraises_lifecycle_error(self):
        lc = MemoryLifecycleManager()
        lc._repository = MagicMock()
        lc._repository.list = MagicMock(side_effect=MemoryLifecycleError("db down"))
        with pytest.raises(MemoryLifecycleError):
            await lc.run_maintenance(MemoryScope())

    @pytest.mark.asyncio
    async def test_run_maintenance_wraps_unknown_error(self):
        lc = MemoryLifecycleManager()
        lc._repository = MagicMock()
        lc._repository.list = MagicMock(side_effect=RuntimeError("boom"))
        with pytest.raises(MemoryLifecycleError):
            await lc.run_maintenance(MemoryScope())

    @pytest.mark.asyncio
    async def test_compact_skips_used_ids(self):
        lc = MemoryLifecycleManager()
        lc._repository = MagicMock()
        lc._repository.list = MagicMock(return_value=[
            MemoryItem(id="a", content="quick brown fox jumps"),
            MemoryItem(id="b", content="entirely different tokens"),
            MemoryItem(id="c", content="quick brown fox runs"),
        ])
        lc._repository.items = {}
        merged = await lc.compact(MemoryScope(), threshold=0.5)
        assert len(merged) == 2

    @pytest.mark.asyncio
    async def test_check_ttl_metadata_override(self):
        lc = MemoryLifecycleManager()
        item = MemoryItem(id="m1", content="c", metadata={"ttl_days": 2.0})
        item.created_at = time.time() - 3 * 86400
        assert await lc.check_ttl(item) is True
        item2 = MemoryItem(id="m2", content="c", metadata={"ttl_days": 10.0})
        item2.created_at = time.time() - 3 * 86400
        assert await lc.check_ttl(item2) is False


class TestSummarizerEdgeCases:
    @pytest.mark.asyncio
    async def test_reraises_summarization_error(self):
        def boom(items, style="concise"):
            raise MemorySummarizationError("nope")

        s = MemorySummarizer(summarizer_func=boom)
        with pytest.raises(MemorySummarizationError):
            await s.summarize([MemoryItem(id="m1", content="c")])

    @pytest.mark.asyncio
    async def test_wraps_unknown_error(self):
        def boom(items, style="concise"):
            raise RuntimeError("boom")

        s = MemorySummarizer(summarizer_func=boom)
        with pytest.raises(MemorySummarizationError):
            await s.summarize([MemoryItem(id="m1", content="c")])

    @pytest.mark.asyncio
    async def test_async_custom_summarizer(self):
        async def async_sum(items, style="concise"):
            return f"async:{len(items)}"

        s = MemorySummarizer(summarizer_func=async_sum)
        assert await s.summarize([MemoryItem(id="m1", content="c")]) == "async:1"


class TestManagerErrorPaths:
    @pytest.mark.asyncio
    async def test_store_empty_content_raises_validation(self):
        mgr = MemoryManager()
        with pytest.raises(MemoryValidationError):
            await mgr.store("   ")

    @pytest.mark.asyncio
    async def test_retrieve_propagates_memory_error(self):
        mgr = MemoryManager()
        mgr._repository = MagicMock()
        mgr._repository.list = MagicMock(side_effect=MemoryStorageError("nope"))
        with pytest.raises(MemoryError):
            await mgr.retrieve(MemoryScope())

    @pytest.mark.asyncio
    async def test_retrieve_wraps_unknown_error(self):
        mgr = MemoryManager()
        mgr._repository = MagicMock()
        mgr._repository.list = MagicMock(side_effect=RuntimeError("boom"))
        with pytest.raises(MemoryError):
            await mgr.retrieve(MemoryScope())

    @pytest.mark.asyncio
    async def test_update_empty_content(self):
        mgr = MemoryManager()
        item = await mgr.store("hello", MemoryScope())
        with pytest.raises(MemoryValidationError):
            await mgr.update(item.id, content="  ")

    @pytest.mark.asyncio
    async def test_update_missing_item(self):
        mgr = MemoryManager()
        with pytest.raises(MemoryNotFoundError):
            await mgr.update("nope")

    @pytest.mark.asyncio
    async def test_update_repository_tenant_error(self):
        mgr = MemoryManager()
        item = await mgr.store("hello", MemoryScope())
        mgr._repository = MagicMock()
        mgr._repository.get = MagicMock(return_value=item)
        mgr._repository.update = AsyncMock(side_effect=MemoryTenantError("nope"))
        with pytest.raises(MemoryError):
            await mgr.update(item.id, content="world")

    @pytest.mark.asyncio
    async def test_update_confidence_and_metadata(self):
        mgr = MemoryManager()
        item = await mgr.store("hello", MemoryScope())
        updated = await mgr.update(
            item.id, confidence=0.9, metadata={"source": "test"}
        )
        assert updated.confidence == 0.9
        assert updated.metadata["source"] == "test"

    @pytest.mark.asyncio
    async def test_summarize_wraps_unknown_error(self):
        mgr = MemoryManager()
        mgr._repository = MagicMock()
        mgr._repository.list = MagicMock(side_effect=RuntimeError("boom"))
        with pytest.raises(MemoryError):
            await mgr.summarize(MemoryScope())

    @pytest.mark.asyncio
    async def test_run_maintenance_reraises_lifecycle_error(self):
        mgr = MemoryManager()
        mgr._lifecycle = MagicMock()
        mgr._lifecycle.run_maintenance = AsyncMock(side_effect=MemoryLifecycleError("nope"))
        with pytest.raises(MemoryLifecycleError):
            await mgr.run_maintenance(MemoryScope())

    @pytest.mark.asyncio
    async def test_delete_repository_error(self):
        mgr = MemoryManager()
        mgr._repository = MagicMock()
        mgr._repository.get = MagicMock(return_value=MemoryItem(id="m1", content="c"))
        mgr._repository.delete = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(MemoryError):
            await mgr.delete("m1")

    @pytest.mark.asyncio
    async def test_summarize_reraises_summarization_error(self):
        mgr = MemoryManager()
        mgr._repository = MagicMock()
        mgr._repository.list = MagicMock(return_value=[MemoryItem(id="m1", content="c")])
        mgr._summarizer = MemorySummarizer(
            summarizer_func=lambda items, style="concise": (_ for _ in ()).throw(MemorySummarizationError("nope"))
        )
        with pytest.raises(MemorySummarizationError):
            await mgr.summarize(MemoryScope())

    @pytest.mark.asyncio
    async def test_search_repository_error(self):
        mgr = MemoryManager()
        mgr._repository = MagicMock()
        mgr._repository.search = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(MemoryError):
            await mgr.search(MemoryQuery(text="gold", scope=MemoryScope()))

    @pytest.mark.asyncio
    async def test_batch_store_repository_error(self):
        mgr = MemoryManager()
        mgr._repository = MagicMock()
        mgr._repository.store = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(MemoryError):
            await mgr.batch_store([{"content": "c"}], MemoryScope())

    @pytest.mark.asyncio
    async def test_batch_store_lifecycle_error(self):
        mgr = MemoryManager()
        mgr._repository = MagicMock()
        mgr._repository.store = AsyncMock(side_effect=MemoryLifecycleError("nope"))
        with pytest.raises(MemoryLifecycleError):
            await mgr.batch_store([{"content": "c"}], MemoryScope())

    @pytest.mark.asyncio
    async def test_embed_failure_sets_none(self):
        async def bad_embed(text):
            raise RuntimeError("no embed")

        repo = MemoryRepository()
        repo._embedder = bad_embed
        mgr = MemoryManager(repository=repo)
        item = await mgr.store("hello", MemoryScope())
        assert item.embedding is None

    @pytest.mark.asyncio
    async def test_embed_result_with_vector_attr(self):
        repo = MemoryRepository()
        async def emb(text):
            return MagicMock(vector=[1.0, 2.0])
        repo._embedder = emb
        mgr = MemoryManager(repository=repo)
        item = await mgr.store("hello", MemoryScope())
        assert item.embedding == [1.0, 2.0]
