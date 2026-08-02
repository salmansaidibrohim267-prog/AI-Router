from __future__ import annotations

import math
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.reranker.config import RerankerConfig
from app.reranker.models import RerankerInput, RerankerMetrics, RerankerResult, RerankerResponse
from app.reranker.exceptions import (
    RerankerCacheError,
    RerankerError,
    RerankerInputError,
    RerankerModelError,
    RerankerTimeoutError,
)
from app.reranker.protocol import BaseReranker
from app.reranker.calibration import (
    CalibrationStrategy,
    MinMaxCalibration,
    SigmoidCalibration,
    SoftmaxCalibration,
    ZScoreCalibration,
    create_calibration_strategy,
)
from app.reranker.caching import RerankerCache
from app.reranker.pipeline import CandidateSelectionPipeline
from app.reranker.logging import RerankerLogger
from app.reranker.statistics import RerankerMetricsTracker
from app.reranker.providers import RuleBasedReranker, CrossEncoderReranker, EnsembleReranker
from app.reranker import create_reranker
from app.reranker.providers.cross_encoder import HAS_CROSS_ENCODER

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TestRerankerModels:
    def test_reranker_result(self):
        r = RerankerResult(id="r1", score=0.95)
        d = r.to_dict()
        assert d["id"] == "r1"
        assert d["score"] == 0.95
        assert d["rank"] == 0

    def test_reranker_result_with_fields(self):
        r = RerankerResult(
            id="r1", score=0.95, original_score=0.8,
            calibrated_score=0.95, rank=1,
            metadata={"key": "val"}, model="test",
        )
        d = r.to_dict()
        assert d["original_score"] == 0.8
        assert d["rank"] == 1
        assert d["model"] == "test"

    def test_reranker_response(self):
        r = RerankerResponse(results=[], total=0, query_time_ms=1.5)
        d = r.to_dict()
        assert d["total"] == 0
        assert d["query_time_ms"] == 1.5

    def test_reranker_response_with_results(self):
        result = RerankerResult(id="r1", score=0.95)
        r = RerankerResponse(
            results=[result], total=1, model="test", cache_hit=True,
        )
        d = r.to_dict()
        assert len(d["results"]) == 1
        assert d["cache_hit"] is True

    def test_reranker_metrics(self):
        m = RerankerMetrics(
            total_requests=10, total_latency_ms=100.0,
            average_latency_ms=10.0, cache_hits=5, cache_misses=2,
            total_candidates_reranked=100, errors=1,
        )
        d = m.to_dict()
        assert d["total_requests"] == 10
        assert d["cache_hits"] == 5
        assert d["average_latency_ms"] == 10.0

    def test_reranker_metrics_defaults(self):
        m = RerankerMetrics()
        d = m.to_dict()
        assert d["total_requests"] == 0

    def test_reranker_input(self):
        inp = RerankerInput(query="test", candidates=[{"id": "1"}])
        assert inp.query == "test"
        assert len(inp.candidates) == 1


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestRerankerConfig:
    def test_defaults(self):
        c = RerankerConfig()
        assert c.provider == "rule_based"
        assert c.top_k_rerank == 10

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("RERANKER_PROVIDER", "cross_encoder")
        monkeypatch.setenv("RERANKER_TOP_K_RERANK", "20")
        monkeypatch.setenv("RERANKER_CACHE_ENABLED", "0")
        c = RerankerConfig.from_env()
        assert c.provider == "cross_encoder"
        assert c.top_k_rerank == 20
        assert c.cache_enabled is False


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

class TestMinMaxCalibration:
    def test_empty(self):
        assert MinMaxCalibration().calibrate([]) == []

    def test_single(self):
        assert MinMaxCalibration().calibrate([5.0]) == [1.0]

    def test_all_same(self):
        assert MinMaxCalibration().calibrate([3.0, 3.0]) == [1.0, 1.0]

    def test_normal(self):
        result = MinMaxCalibration().calibrate([0.0, 5.0, 10.0])
        assert result == [0.0, 0.5, 1.0]

    def test_name(self):
        assert MinMaxCalibration().name == "min_max"


class TestSoftmaxCalibration:
    def test_empty(self):
        assert SoftmaxCalibration().calibrate([]) == []

    def test_single(self):
        assert SoftmaxCalibration().calibrate([5.0]) == [1.0]

    def test_sum_to_one(self):
        result = SoftmaxCalibration().calibrate([1.0, 2.0, 3.0])
        assert sum(result) == pytest.approx(1.0)

    def test_name(self):
        assert SoftmaxCalibration().name == "softmax"


class TestSigmoidCalibration:
    def test_empty(self):
        assert SigmoidCalibration().calibrate([]) == []

    def test_zero(self):
        result = SigmoidCalibration().calibrate([0.0])
        assert result[0] == pytest.approx(0.5)

    def test_positive(self):
        result = SigmoidCalibration().calibrate([2.0])
        assert result[0] > 0.5

    def test_negative(self):
        result = SigmoidCalibration().calibrate([-2.0])
        assert result[0] < 0.5

    def test_name(self):
        assert SigmoidCalibration().name == "sigmoid"


class TestZScoreCalibration:
    def test_empty(self):
        assert ZScoreCalibration().calibrate([]) == []

    def test_single(self):
        result = ZScoreCalibration().calibrate([5.0])
        assert len(result) == 1

    def test_normal(self):
        result = ZScoreCalibration().calibrate([1.0, 2.0, 3.0])
        assert 0.0 <= result[0] <= result[2] <= 1.0

    def test_name(self):
        assert ZScoreCalibration().name == "z_score"


class TestCreateCalibrationStrategy:
    def test_min_max(self):
        s = create_calibration_strategy("min_max")
        assert isinstance(s, MinMaxCalibration)

    def test_softmax(self):
        s = create_calibration_strategy("softmax")
        assert isinstance(s, SoftmaxCalibration)

    def test_sigmoid(self):
        s = create_calibration_strategy("sigmoid")
        assert isinstance(s, SigmoidCalibration)

    def test_z_score(self):
        s = create_calibration_strategy("z_score")
        assert isinstance(s, ZScoreCalibration)

    def test_invalid(self):
        with pytest.raises(ValueError):
            create_calibration_strategy("unknown")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class TestRerankerCache:
    def setup_method(self):
        self.cache = RerankerCache(ttl=60, max_size=100)

    def test_miss(self):
        result = self.cache.get("query", ["a", "b"], "v1")
        assert result is None

    def test_set_and_get(self):
        results = [RerankerResult(id="a", score=0.9)]
        self.cache.set("query", ["a"], "v1", results)
        cached = self.cache.get("query", ["a"], "v1")
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].id == "a"

    def test_different_query_miss(self):
        results = [RerankerResult(id="a", score=0.9)]
        self.cache.set("query1", ["a"], "v1", results)
        cached = self.cache.get("query2", ["a"], "v1")
        assert cached is None

    def test_invalidate(self):
        results = [RerankerResult(id="a", score=0.9)]
        self.cache.set("q", ["a"], "v1", results)
        assert self.cache.invalidate("q", ["a"], "v1") is True
        assert self.cache.get("q", ["a"], "v1") is None

    def test_invalidate_missing(self):
        assert self.cache.invalidate("missing", ["a"], "v1") is False

    def test_clear(self):
        results = [RerankerResult(id="a", score=0.9)]
        self.cache.set("q1", ["a"], "v1", results)
        self.cache.set("q2", ["b"], "v1", results)
        self.cache.clear()
        assert self.cache.size == 0
        assert self.cache.hits == 0

    def test_statistics(self):
        results = [RerankerResult(id="a", score=0.9)]
        self.cache.get("q", ["a"], "v1")
        self.cache.set("q", ["a"], "v1", results)
        self.cache.get("q", ["a"], "v1")
        stats = self.cache.statistics()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
        assert stats["size"] == 1

    def test_ttl_expiry(self):
        cache = RerankerCache(ttl=0)
        results = [RerankerResult(id="a", score=0.9)]
        cache.set("q", ["a"], "v1", results)
        cached = cache.get("q", ["a"], "v1")
        assert cached is None

    def test_max_size_eviction(self):
        cache = RerankerCache(ttl=3600, max_size=2)
        cache.set("q1", ["a"], "v1", [RerankerResult(id="a", score=1.0)])
        cache.set("q2", ["b"], "v1", [RerankerResult(id="b", score=1.0)])
        cache.set("q3", ["c"], "v1", [RerankerResult(id="c", score=1.0)])
        assert cache.size == 2

    def test_hits_property(self):
        assert self.cache.hits == 0

    def test_misses_property(self):
        assert self.cache.misses == 0


# ---------------------------------------------------------------------------
# RuleBasedReranker
# ---------------------------------------------------------------------------

class TestRuleBasedReranker:
    @pytest.fixture
    def reranker(self):
        return RuleBasedReranker()

    @pytest.mark.asyncio
    async def test_warmup(self, reranker):
        await reranker.warmup()
        assert reranker._warmed

    @pytest.mark.asyncio
    async def test_shutdown(self, reranker):
        await reranker.warmup()
        await reranker.shutdown()
        assert not reranker._warmed

    @pytest.mark.asyncio
    async def test_model_name(self, reranker):
        assert reranker.model_name == "rule_based"

    @pytest.mark.asyncio
    async def test_score_match(self, reranker):
        score = await reranker.score(
            "hello world",
            {"text": "hello world python", "metadata": {}},
        )
        assert score > 0

    @pytest.mark.asyncio
    async def test_score_no_match(self, reranker):
        score = await reranker.score(
            "goodbye",
            {"text": "hello world"},
        )
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_score_empty_query(self, reranker):
        score = await reranker.score("", {"text": "hello"})
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_score_empty_candidate(self, reranker):
        score = await reranker.score("hello", {"text": ""})
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_batch_score(self, reranker):
        candidates = [
            {"text": "hello world", "metadata": {}},
            {"text": "goodbye world", "metadata": {}},
        ]
        scores = await reranker.batch_score("hello", candidates)
        assert len(scores) == 2
        assert scores[0] > scores[1]

    @pytest.mark.asyncio
    async def test_rerank(self, reranker):
        candidates = [
            {"id": "a", "text": "hello world python", "metadata": {}},
            {"id": "b", "text": "goodbye world", "metadata": {}},
            {"id": "c", "text": "hello python programming", "metadata": {}},
        ]
        results = await reranker.rerank("hello python", candidates, top_k=2)
        assert len(results) == 2
        assert results[0].score >= results[1].score
        assert results[0].rank == 1

    @pytest.mark.asyncio
    async def test_rerank_empty(self, reranker):
        results = await reranker.rerank("hello", [])
        assert results == []

    @pytest.mark.asyncio
    async def test_rerank_with_calibration(self):
        reranker = RuleBasedReranker(calibration="softmax")
        candidates = [
            {"id": "a", "text": "hello world", "metadata": {}},
            {"id": "b", "text": "hello python world ml ai", "metadata": {}},
        ]
        results = await reranker.rerank("hello world", candidates, top_k=2)
        assert len(results) == 2
        assert sum(r.score for r in results) == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_score_from_content_field(self, reranker):
        score = await reranker.score("hello", {"content": "hello world"})
        assert score > 0

    @pytest.mark.asyncio
    async def test_score_from_metadata(self, reranker):
        score = await reranker.score("hello", {"text": "", "metadata": {"title": "hello world"}})
        assert score > 0

    @pytest.mark.asyncio
    async def test_rerank_async(self, reranker):
        candidates = [{"id": "a", "text": "hello world", "metadata": {}}]
        results = await reranker.rerank_async("hello", candidates)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# CrossEncoderReranker (skipped if not installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_CROSS_ENCODER, reason="sentence_transformers not installed")
class TestCrossEncoderReranker:
    @pytest.fixture
    def reranker(self):
        return CrossEncoderReranker()

    @pytest.mark.asyncio
    async def test_warmup(self, reranker):
        await reranker.warmup()
        assert reranker._model is not None

    @pytest.mark.asyncio
    async def test_model_name(self, reranker):
        assert "cross-encoder" in reranker.model_name

    @pytest.mark.asyncio
    async def test_score(self, reranker):
        await reranker.warmup()
        score = await reranker.score("hello", {"text": "hello world"})
        assert isinstance(score, float)

    @pytest.mark.asyncio
    async def test_batch_score(self, reranker):
        await reranker.warmup()
        scores = await reranker.batch_score("hello", [
            {"text": "hello world"},
            {"text": "goodbye"},
        ])
        assert len(scores) == 2

    @pytest.mark.asyncio
    async def test_rerank(self, reranker):
        await reranker.warmup()
        results = await reranker.rerank("hello", [
            {"id": "a", "text": "hello world"},
            {"id": "b", "text": "goodbye"},
        ], top_k=2)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# EnsembleReranker
# ---------------------------------------------------------------------------

class TestEnsembleReranker:
    @pytest.fixture
    def r1(self):
        r = AsyncMock(spec=BaseReranker)
        r.model_name = "r1"
        r.score = AsyncMock(return_value=0.8)
        r.batch_score = AsyncMock(return_value=[0.8, 0.6, 0.4])
        r.rerank = AsyncMock(return_value=[RerankerResult(id="a", score=0.8)])
        r.warmup = AsyncMock()
        r.shutdown = AsyncMock()
        return r

    @pytest.fixture
    def r2(self):
        r = AsyncMock(spec=BaseReranker)
        r.model_name = "r2"
        r.score = AsyncMock(return_value=0.6)
        r.batch_score = AsyncMock(return_value=[0.6, 0.8, 0.5])
        r.rerank = AsyncMock(return_value=[RerankerResult(id="b", score=0.6)])
        r.warmup = AsyncMock()
        r.shutdown = AsyncMock()
        return r

    @pytest.fixture
    def ensemble(self, r1, r2):
        return EnsembleReranker([r1, r2], weights=[1.0, 1.0])

    @pytest.mark.asyncio
    async def test_model_name(self, ensemble):
        assert "ensemble" in ensemble.model_name
        assert "r1" in ensemble.model_name
        assert "r2" in ensemble.model_name

    @pytest.mark.asyncio
    async def test_warmup(self, ensemble, r1, r2):
        await ensemble.warmup()
        r1.warmup.assert_awaited_once()
        r2.warmup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown(self, ensemble, r1, r2):
        await ensemble.shutdown()
        r1.shutdown.assert_awaited_once()
        r2.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_score(self, ensemble):
        score = await ensemble.score("q", {"text": "hello"})
        assert score == 0.7

    @pytest.mark.asyncio
    async def test_batch_score(self, ensemble):
        scores = await ensemble.batch_score("q", [{"text": "a"}, {"text": "b"}, {"text": "c"}])
        assert len(scores) == 3

    @pytest.mark.asyncio
    async def test_batch_score_empty(self, ensemble):
        scores = await ensemble.batch_score("q", [])
        assert scores == []

    @pytest.mark.asyncio
    async def test_rerank(self, ensemble):
        candidates = [{"id": "a", "text": "hello"}, {"id": "b", "text": "world"}]
        results = await ensemble.rerank("q", candidates, top_k=2)
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_rerank_empty(self, ensemble):
        results = await ensemble.rerank("q", [])
        assert results == []

    @pytest.mark.asyncio
    async def test_rerank_with_calibration(self, r1, r2):
        ensemble = EnsembleReranker([r1, r2], calibration="softmax")
        candidates = [{"id": "a", "text": "hello"}, {"id": "b", "text": "world"}]
        results = await ensemble.rerank("q", candidates, top_k=2)
        assert results is not None

    def test_no_rerankers(self):
        with pytest.raises(RerankerInputError):
            EnsembleReranker([])

    def test_wrong_weights(self, r1, r2):
        with pytest.raises(RerankerInputError):
            EnsembleReranker([r1, r2], weights=[1.0])


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class TestCandidateSelectionPipeline:
    @pytest.fixture
    def reranker(self):
        return RuleBasedReranker()

    @pytest.fixture
    def pipeline(self, reranker):
        cfg = RerankerConfig(top_k_retrieve=5, top_k_rerank=3, top_k_return=2)
        return CandidateSelectionPipeline(reranker=reranker, config=cfg)

    @pytest.mark.asyncio
    async def test_retrieve_top_under_limit(self, pipeline):
        candidates = [{"id": str(i)} for i in range(3)]
        result = await pipeline.retrieve_top(candidates)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_retrieve_top_over_limit(self, pipeline):
        candidates = [{"id": str(i)} for i in range(10)]
        result = await pipeline.retrieve_top(candidates)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_rerank_top(self, pipeline):
        candidates = [{"id": str(i), "text": "hello world", "metadata": {}} for i in range(5)]
        results = await pipeline.rerank_top("hello", candidates)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_return_top(self, pipeline):
        results = [RerankerResult(id=str(i), score=1.0) for i in range(5)]
        returned = await pipeline.return_top(results)
        assert len(returned) == 2

    @pytest.mark.asyncio
    async def test_run(self, pipeline):
        candidates = [{"id": str(i), "text": "hello world", "metadata": {}} for i in range(10)]
        results = await pipeline.run("hello", candidates)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_run_empty(self, pipeline):
        results = await pipeline.run("hello", [])
        assert results == []


# ---------------------------------------------------------------------------
# Metrics Tracker
# ---------------------------------------------------------------------------

class TestRerankerMetricsTracker:
    def test_snapshot_empty(self):
        t = RerankerMetricsTracker(track=True)
        s = t.snapshot()
        assert s.total_requests == 0

    def test_record_request(self):
        t = RerankerMetricsTracker(track=True)
        t.record_request(10.0, 5)
        s = t.snapshot()
        assert s.total_requests == 1
        assert s.total_latency_ms == 10.0
        assert s.total_candidates_reranked == 5

    def test_cache_hit(self):
        t = RerankerMetricsTracker(track=True)
        t.record_cache_hit()
        t.record_cache_miss()
        s = t.snapshot()
        assert s.cache_hits == 1
        assert s.cache_misses == 1

    def test_error(self):
        t = RerankerMetricsTracker(track=True)
        t.record_error()
        s = t.snapshot()
        assert s.errors == 1

    def test_track_disabled(self):
        t = RerankerMetricsTracker(track=False)
        t.record_request(10.0, 5)
        t.record_cache_hit()
        s = t.snapshot()
        assert s.total_requests == 0
        assert s.cache_hits == 0

    def test_reset(self):
        t = RerankerMetricsTracker(track=True)
        t.record_request(10.0, 5)
        t.reset()
        s = t.snapshot()
        assert s.total_requests == 0

    def test_multiple_requests(self):
        t = RerankerMetricsTracker(track=True)
        t.record_request(10.0, 5)
        t.record_request(20.0, 10)
        s = t.snapshot()
        assert s.total_requests == 2
        assert s.average_latency_ms == 15.0


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class TestRerankerLogger:
    def test_enabled(self):
        logger = RerankerLogger(enabled=True)
        assert logger._enabled is True

    def test_disabled(self):
        logger = RerankerLogger(enabled=False)
        assert logger._enabled is False

    def test_log_rerank(self):
        logger = RerankerLogger(enabled=True)
        logger.log_rerank("query", 10, 5)

    def test_log_result(self):
        logger = RerankerLogger(enabled=True)
        response = RerankerResponse(results=[], total=0)
        logger.log_result("query", response, 1.0)

    def test_log_error(self):
        logger = RerankerLogger(enabled=True)
        logger.log_error("query", ValueError("test"))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestCreateReranker:
    def test_rule_based(self):
        r = create_reranker(RerankerConfig(provider="rule_based"))
        assert isinstance(r, RuleBasedReranker)

    def test_cross_encoder(self):
        r = create_reranker(RerankerConfig(provider="cross_encoder"))
        assert isinstance(r, CrossEncoderReranker)

    def test_ensemble(self):
        r = create_reranker(RerankerConfig(provider="ensemble"))
        assert isinstance(r, EnsembleReranker)

    def test_ensemble_with_weights(self):
        r = create_reranker(RerankerConfig(
            provider="ensemble", ensemble_weights="0.7,0.3",
        ))
        assert isinstance(r, EnsembleReranker)
        assert len(r._weights) == 2

    def test_invalid(self):
        with pytest.raises(ValueError):
            create_reranker(RerankerConfig(provider="unknown"))


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TestRerankerExceptions:
    def test_reranker_error(self):
        e = RerankerError("msg")
        assert str(e) == "msg"

    def test_reranker_model_error(self):
        e = RerankerModelError("model failed")
        assert "model" in str(e)

    def test_reranker_input_error(self):
        e = RerankerInputError("bad input")
        assert "input" in str(e).lower()

    def test_reranker_timeout_error(self):
        e = RerankerTimeoutError("timed out")
        assert "timed" in str(e).lower()

    def test_reranker_cache_error(self):
        e = RerankerCacheError("cache failed")
        assert "cache" in str(e).lower()


# ---------------------------------------------------------------------------
# RuleBasedReranker - Edge Cases
# ---------------------------------------------------------------------------

class TestRuleBasedRerankerEdgeCases:
    @pytest.mark.asyncio
    async def test_candidate_without_id(self):
        reranker = RuleBasedReranker()
        candidates = [{"text": "hello world", "metadata": {}}]
        results = await reranker.rerank("hello", candidates)
        assert len(results) == 1
        assert results[0].id is not None

    @pytest.mark.asyncio
    async def test_score_with_metadata_values(self):
        reranker = RuleBasedReranker()
        score = await reranker.score("hello", {
            "text": "",
            "metadata": {"title": "hello world", "description": "python"},
        })
        assert score > 0

    @pytest.mark.asyncio
    async def test_score_candidate_none_text(self):
        reranker = RuleBasedReranker()
        score = await reranker.score("hello", {"metadata": {"x": "y"}})
        assert score >= 0

    @pytest.mark.asyncio
    async def test_rerank_preserves_order(self):
        reranker = RuleBasedReranker(calibration="min_max")
        candidates = [
            {"id": "z", "text": "hello world python ai ml", "metadata": {}},
            {"id": "a", "text": "hello world", "metadata": {}},
        ]
        results = await reranker.rerank("hello world python", candidates, top_k=2)
        assert results[0].id == "z"


# ---------------------------------------------------------------------------
# CrossEncoderReranker - raises when not installed
# ---------------------------------------------------------------------------

@pytest.mark.skipif(HAS_CROSS_ENCODER, reason="sentence_transformers IS installed")
class TestCrossEncoderRerankerNotInstalled:
    @pytest.mark.asyncio
    async def test_warmup_raises(self):
        reranker = CrossEncoderReranker()
        with pytest.raises(RerankerModelError):
            await reranker.warmup()

    @pytest.mark.asyncio
    async def test_score_raises(self):
        reranker = CrossEncoderReranker()
        with pytest.raises(RerankerModelError):
            await reranker.score("q", {"text": "hello"})


# ---------------------------------------------------------------------------
# Integration: RuleBasedReranker full flow
# ---------------------------------------------------------------------------

class TestRerankerIntegration:
    @pytest.mark.asyncio
    async def test_full_flow(self):
        reranker = RuleBasedReranker(calibration="softmax")
        candidates = [
            {"id": "1", "text": "python programming language for AI", "metadata": {"source": "docs"}},
            {"id": "2", "text": "java programming for enterprise", "metadata": {"source": "docs"}},
            {"id": "3", "text": "web development with javascript", "metadata": {"source": "tutorial"}},
        ]
        results = await reranker.rerank("python AI programming", candidates, top_k=3)
        assert len(results) == 3
        assert results[0].id == "1"
        assert results[0].score >= results[1].score
        assert results[0].rank == 1
        assert results[0].model == "rule_based"
        assert results[0].original_score >= 0
        assert results[0].calibrated_score == pytest.approx(results[0].score)

    @pytest.mark.asyncio
    async def test_pipeline_with_reranker(self):
        cfg = RerankerConfig(top_k_retrieve=10, top_k_rerank=5, top_k_return=3)
        reranker = RuleBasedReranker(calibration="min_max")
        pipeline = CandidateSelectionPipeline(reranker=reranker, config=cfg)
        candidates = [
            {"id": str(i), "text": f"document {i} with some content", "metadata": {}}
            for i in range(20)
        ]
        results = await pipeline.run("document content", candidates)
        assert len(results) == 3
