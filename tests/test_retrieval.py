from __future__ import annotations

import math
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.retrieval.config import RetrievalConfig
from app.retrieval.models import (
    MetadataFilter,
    RetrievalStatistics,
    SearchQuery,
    SearchResponse,
    SearchResultItem,
    SimilarityMetric,
)
from app.retrieval.exceptions import (
    EmptyQueryError,
    FilterError,
    InvalidQueryError,
    InvalidSimilarityMetricError,
    PaginationError,
    RetrievalError,
    VectorDimensionMismatchError,
)
from app.retrieval.similarity import (
    CosineSimilarity,
    DotProductSimilarity,
    EuclideanSimilarity,
    SimilarityStrategy,
    create_similarity_strategy,
)
from app.retrieval.filtering import MetadataFilterEngine
from app.retrieval.ranking import Ranker
from app.retrieval.pagination import Paginator
from app.retrieval.statistics import RetrievalStatsTracker
from app.retrieval.logging import RetrievalLogger
from app.retrieval.service import SemanticSearch

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestSearchQuery:
    def test_defaults(self):
        q = SearchQuery(text="hello")
        assert q.text == "hello"
        assert q.top_k == 10
        assert q.similarity == SimilarityMetric.COSINE

    def test_to_dict(self):
        q = SearchQuery(text="hello", tags=["ai"], author="me")
        d = q.to_dict()
        assert d["text"] == "hello"
        assert d["tags"] == ["ai"]
        assert d["author"] == "me"

    def test_with_custom_filters(self):
        q = SearchQuery(text="test", custom_filters={"domain": "tech"})
        d = q.to_dict()
        assert d["custom_filters"]["domain"] == "tech"

    def test_with_vector(self):
        q = SearchQuery(vector=[0.1, 0.2, 0.3])
        assert q.vector == [0.1, 0.2, 0.3]

    def test_with_fields(self):
        q = SearchQuery(
            text="hello", top_k=5, offset=2, limit=3,
            score_threshold=0.5, max_distance=0.3,
            collection="docs", namespace="ns1",
            similarity=SimilarityMetric.EUCLIDEAN,
            include_metadata=True, include_vector=True,
            recency_boost=True, quality_boost=False,
        )
        assert q.top_k == 5
        assert q.offset == 2
        assert q.limit == 3
        assert q.score_threshold == 0.5
        assert q.max_distance == 0.3


class TestSearchResultItem:
    def test_defaults(self):
        r = SearchResultItem(id="r1", score=0.95)
        assert r.rank == 0
        assert r.metadata == {}

    def test_to_dict(self):
        r = SearchResultItem(
            id="r1", score=0.95, rank=1, metadata={"key": "val"},
            namespace="ns1", collection="coll1",
        )
        d = r.to_dict()
        assert d["id"] == "r1"
        assert d["rank"] == 1
        assert "vector" not in d

    def test_to_dict_with_vector(self):
        r = SearchResultItem(id="r1", score=0.95, vector=[0.1, 0.2])
        d = r.to_dict(include_vector=True)
        assert d["vector"] == [0.1, 0.2]


class TestSearchResponse:
    def test_defaults(self):
        r = SearchResponse(results=[], total=0, offset=0, limit=10)
        assert r.query_time_ms == 0.0

    def test_to_dict(self):
        r = SearchResponse(
            results=[SearchResultItem(id="r1", score=0.95)],
            total=1, offset=0, limit=10, query_time_ms=1.5,
        )
        d = r.to_dict()
        assert len(d["results"]) == 1
        assert d["total"] == 1
        assert d["query_time_ms"] == 1.5


class TestMetadataFilter:
    def test_to_dict(self):
        mf = MetadataFilter(field="author", value="me", operator="eq")
        d = mf.to_dict()
        assert d["field"] == "author"
        assert d["value"] == "me"

    def test_default_operator(self):
        mf = MetadataFilter(field="tag", value="ai")
        assert mf.operator == "eq"


class TestRetrievalStatistics:
    def test_defaults(self):
        s = RetrievalStatistics()
        assert s.query_count == 0

    def test_to_dict(self):
        s = RetrievalStatistics(
            query_count=10, total_latency_ms=100.0, average_latency_ms=10.0,
        )
        d = s.to_dict()
        assert d["query_count"] == 10
        assert d["average_latency_ms"] == 10.0

    def test_empty_to_dict(self):
        s = RetrievalStatistics()
        d = s.to_dict()
        assert d["query_count"] == 0
        assert d["average_latency_ms"] == 0.0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestRetrievalConfig:
    def test_defaults(self):
        c = RetrievalConfig()
        assert c.top_k_default == 10
        assert c.default_similarity == "cosine"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("RETRIEVAL_TOP_K_DEFAULT", "25")
        monkeypatch.setenv("RETRIEVAL_SIMILARITY", "euclidean")
        monkeypatch.setenv("RETRIEVAL_TRACK_STATISTICS", "0")
        c = RetrievalConfig.from_env()
        assert c.top_k_default == 25
        assert c.default_similarity == "euclidean"
        assert c.track_statistics is False


# ---------------------------------------------------------------------------
# Similarity Strategies
# ---------------------------------------------------------------------------

class TestCosineSimilarity:
    def test_identical(self):
        s = CosineSimilarity()
        v = [1.0, 0.0, 0.0]
        assert s.compute(v, v) == pytest.approx(1.0)

    def test_orthogonal(self):
        s = CosineSimilarity()
        assert s.compute([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite(self):
        s = CosineSimilarity()
        assert s.compute([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector(self):
        s = CosineSimilarity()
        assert s.compute([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_name(self):
        assert CosineSimilarity().name == "cosine"


class TestDotProductSimilarity:
    def test_same(self):
        s = DotProductSimilarity()
        assert s.compute([1.0, 2.0], [3.0, 4.0]) == pytest.approx(11.0)

    def test_zero(self):
        s = DotProductSimilarity()
        assert s.compute([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_name(self):
        assert DotProductSimilarity().name == "dot_product"


class TestEuclideanSimilarity:
    def test_identical(self):
        s = EuclideanSimilarity()
        v = [1.0, 0.0]
        assert s.compute(v, v) == pytest.approx(1.0)

    def test_different(self):
        s = EuclideanSimilarity()
        score = s.compute([0.0, 0.0], [3.0, 4.0])
        assert score < 1.0
        assert score > 0.0

    def test_name(self):
        assert EuclideanSimilarity().name == "euclidean"


class TestCreateSimilarityStrategy:
    def test_cosine(self):
        s = create_similarity_strategy("cosine")
        assert isinstance(s, CosineSimilarity)

    def test_dot_product(self):
        s = create_similarity_strategy("dot_product")
        assert isinstance(s, DotProductSimilarity)

    def test_euclidean(self):
        s = create_similarity_strategy("euclidean")
        assert isinstance(s, EuclideanSimilarity)

    def test_from_enum(self):
        s = create_similarity_strategy(SimilarityMetric.COSINE)
        assert isinstance(s, CosineSimilarity)

    def test_invalid(self):
        with pytest.raises(InvalidSimilarityMetricError):
            create_similarity_strategy("unknown")


# ---------------------------------------------------------------------------
# MetadataFilterEngine
# ---------------------------------------------------------------------------

class TestMetadataFilterEngine:
    def setup_method(self):
        self.engine = MetadataFilterEngine()

    def test_no_filters(self):
        items = [{"metadata": {"author": "me"}}]
        result = self.engine.apply(SearchQuery(text="test"), items)
        assert len(result) == 1

    def test_filter_eq(self):
        items = [
            {"metadata": {"author": "me"}},
            {"metadata": {"author": "you"}},
        ]
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="author", value="me"),
        ])
        result = self.engine.apply(q, items)
        assert len(result) == 1
        assert result[0]["metadata"]["author"] == "me"

    def test_filter_author(self):
        items = [
            {"metadata": {"author": "alice"}},
            {"metadata": {"author": "bob"}},
        ]
        q = SearchQuery(text="test", author="alice")
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_filter_tags(self):
        items = [
            {"metadata": {"tags": ["ai", "ml"]}},
            {"metadata": {"tags": ["web"]}},
        ]
        q = SearchQuery(text="test", tags=["ai"])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_filter_tags_string(self):
        items = [{"metadata": {"tags": "ai"}}]
        q = SearchQuery(text="test", tags=["ai"])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_filter_language(self):
        items = [
            {"metadata": {"language": "en"}},
            {"metadata": {"language": "fr"}},
        ]
        q = SearchQuery(text="test", language="en")
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_filter_source(self):
        items = [
            {"metadata": {"source": "web"}},
            {"metadata": {"source": "api"}},
        ]
        q = SearchQuery(text="test", source="web")
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_filter_tenant(self):
        items = [
            {"metadata": {"tenant": "acme"}},
            {"metadata": {"tenant": "other"}},
        ]
        q = SearchQuery(text="test", tenant="acme")
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_custom_filters(self):
        items = [
            {"metadata": {"domain": "tech"}},
            {"metadata": {"domain": "finance"}},
        ]
        q = SearchQuery(text="test", custom_filters={"domain": "tech"})
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_multiple_filters(self):
        items = [
            {"metadata": {"author": "alice", "language": "en"}},
            {"metadata": {"author": "alice", "language": "fr"}},
            {"metadata": {"author": "bob", "language": "en"}},
        ]
        q = SearchQuery(text="test", author="alice", language="en")
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_operator_neq(self):
        items = [{"metadata": {"status": "active"}}, {"metadata": {"status": "inactive"}}]
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="status", value="active", operator="neq"),
        ])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_operator_gt(self):
        items = [{"metadata": {"score": 10}}, {"metadata": {"score": 5}}]
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="score", value=7, operator="gt"),
        ])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_operator_gte(self):
        items = [{"metadata": {"score": 7}}, {"metadata": {"score": 5}}]
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="score", value=7, operator="gte"),
        ])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_operator_lt(self):
        items = [{"metadata": {"score": 3}}, {"metadata": {"score": 10}}]
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="score", value=5, operator="lt"),
        ])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_operator_lte(self):
        items = [{"metadata": {"score": 5}}, {"metadata": {"score": 10}}]
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="score", value=5, operator="lte"),
        ])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_operator_in(self):
        items = [{"metadata": {"role": "admin"}}, {"metadata": {"role": "user"}}]
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="role", value=["admin", "mod"], operator="in"),
        ])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_operator_contains(self):
        items = [{"metadata": {"title": "hello world"}}, {"metadata": {"title": "goodbye"}}]
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="title", value="hello", operator="contains"),
        ])
        result = self.engine.apply(q, items)
        assert len(result) == 1

    def test_unknown_operator(self):
        with pytest.raises(FilterError):
            q = SearchQuery(text="test", metadata_filters=[
                MetadataFilter(field="x", value="y", operator="unknown"),
            ])
            self.engine.apply(q, [{"metadata": {"x": "y"}}])

    def test_build_vs_filter_empty(self):
        q = SearchQuery(text="test")
        result = self.engine.build_vector_store_filter(q)
        assert result is None

    def test_build_vs_filter_author(self):
        q = SearchQuery(text="test", author="alice")
        result = self.engine.build_vector_store_filter(q)
        assert result == {"author": "alice"}

    def test_build_vs_filter_combined(self):
        q = SearchQuery(text="test", author="alice", language="en", custom_filters={"domain": "tech"})
        result = self.engine.build_vector_store_filter(q)
        assert result["author"] == "alice"
        assert result["language"] == "en"
        assert result["domain"] == "tech"

    def test_build_vs_filter_eq_only(self):
        q = SearchQuery(text="test", metadata_filters=[
            MetadataFilter(field="status", value="active", operator="gt"),
        ])
        result = self.engine.build_vector_store_filter(q)
        assert result is None


# ---------------------------------------------------------------------------
# Ranker
# ---------------------------------------------------------------------------

class TestRanker:
    def setup_method(self):
        self.ranker = Ranker()

    def _make_item(self, id: str, score: float, metadata: dict | None = None) -> SearchResultItem:
        return SearchResultItem(id=id, score=score, metadata=metadata or {})

    def test_rank_by_score(self):
        items = [
            self._make_item("a", 0.9),
            self._make_item("b", 0.8),
            self._make_item("c", 0.95),
        ]
        q = SearchQuery(text="test", recency_boost=False, quality_boost=False, metadata_boost=False, manual_boost=False)
        ranked = self.ranker.rank(items, q)
        assert [r.id for r in ranked] == ["c", "a", "b"]
        assert ranked[0].rank == 1

    def test_recency_boost(self):
        recent = self._make_item("recent", 0.5, {"created_at": time.time()})
        old = self._make_item("old", 0.5, {"created_at": time.time() - 86400 * 30})
        q = SearchQuery(text="test", recency_boost=True, quality_boost=False, metadata_boost=False, manual_boost=False)
        ranked = self.ranker.rank([old, recent], q)
        assert ranked[0].id == "recent"

    def test_recency_missing_timestamp(self):
        item = self._make_item("a", 0.5, {})
        q = SearchQuery(text="test", recency_boost=True, quality_boost=False, metadata_boost=False, manual_boost=False)
        ranked = self.ranker.rank([item], q)
        assert ranked[0].id == "a"

    def test_recency_bad_timestamp(self):
        item = self._make_item("a", 0.5, {"created_at": "invalid"})
        q = SearchQuery(text="test", recency_boost=True)
        ranked = self.ranker.rank([item], q)
        assert ranked[0].id == "a"

    def test_quality_boost(self):
        high = self._make_item("high", 0.5, {"quality": 0.9})
        low = self._make_item("low", 0.5, {"quality": 0.1})
        q = SearchQuery(text="test", recency_boost=False, quality_boost=True, metadata_boost=False, manual_boost=False)
        ranked = self.ranker.rank([low, high], q)
        assert ranked[0].id == "high"

    def test_quality_default(self):
        item = self._make_item("a", 0.5, {})
        q = SearchQuery(text="test", recency_boost=False, quality_boost=True, metadata_boost=False, manual_boost=False)
        ranked = self.ranker.rank([item], q)
        assert ranked[0].id == "a"

    def test_quality_bad_value(self):
        item = self._make_item("a", 0.5, {"quality": "bad"})
        q = SearchQuery(text="test", recency_boost=False, quality_boost=True, metadata_boost=False, manual_boost=False)
        ranked = self.ranker.rank([item], q)
        assert ranked[0].id == "a"

    def test_metadata_boost_author(self):
        matching = self._make_item("match", 0.5, {"author": "alice"})
        other = self._make_item("other", 0.5, {"author": "bob"})
        q = SearchQuery(text="test", author="alice", metadata_boost=True, recency_boost=False, quality_boost=False, manual_boost=False)
        ranked = self.ranker.rank([other, matching], q)
        assert ranked[0].id == "match"

    def test_metadata_boost_tags(self):
        matching = self._make_item("match", 0.5, {"tags": ["ai", "ml"]})
        other = self._make_item("other", 0.5, {"tags": ["web"]})
        q = SearchQuery(text="test", tags=["ai"], metadata_boost=True, recency_boost=False, quality_boost=False, manual_boost=False)
        ranked = self.ranker.rank([other, matching], q)
        assert ranked[0].id == "match"

    def test_manual_boost(self):
        boosted = self._make_item("boosted", 0.5, {"boost": 0.5})
        normal = self._make_item("normal", 0.5, {})
        q = SearchQuery(text="test", manual_boost=True, recency_boost=False, quality_boost=False, metadata_boost=False)
        ranked = self.ranker.rank([normal, boosted], q)
        assert ranked[0].id == "boosted"

    def test_manual_boost_bad_value(self):
        item = self._make_item("a", 0.5, {"boost": "invalid"})
        q = SearchQuery(text="test", manual_boost=True, recency_boost=False, quality_boost=False, metadata_boost=False)
        ranked = self.ranker.rank([item], q)
        assert ranked[0].id == "a"


# ---------------------------------------------------------------------------
# Paginator
# ---------------------------------------------------------------------------

class TestPaginator:
    def setup_method(self):
        self.pag = Paginator(max_limit=100)

    def _make_items(self, n: int) -> list[SearchResultItem]:
        return [SearchResultItem(id=str(i), score=1.0) for i in range(n)]

    def test_no_pagination(self):
        items = self._make_items(5)
        q = SearchQuery(text="test")
        result = self.pag.apply(q, items)
        assert len(result) == 5

    def test_offset(self):
        items = self._make_items(10)
        q = SearchQuery(text="test", offset=5, limit=10)
        result = self.pag.apply(q, items)
        assert len(result) == 5
        assert result[0].id == "5"

    def test_limit(self):
        items = self._make_items(10)
        q = SearchQuery(text="test", limit=3)
        result = self.pag.apply(q, items)
        assert len(result) == 3

    def test_beyond_range(self):
        items = self._make_items(5)
        q = SearchQuery(text="test", offset=10)
        result = self.pag.apply(q, items)
        assert len(result) == 0

    def test_max_limit(self):
        items = self._make_items(200)
        q = SearchQuery(text="test", limit=200)
        result = self.pag.apply(q, items)
        assert len(result) == 100

    def test_cursor(self):
        items = self._make_items(20)
        q = SearchQuery(text="test", cursor=None, limit=5)
        page1 = self.pag.apply(q, items)
        cursor = self.pag.compute_next_cursor(q, page1, len(items))
        assert cursor is not None
        q2 = SearchQuery(text="test", cursor=cursor, limit=5)
        page2 = self.pag.apply(q2, items)
        assert len(page2) == 5
        assert page2[0].id == "5"

    def test_cursor_end(self):
        items = self._make_items(5)
        q = SearchQuery(text="test", limit=5)
        page = self.pag.apply(q, items)
        cursor = self.pag.compute_next_cursor(q, page, len(items))
        assert cursor is None

    def test_invalid_cursor(self):
        with pytest.raises(PaginationError):
            items = self._make_items(5)
            q = SearchQuery(text="test", cursor="invalid!")
            self.pag.apply(q, items)


# ---------------------------------------------------------------------------
# RetrievalStatsTracker
# ---------------------------------------------------------------------------

class TestRetrievalStatsTracker:
    def test_snapshot_empty(self):
        t = RetrievalStatsTracker(track=True)
        s = t.snapshot()
        assert s.query_count == 0

    def test_record_query(self):
        t = RetrievalStatsTracker(track=True)
        t.record_query(latency_ms=10.0, scanned=5, comparisons=20)
        s = t.snapshot()
        assert s.query_count == 1
        assert s.total_latency_ms == 10.0
        assert s.average_latency_ms == 10.0
        assert s.total_vectors_scanned == 5
        assert s.total_comparisons == 20

    def test_multiple_queries(self):
        t = RetrievalStatsTracker(track=True)
        t.record_query(10.0)
        t.record_query(20.0)
        s = t.snapshot()
        assert s.query_count == 2
        assert s.total_latency_ms == 30.0
        assert s.average_latency_ms == 15.0

    def test_cache_hit(self):
        t = RetrievalStatsTracker(track=True)
        t.record_cache_hit()
        t.record_cache_miss()
        s = t.snapshot()
        assert s.cache_hits == 1
        assert s.cache_misses == 1

    def test_track_disabled(self):
        t = RetrievalStatsTracker(track=False)
        t.record_query(10.0)
        t.record_cache_hit()
        s = t.snapshot()
        assert s.query_count == 0
        assert s.cache_hits == 0

    def test_reset(self):
        t = RetrievalStatsTracker(track=True)
        t.record_query(10.0)
        t.reset()
        s = t.snapshot()
        assert s.query_count == 0


# ---------------------------------------------------------------------------
# RetrievalLogger
# ---------------------------------------------------------------------------

class TestRetrievalLogger:
    def test_enabled(self):
        logger = RetrievalLogger(enabled=True)
        assert logger._enabled is True

    def test_disabled(self):
        logger = RetrievalLogger(enabled=False)
        assert logger._enabled is False

    def test_log_query(self):
        logger = RetrievalLogger(enabled=True)
        q = SearchQuery(text="hello")
        logger.log_query(q)

    def test_log_result(self):
        logger = RetrievalLogger(enabled=True)
        q = SearchQuery(text="hello")
        r = SearchResponse(results=[], total=0, offset=0, limit=10)
        logger.log_result(q, r, 1.0)

    def test_log_error(self):
        logger = RetrievalLogger(enabled=True)
        logger.log_error(SearchQuery(text="hello"), ValueError("test"))


# ---------------------------------------------------------------------------
# SemanticSearch Service
# ---------------------------------------------------------------------------

class TestSemanticSearch:
    @pytest.fixture
    def vs_mock(self):
        store = AsyncMock()
        store.search = AsyncMock(return_value=[
            type("VSResult", (), {
                "id": f"r{i}", "score": 0.9 - i * 0.1,
                "vector": [float(i)] * 4,
                "metadata": {"author": "alice", "quality": 0.8, "created_at": 1e9},
                "namespace": "default",
            })()
            for i in range(3)
        ])
        store.provider_name = "memory"
        return store

    @pytest.fixture
    def embed_mock(self):
        emb = AsyncMock()
        emb.embed_text = AsyncMock(return_value=type("ER", (), {
            "vector": [0.1, 0.2, 0.3, 0.4],
            "model": "test",
            "provider": "local",
            "dimensions": 4,
            "token_count": 3,
        })())
        return emb

    @pytest.fixture
    def ss(self, vs_mock, embed_mock):
        return SemanticSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            config=RetrievalConfig(
                enable_recency_boost=False,
                enable_quality_boost=False,
                enable_metadata_boost=False,
                enable_manual_boost=False,
                track_statistics=False,
                log_queries=False,
            ),
        )

    @pytest.mark.asyncio
    async def test_search_text(self, ss):
        q = SearchQuery(text="hello", top_k=5)
        response = await ss.search(q)
        assert len(response.results) == 3
        assert response.total == 3

    @pytest.mark.asyncio
    async def test_search_by_embedding(self, ss):
        q = SearchQuery(vector=[0.1, 0.2, 0.3, 0.4], top_k=5)
        response = await ss.search(q)
        assert len(response.results) == 3

    @pytest.mark.asyncio
    async def test_search_empty_query(self, ss):
        with pytest.raises(EmptyQueryError):
            await ss.search(SearchQuery(text=""))

    @pytest.mark.asyncio
    async def test_search_empty_vector(self, ss):
        ss_no_embed = SemanticSearch(
            vector_store=ss._vector_store,
            embedding_service=None,
            config=ss._config,
        )
        with pytest.raises(InvalidQueryError):
            await ss_no_embed.search(SearchQuery(text="hello"))

    @pytest.mark.asyncio
    async def test_invalid_top_k(self, ss):
        with pytest.raises(InvalidQueryError):
            await ss.search(SearchQuery(text="hello", top_k=0))

    @pytest.mark.asyncio
    async def test_negative_offset(self, ss):
        with pytest.raises(InvalidQueryError):
            await ss.search(SearchQuery(text="hello", offset=-1))

    @pytest.mark.asyncio
    async def test_search_async(self, ss):
        response = await ss.search_async(SearchQuery(text="hello"))
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_retrieve(self, ss):
        results = await ss.retrieve("hello", top_k=5)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_retrieve_with_scores(self, ss):
        results = await ss.retrieve_with_scores("hello")
        assert len(results) == 3
        assert isinstance(results[0], tuple)
        assert isinstance(results[0][1], float)

    @pytest.mark.asyncio
    async def test_batch_search(self, ss):
        queries = [SearchQuery(text="hello"), SearchQuery(text="world")]
        responses = await ss.batch_search(queries)
        assert len(responses) == 2

    @pytest.mark.asyncio
    async def test_search_by_embedding_direct(self, ss):
        response = await ss.search_by_embedding([0.1, 0.2, 0.3, 0.4])
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_search_with_score_threshold(self, ss):
        q = SearchQuery(text="hello", score_threshold=0.85)
        response = await ss.search(q)
        assert len(response.results) <= 3

    @pytest.mark.asyncio
    async def test_search_with_filter(self, vs_mock, embed_mock):
        ss = SemanticSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        q = SearchQuery(text="hello", author="alice")
        response = await ss.search(q)
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_search_with_max_distance(self, vs_mock, embed_mock):
        ss = SemanticSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        q = SearchQuery(text="hello", max_distance=0.1)
        response = await ss.search(q)
        assert response.results is not None

    @pytest.mark.asyncio
    async def test_search_with_pagination(self, vs_mock, embed_mock):
        ss = SemanticSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        q = SearchQuery(text="hello", offset=0, limit=2)
        response = await ss.search(q)
        assert len(response.results) <= 2
        assert response.offset == 0

    @pytest.mark.asyncio
    async def test_search_with_invalid_top_k_exceeds_max(self, ss):
        ss_max_limit = SemanticSearch(
            vector_store=ss._vector_store,
            embedding_service=ss._embedding_service,
            config=RetrievalConfig(top_k_max=5),
        )
        with pytest.raises(InvalidQueryError):
            await ss_max_limit.search(SearchQuery(text="hello", top_k=10))

    @pytest.mark.asyncio
    async def test_vs_exception(self, vs_mock, embed_mock):
        vs_mock.search = AsyncMock(side_effect=Exception("VS down"))
        ss = SemanticSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        with pytest.raises(RetrievalError):
            await ss.search(SearchQuery(text="hello"))

    @pytest.mark.asyncio
    async def test_search_with_all_boosts_disabled(self, vs_mock, embed_mock):
        ss = SemanticSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            config=RetrievalConfig(
                enable_recency_boost=False,
                enable_quality_boost=False,
                enable_metadata_boost=False,
                enable_manual_boost=False,
                track_statistics=False,
                log_queries=False,
            ),
        )
        q = SearchQuery(text="hello", recency_boost=False, quality_boost=False, metadata_boost=False, manual_boost=False)
        response = await ss.search(q)
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_search_with_include_vector(self, vs_mock, embed_mock):
        ss = SemanticSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        q = SearchQuery(text="hello", include_vector=True)
        response = await ss.search(q)
        # Results may or may not have vector
        assert response.total > 0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TestRetrievalExceptions:
    def test_retrieval_error(self):
        e = RetrievalError("msg")
        assert str(e) == "msg"

    def test_invalid_query_error(self):
        e = InvalidQueryError()
        assert str(e) == "Invalid search query"

    def test_empty_query_error(self):
        e = EmptyQueryError()
        assert "empty" in str(e).lower()

    def test_vector_dimension_mismatch_error(self):
        e = VectorDimensionMismatchError(384, 128)
        assert "384" in str(e)

    def test_invalid_similarity_metric_error(self):
        e = InvalidSimilarityMetricError("bad")
        assert "bad" in str(e)

    def test_pagination_error(self):
        e = PaginationError()
        assert str(e) == "Invalid pagination"

    def test_filter_error(self):
        e = FilterError("bad filter")
        assert "bad filter" in str(e)
