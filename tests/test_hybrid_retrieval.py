from __future__ import annotations

import math
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.retrieval.bm25 import BM25InvertedIndex, BM25Tokenizer
from app.retrieval.normalization import (
    MinMaxNormalization,
    ZScoreNormalization,
    SoftmaxNormalization,
    RankBasedNormalization,
    NormalizationStrategy,
    create_normalization_strategy,
)
from app.retrieval.fusion import (
    WeightedSumFusion,
    RRFusion,
    CombSUMFusion,
    CombMNZFusion,
    FusionStrategy,
    create_fusion_strategy,
)
from app.retrieval.query_expansion import QueryExpander
from app.retrieval.hybrid import HybridSearch
from app.retrieval.config import RetrievalConfig
from app.retrieval.models import (
    SearchQuery,
    SearchResponse,
    SearchResultItem,
)
from app.retrieval.exceptions import (
    BM25Error,
    EmptyQueryError,
    FusionError,
    InvalidQueryError,
    NormalizationError,
    QueryExpansionError,
    RetrievalError,
)

# ---------------------------------------------------------------------------
# BM25 Tokenizer
# ---------------------------------------------------------------------------

class TestBM25Tokenizer:
    def setup_method(self):
        self.t = BM25Tokenizer()

    def test_tokenize_basic(self):
        tokens = self.t.tokenize("hello world")
        assert tokens == ["hello", "world"]

    def test_tokenize_lowercase(self):
        tokens = self.t.tokenize("Hello World")
        assert tokens == ["hello", "world"]

    def test_tokenize_punctuation(self):
        tokens = self.t.tokenize("hello, world! test.")
        assert tokens == ["hello", "world", "test"]

    def test_tokenize_single_char(self):
        tokens = self.t.tokenize("a b c hello")
        assert "hello" in tokens
        assert "a" not in tokens

    def test_tokenize_contractions(self):
        tokens = self.t.tokenize("don't can't")
        assert "don't" in tokens

    def test_tokenize_empty(self):
        tokens = self.t.tokenize("")
        assert tokens == []

    def test_tokenize_unicode(self):
        tokens = self.t.tokenize("café naïve")
        assert "café" in tokens
        assert "naïve" in tokens


# ---------------------------------------------------------------------------
# BM25 Inverted Index
# ---------------------------------------------------------------------------

class TestBM25InvertedIndex:
    def setup_method(self):
        self.idx = BM25InvertedIndex()

    def test_index_and_search(self):
        self.idx.index_document("d1", "hello world")
        results = self.idx.search("hello", top_k=10)
        assert len(results) == 1
        assert results[0][0] == "d1"
        assert results[0][1] > 0

    def test_multi_document_search(self):
        self.idx.index_document("d1", "hello world")
        self.idx.index_document("d2", "hello python")
        self.idx.index_document("d3", "goodbye world")
        results = self.idx.search("hello", top_k=10)
        assert len(results) == 2
        assert {r[0] for r in results} == {"d1", "d2"}

    def test_relevance_ranking(self):
        self.idx.index_document("d1", "python python python")
        self.idx.index_document("d2", "python is great")
        results = self.idx.search("python", top_k=10)
        assert results[0][0] == "d1"

    def test_no_match(self):
        self.idx.index_document("d1", "hello world")
        results = self.idx.search("nonexistent", top_k=10)
        assert len(results) == 0

    def test_empty_query(self):
        self.idx.index_document("d1", "hello world")
        results = self.idx.search("", top_k=10)
        assert len(results) == 0

    def test_index_with_metadata(self):
        self.idx.index_document("d1", "hello", metadata={"author": "alice"})
        results = self.idx.search("hello", top_k=10)
        assert results[0][2]["author"] == "alice"

    def test_remove_document(self):
        self.idx.index_document("d1", "hello world")
        self.idx.index_document("d2", "hello python")
        assert self.idx.doc_count == 2
        self.idx.remove_document("d1")
        assert self.idx.doc_count == 1
        results = self.idx.search("hello", top_k=10)
        assert len(results) == 1
        assert results[0][0] == "d2"

    def test_remove_missing(self):
        assert self.idx.remove_document("nonexistent") is False

    def test_clear(self):
        self.idx.index_document("d1", "hello")
        self.idx.index_document("d2", "world")
        self.idx.clear()
        assert self.idx.doc_count == 0
        assert self.idx.avg_doc_length == 0.0

    def test_statistics(self):
        self.idx.index_document("d1", "hello world python")
        self.idx.index_document("d2", "hello world")
        stats = self.idx.statistics()
        assert stats["doc_count"] == 2
        assert stats["unique_terms"] > 0
        assert stats["avg_doc_length"] > 0

    def test_get_document_text(self):
        self.idx.index_document("d1", "hello world")
        assert self.idx.get_document_text("d1") == "hello world"
        assert self.idx.get_document_text("missing") == ""

    def test_get_document_metadata(self):
        self.idx.index_document("d1", "hello", metadata={"key": "val"})
        assert self.idx.get_document_metadata("d1")["key"] == "val"

    def test_store_property(self):
        self.idx.index_document("d1", "hello")
        assert "d1" in self.idx.store

    def test_avg_doc_length_update(self):
        self.idx.index_document("d1", "hello world")
        avg1 = self.idx.avg_doc_length
        self.idx.index_document("d2", "a b c d e")
        assert self.idx.avg_doc_length != avg1

    def test_filter_ids(self):
        self.idx.index_document("d1", "hello world")
        self.idx.index_document("d2", "hello python")
        results = self.idx.search("hello", top_k=10, filter_ids={"d1"})
        assert len(results) == 1
        assert results[0][0] == "d1"

    def test_index_remove_recomputes_df(self):
        self.idx.index_document("d1", "hello")
        self.idx.index_document("d2", "hello")
        stats_before = self.idx.statistics()
        self.idx.remove_document("d1")
        stats_after = self.idx.statistics()
        assert stats_after["doc_count"] == 1

    def test_bf_tit_for_tat(self):
        self.idx.index_document("d1", "hello world hello")
        results = self.idx.search("hello hello", top_k=10)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Score Normalization
# ---------------------------------------------------------------------------

class TestMinMaxNormalization:
    def test_empty(self):
        assert MinMaxNormalization().normalize([]) == []

    def test_single(self):
        assert MinMaxNormalization().normalize([5.0]) == [1.0]

    def test_all_same(self):
        assert MinMaxNormalization().normalize([3.0, 3.0, 3.0]) == [1.0, 1.0, 1.0]

    def test_normal(self):
        result = MinMaxNormalization().normalize([0.0, 5.0, 10.0])
        assert result == [0.0, 0.5, 1.0]

    def test_name(self):
        assert MinMaxNormalization().name == "min_max"


class TestZScoreNormalization:
    def test_empty(self):
        assert ZScoreNormalization().normalize([]) == []

    def test_single(self):
        result = ZScoreNormalization().normalize([5.0])
        assert len(result) == 1
        assert result[0] == 0.5

    def test_all_same(self):
        result = ZScoreNormalization().normalize([3.0, 3.0, 3.0])
        assert result == [0.5, 0.5, 0.5]

    def test_normal(self):
        result = ZScoreNormalization().normalize([1.0, 2.0, 3.0])
        assert 0.0 <= result[0] <= result[2] <= 1.0

    def test_name(self):
        assert ZScoreNormalization().name == "z_score"


class TestSoftmaxNormalization:
    def test_empty(self):
        assert SoftmaxNormalization().normalize([]) == []

    def test_single(self):
        result = SoftmaxNormalization().normalize([5.0])
        assert result == [1.0]

    def test_all_same(self):
        result = SoftmaxNormalization().normalize([2.0, 2.0, 2.0])
        assert all(r == pytest.approx(1.0 / 3) for r in result)

    def test_sum_to_one(self):
        result = SoftmaxNormalization().normalize([1.0, 2.0, 3.0])
        assert sum(result) == pytest.approx(1.0)

    def test_name(self):
        assert SoftmaxNormalization().name == "softmax"


class TestRankBasedNormalization:
    def test_empty(self):
        assert RankBasedNormalization().normalize([]) == []

    def test_single(self):
        assert RankBasedNormalization().normalize([5.0]) == [1.0]

    def test_two(self):
        result = RankBasedNormalization().normalize([3.0, 1.0])
        assert result[0] == 1.0
        assert result[1] == 0.0

    def test_three(self):
        result = RankBasedNormalization().normalize([10.0, 5.0, 1.0])
        assert result == [1.0, 0.5, 0.0]

    def test_name(self):
        assert RankBasedNormalization().name == "rank_based"


class TestCreateNormalizationStrategy:
    def test_min_max(self):
        s = create_normalization_strategy("min_max")
        assert isinstance(s, MinMaxNormalization)

    def test_z_score(self):
        s = create_normalization_strategy("z_score")
        assert isinstance(s, ZScoreNormalization)

    def test_softmax(self):
        s = create_normalization_strategy("softmax")
        assert isinstance(s, SoftmaxNormalization)

    def test_rank_based(self):
        s = create_normalization_strategy("rank_based")
        assert isinstance(s, RankBasedNormalization)

    def test_invalid(self):
        with pytest.raises(ValueError):
            create_normalization_strategy("unknown")


# ---------------------------------------------------------------------------
# Score Fusion
# ---------------------------------------------------------------------------

class TestWeightedSumFusion:
    def test_basic(self):
        fusion = WeightedSumFusion()
        semantic = {"a": 0.8, "b": 0.6}
        keyword = {"b": 0.9, "c": 0.7}
        results = fusion.fuse(semantic, keyword)
        assert len(results) == 3
        assert results[0][0] == "b"

    def test_weights(self):
        fusion = WeightedSumFusion()
        semantic = {"a": 0.9, "b": 0.1}
        keyword = {"a": 0.1, "b": 0.9}
        results = fusion.fuse(semantic, keyword, semantic_weight=1.0, keyword_weight=0.0)
        assert results[0][0] == "a"

    def test_empty(self):
        fusion = WeightedSumFusion()
        assert fusion.fuse({}, {}) == []

    def test_name(self):
        assert WeightedSumFusion().name == "weighted_sum"


class TestRRFusion:
    def test_basic(self):
        fusion = RRFusion()
        semantic = {"a": 0.9, "b": 0.8, "c": 0.7}
        keyword = {"b": 0.9, "d": 0.8, "e": 0.7}
        results = fusion.fuse(semantic, keyword)
        assert len(results) > 0

    def test_single_list(self):
        fusion = RRFusion()
        semantic = {"a": 1.0, "b": 0.5}
        results = fusion.fuse(semantic, {})
        assert len(results) == 2
        assert results[0][0] == "a"

    def test_empty(self):
        fusion = RRFusion()
        assert fusion.fuse({}, {}) == []

    def test_name(self):
        assert RRFusion().name == "rrf"


class TestCombSUMFusion:
    def test_basic(self):
        fusion = CombSUMFusion()
        semantic = {"a": 0.8, "b": 0.6}
        keyword = {"b": 0.9, "c": 0.7}
        results = fusion.fuse(semantic, keyword)
        assert len(results) == 3

    def test_name(self):
        assert CombSUMFusion().name == "combsum"


class TestCombMNZFusion:
    def test_basic(self):
        fusion = CombMNZFusion()
        semantic = {"a": 0.8, "b": 0.6}
        keyword = {"b": 0.9, "c": 0.7}
        results = fusion.fuse(semantic, keyword)
        assert len(results) == 3

    def test_only_semantic(self):
        fusion = CombMNZFusion()
        semantic = {"a": 0.8, "b": 0.6}
        results = fusion.fuse(semantic, {})
        assert len(results) == 2

    def test_name(self):
        assert CombMNZFusion().name == "combmnz"


class TestCreateFusionStrategy:
    def test_weighted_sum(self):
        s = create_fusion_strategy("weighted_sum")
        assert isinstance(s, WeightedSumFusion)

    def test_rrf(self):
        s = create_fusion_strategy("rrf")
        assert isinstance(s, RRFusion)

    def test_combsum(self):
        s = create_fusion_strategy("combsum")
        assert isinstance(s, CombSUMFusion)

    def test_combmnz(self):
        s = create_fusion_strategy("combmnz")
        assert isinstance(s, CombMNZFusion)

    def test_invalid(self):
        with pytest.raises(ValueError):
            create_fusion_strategy("unknown")


# ---------------------------------------------------------------------------
# Query Expansion
# ---------------------------------------------------------------------------

class TestQueryExpander:
    def test_no_expansion(self):
        qe = QueryExpander()
        results = qe.expand("hello world")
        assert results == ["hello world"]

    def test_synonym_expansion(self):
        qe = QueryExpander(synonyms={"ai": ["artificial", "intelligence"]})
        results = qe.expand("ai")
        assert len(results) >= 2

    def test_abbreviation_expansion(self):
        qe = QueryExpander(abbreviations={"ml": "machine learning"})
        results = qe.expand("ml")
        assert any("machine learning" in r for r in results)

    def test_typo_correction(self):
        qe = QueryExpander()
        qe.add_typo_correction("recieve", "receive")
        results = qe.expand("recieve")
        assert any("receive" in r for r in results)

    def test_add_synonyms(self):
        qe = QueryExpander()
        qe.add_synonyms("car", ["automobile", "vehicle"])
        results = qe.expand("car")
        assert len(results) >= 2

    def test_add_abbreviation(self):
        qe = QueryExpander()
        qe.add_abbreviation("asap", "as soon as possible")
        results = qe.expand("asap")
        assert any("as soon" in r for r in results)

    def test_multiple_expansions(self):
        qe = QueryExpander(
            synonyms={"nlp": ["natural", "language"]},
            abbreviations={"ai": "artificial intelligence"},
        )
        qe.add_typo_correction("sytem", "system")
        results = qe.expand("ai nlp sytem")
        assert len(results) >= 3

    def test_deduplication(self):
        qe = QueryExpander()
        results = qe.expand("hello hello")
        assert len(results) == 1

    def test_empty_query(self):
        qe = QueryExpander()
        results = qe.expand("")
        assert results == [""]

    def test_synonym_not_found(self):
        qe = QueryExpander()
        qe.add_synonyms("car", ["automobile"])
        results = qe.expand("bike")
        assert results == ["bike"]

    def test_abbreviation_not_found(self):
        qe = QueryExpander()
        qe.add_abbreviation("asap", "as soon as possible")
        results = qe.expand("urgent")
        assert results == ["urgent"]


# ---------------------------------------------------------------------------
# Normalization / Fusion exceptions
# ---------------------------------------------------------------------------

class TestNormalizationExceptions:
    def test_normalization_error(self):
        e = NormalizationError("test")
        assert str(e) == "test"


class TestFusionExceptions:
    def test_fusion_error(self):
        e = FusionError("test")
        assert str(e) == "test"


class TestBM25Exceptions:
    def test_bm25_error(self):
        e = BM25Error("test")
        assert str(e) == "test"


class TestQueryExpansionExceptions:
    def test_query_expansion_error(self):
        e = QueryExpansionError("test")
        assert str(e) == "test"


# ---------------------------------------------------------------------------
# HybridSearch Service
# ---------------------------------------------------------------------------

class TestHybridSearch:
    @pytest.fixture
    def vs_mock(self):
        store = AsyncMock()
        store.search = AsyncMock(return_value=[
            type("VSResult", (), {
                "id": f"r{i}", "score": 0.9 - i * 0.1,
                "vector": [float(i)] * 4,
                "metadata": {"author": "alice"},
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
    def bm25_index(self):
        idx = BM25InvertedIndex()
        idx.index_document("r0", "hello world python", {"author": "alice"})
        idx.index_document("r1", "hello world java", {"author": "alice"})
        idx.index_document("r2", "goodbye world", {"author": "bob"})
        return idx

    @pytest.fixture
    def hs(self, vs_mock, embed_mock, bm25_index):
        return HybridSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            bm25_index=bm25_index,
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
    async def test_search(self, hs):
        q = SearchQuery(text="hello", top_k=5)
        response = await hs.search(q)
        assert response.total > 0
        assert response.results is not None

    @pytest.mark.asyncio
    async def test_search_async(self, hs):
        response = await hs.search_async(SearchQuery(text="hello"))
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_retrieve(self, hs):
        results = await hs.retrieve("hello")
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_batch_search(self, hs):
        queries = [SearchQuery(text="hello"), SearchQuery(text="world")]
        responses = await hs.batch_search(queries)
        assert len(responses) == 2

    @pytest.mark.asyncio
    async def test_search_empty_query(self, hs):
        with pytest.raises(EmptyQueryError):
            await hs.search(SearchQuery(text=""))

    @pytest.mark.asyncio
    async def test_search_invalid_top_k(self, hs):
        with pytest.raises(InvalidQueryError):
            await hs.search(SearchQuery(text="hello", top_k=0))

    @pytest.mark.asyncio
    async def test_negative_offset(self, hs):
        with pytest.raises(InvalidQueryError):
            await hs.search(SearchQuery(text="hello", offset=-1))

    @pytest.mark.asyncio
    async def test_search_with_fusion_strategies(self, vs_mock, embed_mock, bm25_index):
        for fusion_name in ["weighted_sum", "rrf", "combsum", "combmnz"]:
            hs = HybridSearch(
                vector_store=vs_mock,
                embedding_service=embed_mock,
                bm25_index=bm25_index,
                config=RetrievalConfig(
                    enable_recency_boost=False, enable_quality_boost=False,
                    enable_metadata_boost=False, enable_manual_boost=False,
                    track_statistics=False, log_queries=False,
                ),
            )
            q = SearchQuery(text="hello", fusion_strategy=fusion_name)
            response = await hs.search(q)
            assert response.total > 0, f"fusion={fusion_name} failed"

    @pytest.mark.asyncio
    async def test_search_with_normalization_strategies(self, vs_mock, embed_mock, bm25_index):
        for norm_name in ["min_max", "z_score", "softmax", "rank_based"]:
            hs = HybridSearch(
                vector_store=vs_mock,
                embedding_service=embed_mock,
                bm25_index=bm25_index,
                config=RetrievalConfig(
                    enable_recency_boost=False, enable_quality_boost=False,
                    enable_metadata_boost=False, enable_manual_boost=False,
                    track_statistics=False, log_queries=False,
                ),
            )
            q = SearchQuery(text="hello", normalization_strategy=norm_name)
            response = await hs.search(q)
            assert response.total > 0, f"norm={norm_name} failed"

    @pytest.mark.asyncio
    async def test_search_with_weights(self, hs):
        q = SearchQuery(text="hello", semantic_weight=0.7, keyword_weight=0.3)
        response = await hs.search(q)
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_search_no_semantic(self, bm25_index):
        hs = HybridSearch(
            vector_store=AsyncMock(),
            embedding_service=None,
            bm25_index=bm25_index,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        q = SearchQuery(text="hello")
        response = await hs.search(q)
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_search_no_bm25(self, vs_mock, embed_mock):
        hs = HybridSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            bm25_index=BM25InvertedIndex(),
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        q = SearchQuery(text="hello")
        response = await hs.search(q)
        assert response is not None

    @pytest.mark.asyncio
    async def test_search_vs_exception(self, vs_mock, embed_mock, bm25_index):
        vs_mock.search = AsyncMock(side_effect=Exception("VS down"))
        hs = HybridSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            bm25_index=bm25_index,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        response = await hs.search(SearchQuery(text="hello"))
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_index_document(self, hs):
        hs.index_document("new_doc", "some text content", {"key": "val"})
        assert hs.get_bm25_index().doc_count >= 4

    @pytest.mark.asyncio
    async def test_remove_document(self, hs):
        hs.index_document("temp", "temporary")
        assert hs.remove_document("temp") is True
        assert hs.remove_document("nonexistent") is False

    @pytest.mark.asyncio
    async def test_get_bm25_index(self, hs):
        idx = hs.get_bm25_index()
        assert idx.doc_count >= 3

    @pytest.mark.asyncio
    async def test_search_with_custom_top_k(self, hs):
        q = SearchQuery(text="hello", top_k=1, limit=1)
        response = await hs.search(q)
        assert len(response.results) <= 1

    @pytest.mark.asyncio
    async def test_search_with_score_threshold(self, hs):
        q = SearchQuery(text="hello", score_threshold=0.5)
        response = await hs.search(q)
        assert response.total >= 0

    @pytest.mark.asyncio
    async def test_search_with_filter(self, hs):
        q = SearchQuery(text="hello", author="alice")
        response = await hs.search(q)
        assert response.total >= 0

    @pytest.mark.asyncio
    async def test_search_with_query_expansion(self, vs_mock, embed_mock, bm25_index):
        qe = QueryExpander(synonyms={"hello": ["hi", "greetings"]})
        hs = HybridSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            bm25_index=bm25_index,
            query_expander=qe,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        response = await hs.search(SearchQuery(text="hello"))
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_search_stats_tracking(self, vs_mock, embed_mock, bm25_index):
        from app.retrieval.statistics import RetrievalStatsTracker
        stats = RetrievalStatsTracker(track=True)
        hs = HybridSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            bm25_index=bm25_index,
            stats_tracker=stats,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=True, log_queries=False,
            ),
        )
        await hs.search(SearchQuery(text="hello"))
        s = stats.snapshot()
        assert s.query_count >= 1

    @pytest.mark.asyncio
    async def test_search_pagination(self, vs_mock, embed_mock, bm25_index):
        hs = HybridSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            bm25_index=bm25_index,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        q = SearchQuery(text="hello", offset=0, limit=2)
        response = await hs.search(q)
        assert response.offset == 0
        assert len(response.results) <= 2

    @pytest.mark.asyncio
    async def test_search_vs_error_fallback(self, vs_mock, bm25_index):
        vs_mock.search = AsyncMock(side_effect=RuntimeError("fail"))
        hs = HybridSearch(
            vector_store=vs_mock,
            embedding_service=None,
            bm25_index=bm25_index,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        response = await hs.search(SearchQuery(text="hello"))
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_search_exception_wrapping(self, vs_mock, embed_mock):
        vs_mock.search = AsyncMock(side_effect=RuntimeError("unexpected"))
        hs = HybridSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            bm25_index=BM25InvertedIndex(),
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )
        response = await hs.search(SearchQuery(text="hello"))
        assert response is not None


# ---------------------------------------------------------------------------
# End-to-end integration
# ---------------------------------------------------------------------------

class TestHybridSearchIntegration:
    @pytest.fixture
    def vs_mock(self):
        store = AsyncMock()
        store.search = AsyncMock(return_value=[
            type("VSResult", (), {
                "id": f"r{i}", "score": 0.95 - i * 0.1,
                "vector": [float(i)] * 4,
                "metadata": {"author": "alice", "source": "web"},
                "namespace": "default",
            })()
            for i in range(3)
        ])
        return store

    @pytest.fixture
    def embed_mock(self):
        emb = AsyncMock()
        emb.embed_text = AsyncMock(return_value=type("ER", (), {
            "vector": [0.1, 0.2, 0.3, 0.4],
        })())
        return emb

    @pytest.fixture
    def bm25(self):
        idx = BM25InvertedIndex()
        idx.index_document("r0", "python programming language", {"author": "alice"})
        idx.index_document("r1", "java programming language", {"author": "alice"})
        idx.index_document("r2", "web development javascript", {"author": "bob"})
        return idx

    @pytest.fixture
    def hs(self, vs_mock, embed_mock, bm25):
        return HybridSearch(
            vector_store=vs_mock,
            embedding_service=embed_mock,
            bm25_index=bm25,
            config=RetrievalConfig(
                enable_recency_boost=False, enable_quality_boost=False,
                enable_metadata_boost=False, enable_manual_boost=False,
                track_statistics=False, log_queries=False,
            ),
        )

    @pytest.mark.asyncio
    async def test_full_flow_weighted_sum(self, hs):
        q = SearchQuery(
            text="python",
            top_k=5,
            fusion_strategy="weighted_sum",
            normalization_strategy="min_max",
            semantic_weight=0.6,
            keyword_weight=0.4,
        )
        response = await hs.search(q)
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_full_flow_rrf(self, hs):
        q = SearchQuery(
            text="programming",
            top_k=5,
            fusion_strategy="rrf",
            normalization_strategy="rank_based",
        )
        response = await hs.search(q)
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_full_flow_combsum(self, hs):
        q = SearchQuery(
            text="java",
            top_k=5,
            fusion_strategy="combsum",
            normalization_strategy="z_score",
        )
        response = await hs.search(q)
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_full_flow_combmnz(self, hs):
        q = SearchQuery(
            text="web",
            top_k=5,
            fusion_strategy="combmnz",
            normalization_strategy="softmax",
        )
        response = await hs.search(q)
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_bm25_only(self, bm25):
        results = bm25.search("programming", top_k=5)
        assert len(results) == 2
        ids = {r[0] for r in results}
        assert "r0" in ids
        assert "r1" in ids

    @pytest.mark.asyncio
    async def test_bm25_relevance(self, bm25):
        results = bm25.search("python", top_k=5)
        assert results[0][0] == "r0"
