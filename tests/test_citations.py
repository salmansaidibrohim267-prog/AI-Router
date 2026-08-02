from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.citations.attribution import (
    EmbeddingAttributionStrategy,
    SentenceAttributionMapper,
    SentenceSplitter,
    TokenOverlapAttributionStrategy,
)
from app.citations.builder import CitationResultBuilder
from app.citations.config import CitationConfig
from app.citations.engine import CitationEngine
from app.citations.exceptions import (
    CitationAttributionError,
    CitationError,
    CitationFormatError,
    CitationGenerationError,
    CitationResolutionError,
    CitationScoringError,
    CitationValidationError,
    UnknownCitationFormatError,
)
from app.citations.formats import (
    APACitationFormatter,
    CustomCitationFormatter,
    FormatFactory,
    IEEECitationFormatter,
    JSONCitationFormatter,
    MarkdownCitationFormatter,
    MLACitationFormatter,
    NumericCitationFormatter,
)
from app.citations.logging import CitationLogger
from app.citations.models import (
    Citation,
    CitationFormat,
    CitationMapping,
    CitationMetrics,
    CitationRequest,
    CitationResult,
    CitationSource,
    ValidationResult,
)
from app.citations.resolver import SourceResolver
from app.citations.scoring import CitationScorer
from app.citations.statistics import CitationMetricsTracker
from app.citations.validator import CitationValidator
from app.memory.models import MemoryItem
from app.rag.models import RetrievedChunk


def make_source(
    source_id: str = "s1",
    content: str = "The capital of France is Paris.",
    **kw,
) -> CitationSource:
    defaults = dict(
        title="Geography Notes",
        author="John Smith",
        url="https://example.com/geo",
        published_at="2021-05-01",
        retrieval_score=0.9,
        rerank_score=0.8,
    )
    defaults.update(kw)
    return CitationSource(source_id=source_id, content=content, **defaults)


def make_engine(**kw) -> CitationEngine:
    return CitationEngine(**kw)


# ============================================================
# Config
# ============================================================
class TestConfig:
    def test_defaults(self):
        c = CitationConfig()
        assert c.default_format == "numeric"
        assert c.attribution_threshold == 0.25
        assert c.retrieval_weight == 0.4
        assert c.rerank_weight == 0.35
        assert c.attribution_weight == 0.25
        assert "ieee" in c.supported_formats

    def test_from_env(self):
        os.environ["CITATION_DEFAULT_FORMAT"] = "apa"
        os.environ["CITATION_MAX_SOURCES"] = "5"
        os.environ["CITATION_VALIDATE_ON_GENERATE"] = "0"
        os.environ["CITATION_JSON_INDENT"] = "4"
        try:
            c = CitationConfig.from_env()
            assert c.default_format == "apa"
            assert c.max_sources_per_citation == 5
            assert c.validate_on_generate is False
            assert c.json_indent == 4
        finally:
            for k in ("CITATION_DEFAULT_FORMAT", "CITATION_MAX_SOURCES",
                      "CITATION_VALIDATE_ON_GENERATE", "CITATION_JSON_INDENT"):
                os.environ.pop(k, None)


# ============================================================
# Models
# ============================================================
class TestModels:
    def test_source_auto_id(self):
        s = CitationSource(source_id="", chunk_id="chunk-9")
        assert s.source_id == "chunk-9"

    def test_source_retrieved_at_default(self):
        s = CitationSource(source_id="s1")
        assert s.retrieved_at is not None

    def test_source_year(self):
        assert make_source().year == "2021"
        assert CitationSource(source_id="s1", published_at="").year == ""
        assert CitationSource(source_id="s1", published_at="2022").year == "2022"

    def test_source_author_last(self):
        assert make_source().author_last == "Smith"
        assert CitationSource(source_id="s1", author="K. Lee").author_last == "Lee"
        assert CitationSource(source_id="s1", author="").author_last == ""

    def test_source_to_dict_from_dict_roundtrip(self):
        s = make_source(page="12", section="2.1")
        d = s.to_dict()
        assert d["page"] == "12"
        assert d["content"] == s.content[:200]
        s2 = CitationSource.from_dict(d)
        assert s2.source_id == "s1"
        assert s2.title == "Geography Notes"
        assert s2.retrieval_score == 0.9
        assert s2.metadata == {}

    def test_source_from_dict_defaults(self):
        s = CitationSource.from_dict({})
        assert s.source_id == ""
        assert s.retrieval_score == 0.0
        assert s.content == ""

    def test_citation_mapping_to_dict(self):
        m = CitationMapping(sentence="x", source_ids=["a", "b"], scores={"a": 0.5})
        d = m.to_dict()
        assert d["source_ids"] == ["a", "b"]
        assert d["scores"] == {"a": 0.5}
        assert d["attribution_score"] == 0.0

    def test_citation_to_dict(self):
        c = Citation(citation_id="c1", sentence="x", source_ids=["a"], confidence=0.9)
        d = c.to_dict()
        assert d["citation_id"] == "c1"
        assert d["confidence"] == 0.9
        assert d["format"] == "numeric"
        assert d["verified"] is True

    def test_result_verified(self):
        r = CitationResult(text="x")
        assert r.verified is True
        r.errors.append("boom")
        assert r.verified is False

    def test_result_to_dict(self):
        r = CitationResult(text="t", rendered="r", confidence=0.5,
                           citations=[Citation(citation_id="c1", sentence="s")],
                           sources=[make_source()], mappings=[])
        d = r.to_dict()
        assert d["format"] == "numeric"
        assert d["confidence"] == 0.5
        assert len(d["citations"]) == 1

    def test_validation_result_to_dict(self):
        v = ValidationResult(valid=False, errors=["e"], confidence=0.1)
        d = v.to_dict()
        assert d["valid"] is False
        assert d["checked_citations"] == 0

    def test_metrics_to_dict(self):
        m = CitationMetrics(total_generations=2)
        d = m.to_dict()
        assert d["total_generations"] == 2
        assert "total_latency_ms" in d

    def test_request_defaults(self):
        r = CitationRequest(text="x")
        assert r.format == CitationFormat.NUMERIC
        assert r.resolve is True
        assert r.validate is True
        assert r.options == {}

    def test_result_from_dict_missing(self):
        r = CitationResult(text="")
        assert r.rendered == ""
        assert r.references == ""


# ============================================================
# Attribution
# ============================================================
class TestSentenceSplitter:
    def test_empty(self):
        assert SentenceSplitter().split("") == []
        assert SentenceSplitter().split("   ") == []

    def test_single(self):
        parts = SentenceSplitter().split("Hello world.")
        assert parts == [("Hello world.", 0, 12)]

    def test_multiple(self):
        parts = SentenceSplitter().split("One. Two! Three?")
        assert [p[0] for p in parts] == ["One.", "Two!", "Three?"]

    def test_offsets_contiguous(self):
        parts = SentenceSplitter().split("One. Two.")
        assert parts[0][1] == 0 and parts[0][2] == 4
        assert parts[1][1] == 5 and parts[1][2] == 9

    def test_long_sentence_chunked(self):
        parts = SentenceSplitter().split("a" * 500, max_chars=100)
        assert len(parts) == 5
        assert all(len(p[0]) <= 100 for p in parts)
        assert parts[0][2] == 100

    def test_trailing_whitespace(self):
        parts = SentenceSplitter().split("One.  Two.", max_chars=100)
        assert [p[0] for p in parts] == ["One.", "Two."]


class TestTokenOverlap:
    def test_empty_tokens(self):
        s = TokenOverlapAttributionStrategy()
        assert s.score("", make_source()) == 0.0
        assert s.score("hi", CitationSource(source_id="s", content="")) == 0.0

    def test_overlap(self):
        s = TokenOverlapAttributionStrategy()
        src = make_source(content="The capital of France is Paris.")
        assert s.score("The capital of France is Paris.", src) == 1.0
        assert s.score("The capital of Italy is Rome.", src) == pytest.approx(4 / 6)

    def test_no_overlap(self):
        s = TokenOverlapAttributionStrategy()
        assert s.score("Quantum physics fascinates.", make_source()) == 0.0

    def test_async_matches_sync(self):
        s = TokenOverlapAttributionStrategy()
        src = make_source()
        assert asyncio.run(s.score_async("The capital of France is Paris.", src)) == 1.0


class TestEmbeddingAttribution:
    def test_sync_embedder(self):
        vectors = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
        s = EmbeddingAttributionStrategy(lambda t: vectors[t])
        assert s.score("a", make_source(content="b")) == 0.0
        assert s.score("a", make_source(content="a")) == pytest.approx(1.0)

    def test_embedder_object_vector(self):
        s = EmbeddingAttributionStrategy(lambda t: MagicMock(vector=[1.0, 0.0]))
        assert s.score("x", make_source(content="y")) == pytest.approx(1.0)

    def test_embedder_invalid_result(self):
        s = EmbeddingAttributionStrategy(lambda t: 42)
        with pytest.raises(CitationAttributionError):
            s.score("x", make_source())

    def test_async_embedder_requires_async_scoring(self):
        async def emb(t):
            return [1.0]
        s = EmbeddingAttributionStrategy(emb)
        with pytest.raises(CitationAttributionError):
            s.score("x", make_source())

    def test_async_embedder_async_scoring(self):
        async def emb(t):
            return [1.0, 0.0] if t == "a" else [0.0, 1.0]
        s = EmbeddingAttributionStrategy(emb)
        assert asyncio.run(s.score_async("a", make_source(content="b"))) == 0.0

    def test_cosine_edges(self):
        s = EmbeddingAttributionStrategy(lambda t: [1.0, 0.0] if t == "x" else [0.0, 1.0])
        assert s.score("x", make_source(content="y")) == 0.0
        s2 = EmbeddingAttributionStrategy(lambda t: [0.0, 0.0])
        assert s2.score("x", make_source(content="x")) == 0.0
        s3 = EmbeddingAttributionStrategy(lambda t: [1.0, 2.0, 3.0] if t == "x" else [1.0, 1.0])
        assert s3.score("x", make_source(content="y")) == 0.0


class TestSentenceAttributionMapper:
    def test_mapping_basic(self):
        mapper = SentenceAttributionMapper(TokenOverlapAttributionStrategy(), threshold=0.3)
        src = make_source(content="Gold prices rallied strongly in 2026.")
        mappings = mapper.map("Gold prices rallied strongly in 2026. That is all.",
                              [src])
        assert len(mappings) == 2
        assert mappings[0].source_ids == ["s1"]
        assert mappings[1].source_ids == []
        assert mappings[0].attribution_score == pytest.approx(1.0)
        assert mappings[0].scores["s1"] == pytest.approx(1.0)

    def test_max_sources_per_sentence(self):
        mapper = SentenceAttributionMapper(
            TokenOverlapAttributionStrategy(), threshold=0.1, max_sources_per_sentence=2
        )
        sources = [
            CitationSource(source_id=f"s{i}", content="alpha beta gamma delta epsilon")
            for i in range(4)
        ]
        mappings = mapper.map("alpha beta gamma delta epsilon", sources)
        assert len(mappings[0].source_ids) == 2

    def test_mapper_sorts_by_score(self):
        mapper = SentenceAttributionMapper(TokenOverlapAttributionStrategy(), threshold=0.2)
        low = CitationSource(source_id="low", content="alpha only")
        high = CitationSource(source_id="high", content="alpha beta gamma delta")
        mappings = mapper.map("alpha beta gamma delta", [low, high])
        assert mappings[0].source_ids == ["high", "low"]

    def test_mapper_strategy_error_swallowed(self):
        class Boom:
            name = "boom"
            def score(self, sentence, source):
                raise RuntimeError("x")
        mapper = SentenceAttributionMapper(Boom(), threshold=0.1)
        mappings = mapper.map("hello there", [make_source()])
        assert mappings[0].source_ids == []

    def test_map_async(self):
        mapper = SentenceAttributionMapper(TokenOverlapAttributionStrategy(), threshold=0.3)
        src = make_source(content="Gold prices rallied strongly in 2026.")
        mappings = asyncio.run(mapper.map_async("Gold prices rallied strongly in 2026.", [src]))
        assert mappings[0].source_ids == ["s1"]

    def test_map_async_strategy_error_swallowed(self):
        class Boom:
            name = "boom"
            async def score_async(self, sentence, source):
                raise RuntimeError("x")
        mapper = SentenceAttributionMapper(Boom(), threshold=0.1)
        mappings = asyncio.run(mapper.map_async("hello", [make_source()]))
        assert mappings[0].source_ids == []

    def test_strategy_property(self):
        strategy = TokenOverlapAttributionStrategy()
        mapper = SentenceAttributionMapper(strategy)
        assert mapper.strategy is strategy


# ============================================================
# Resolver
# ============================================================
class TestResolver:
    def test_passthrough(self):
        s = make_source()
        assert SourceResolver().resolve([s]) == [s]

    def test_dict_source(self):
        s = SourceResolver().resolve([{"source_id": "d1", "content": "abc",
                                       "score": 0.7, "title": "T"}])[0]
        assert s.source_id == "d1"
        assert s.content == "abc"
        assert s.retrieval_score == 0.7
        assert s.title == "T"

    def test_retrieved_chunk(self):
        chunk = RetrievedChunk(
            chunk_id="ch-1", content="content here", score=0.9, rerank_score=0.8,
            metadata={"title": "Doc", "author": "A. B", "url": "https://u"},
        )
        s = SourceResolver().resolve([chunk])[0]
        assert s.source_id == "ch-1"
        assert s.content == "content here"
        assert s.retrieval_score == 0.9
        assert s.rerank_score == 0.8
        assert s.title == "Doc"
        assert s.author == "A. B"
        assert s.url == "https://u"

    def test_memory_item(self):
        item = MemoryItem(id="m1", content="prefers x", metadata={"title": "Profile"})
        s = SourceResolver().resolve([item])[0]
        assert s.source_id == "m1"
        assert s.content == "prefers x"
        assert s.title == "Profile"

    def test_generic_content_object(self):
        class Obj:
            content = "hello"
            metadata = {"source_id": "gen-1", "page": "3"}
        s = SourceResolver().resolve([Obj()])[0]
        assert s.source_id == "gen-1"
        assert s.page == "3"

    def test_unsupported_type(self):
        with pytest.raises(CitationResolutionError):
            SourceResolver().resolve([42])

    def test_dedupe(self):
        s = make_source()
        out = SourceResolver().resolve([s, s])
        assert len(out) == 1

    def test_no_dedupe(self):
        config = CitationConfig(dedupe_sources=False)
        s = make_source()
        out = SourceResolver(config).resolve([s, s])
        assert len(out) == 2

    def test_custom_metadata_mapper(self):
        class Widget:
            def __init__(self):
                self.chunk_id = "w1"
                self.content = "widget data"
                self.score = 0.5
                self.metadata = {"author": "W"}

        def mapper(obj):
            return {"page": "9"}

        s = SourceResolver(metadata_mapper=mapper).resolve([Widget()])[0]
        assert s.page == "9"
        assert s.author == "W"

    def test_metadata_mapper_raising_swallowed(self):
        chunk = RetrievedChunk(chunk_id="c", content="x", score=0.1)
        resolver = SourceResolver(metadata_mapper=lambda o: (_ for _ in ()).throw(RuntimeError()))
        s = resolver.resolve([chunk])[0]
        assert s.source_id == "c"

    def test_from_rag_chunks(self):
        chunks = [
            RetrievedChunk(chunk_id=f"c{i}", content=f"content {i}", score=0.1 * i)
            for i in range(3)
        ]
        out = SourceResolver.from_rag_chunks(chunks)
        assert [s.source_id for s in out] == ["c0", "c1", "c2"]

    def test_resolve_async(self):
        out = asyncio.run(SourceResolver().resolve_async([make_source()]))
        assert len(out) == 1

    def test_resolver_invalid_dict_value(self):
        with pytest.raises(CitationResolutionError):
            SourceResolver().resolve([{"source_id": "x", "retrieval_score": "nope"}])
        with pytest.raises((ValueError, TypeError)):
            CitationSource.from_dict({"retrieval_score": "nope"})

    def test_resolver_error_wrapped(self):
        class Bad:
            chunk_id = "c"
            content = "x"
            score = "not-a-float"
        with pytest.raises(CitationResolutionError):
            SourceResolver().resolve([Bad()])

    def test_source_id_fallback_to_chunk_id(self):
        chunk = RetrievedChunk(chunk_id="only", content="x", score=0.5)
        s = SourceResolver().resolve([chunk])[0]
        assert s.source_id == "only"

    def test_source_retrieved_at_kept(self):
        s = SourceResolver().resolve([make_source(retrieved_at=123.0)])[0]
        assert s.retrieved_at == 123.0


# ============================================================
# Scoring
# ============================================================
class TestScorer:
    def test_score_weights(self):
        scorer = CitationScorer()
        s = make_source(retrieval_score=1.0, rerank_score=1.0)
        assert scorer.score(s, 1.0) == pytest.approx(1.0)
        assert scorer.score(s, 0.0) == pytest.approx(0.75)

    def test_score_clamps(self):
        scorer = CitationScorer()
        s = make_source(retrieval_score=2.0, rerank_score=-1.0)
        assert scorer.score(s, 1.0) == pytest.approx(0.65)

    def test_score_invalid_attribution(self):
        scorer = CitationScorer()
        with pytest.raises(CitationScoringError):
            scorer.score(make_source(), 1.5)

    def test_score_citation(self):
        scorer = CitationScorer()
        s = make_source(retrieval_score=1.0, rerank_score=1.0)
        assert scorer.score_citation(["s1"], [s], {"s1": 1.0}) == pytest.approx(1.0)

    def test_score_citation_empty(self):
        assert CitationScorer().score_citation([], []) == 0.0

    def test_score_citation_unknown_ids(self):
        scorer = CitationScorer()
        assert scorer.score_citation(["missing"], [make_source()]) == 0.0

    def test_score_result(self):
        scorer = CitationScorer()
        c1 = Citation(citation_id="c1", sentence="x", source_ids=["s1"], confidence=0.8)
        c2 = Citation(citation_id="c2", sentence="y", source_ids=["s1"], confidence=0.4)
        assert scorer.score_result([c1, c2], [make_source()]) == pytest.approx(0.6)

    def test_score_result_empty(self):
        assert CitationScorer().score_result([], []) == 0.0

    def test_aggregate(self):
        scorer = CitationScorer()
        assert scorer.aggregate([0.5, 0.7]) == pytest.approx(0.6)
        assert scorer.aggregate([]) == 0.0


# ============================================================
# Validator
# ============================================================
class TestValidator:
    def make_result(self, **kw) -> CitationResult:
        defaults = dict(
            text="The capital of France is Paris.",
            citations=[Citation(citation_id="c1", sentence="The capital of France is Paris.",
                                source_ids=["s1"], confidence=0.9)],
            sources=[make_source()],
            mappings=[CitationMapping(sentence="The capital of France is Paris.",
                                      source_ids=["s1"], attribution_score=0.9)],
        )
        defaults.update(kw)
        return CitationResult(**defaults)

    def test_valid(self):
        v = CitationValidator().validate(self.make_result())
        assert v.valid is True
        assert v.checked_citations == 1
        assert v.checked_sources == 1

    def test_no_sources(self):
        v = CitationValidator().validate(self.make_result(sources=[]))
        assert v.valid is False
        assert any("No sources" in e for e in v.errors)

    def test_no_citations(self):
        v = CitationValidator().validate(self.make_result(citations=[]))
        assert v.valid is False
        assert any("No citations" in e for e in v.errors)

    def test_unknown_source_id(self):
        v = CitationValidator().validate(
            self.make_result(citations=[
                Citation(citation_id="c1", sentence="x", source_ids=["ghost"], confidence=0.9)
            ])
        )
        assert v.valid is False
        assert any("unknown source" in e for e in v.errors)

    def test_empty_source_ids(self):
        r = CitationResult(
            text="x",
            citations=[Citation(citation_id="c1", sentence="x", source_ids=[], confidence=0.9)],
            sources=[make_source()],
        )
        v = CitationValidator().validate(r)
        assert v.valid is False
        assert any("No supporting sources" in e for e in v.errors)

    def test_low_confidence(self):
        v = CitationValidator().validate(
            self.make_result(citations=[
                Citation(citation_id="c1", sentence="x", source_ids=["s1"], confidence=0.1)
            ])
        )
        assert v.valid is False
        assert any("below threshold" in e for e in v.errors)

    def test_unattributed_warning(self):
        v = CitationValidator().validate(
            self.make_result(mappings=[
                CitationMapping(sentence="Nope.", source_ids=[], attribution_score=0.0)
            ])
        )
        assert v.valid is True
        assert any("without supporting" in w for w in v.warnings)

    def test_weak_attribution_warning(self):
        v = CitationValidator().validate(
            self.make_result(mappings=[
                CitationMapping(sentence="x", source_ids=["s1"], attribution_score=0.05)
            ])
        )
        assert v.valid is True
        assert any("weak attribution" in w for w in v.warnings)

    def test_empty_rendered_warning(self):
        v = CitationValidator().validate(self.make_result(rendered="", format=CitationFormat.NUMERIC))
        assert any("Rendered text is empty" in w for w in v.warnings)

    def test_json_format_no_rendered_warning(self):
        v = CitationValidator().validate(
            self.make_result(rendered="", format=CitationFormat.JSON)
        )
        assert not any("Rendered text" in w for w in v.warnings)

    def test_validate_sources(self):
        v = CitationValidator()
        errors = v.validate_sources([make_source(), CitationSource(source_id="", content="")])
        assert len(errors) == 2

    def test_validate_sources_clean(self):
        assert CitationValidator().validate_sources([make_source()]) == []

    def test_validate_async(self):
        v = asyncio.run(CitationValidator().validate_async(self.make_result()))
        assert v.valid is True

    def test_validate_alias(self):
        v = CitationValidator()
        assert v.validate(self.make_result()) == v.validate_result(self.make_result())


# ============================================================
# Formats
# ============================================================
def make_result(citations=1, sources=None, text="Alpha. Beta.", **kw):
    sources = [make_source()] if sources is None else list(sources)
    source_ids = [s.source_id for s in sources] or ["s1"]
    if citations:
        cites = [
            Citation(citation_id=f"c{i + 1}", sentence=sentence,
                     source_ids=list(source_ids), confidence=0.9)
            for i, sentence in enumerate(text.split(". ")[:citations])
        ]
    else:
        cites = []
    return CitationResult(
        text=text,
        citations=cites,
        sources=sources,
        mappings=[],
        confidence=0.9,
        **kw,
    )


class TestFormatsBase:
    def test_pairs_mismatch_falls_back_to_sentence(self):
        r = CitationResult(
            text="One. Two.",
            citations=[Citation(citation_id="c1", sentence="One.", source_ids=["s1"], confidence=0.9)],
            sources=[make_source()],
            mappings=[CitationMapping(sentence="One.", start=0, end=4, source_ids=["s1"]),
                      CitationMapping(sentence="Two.", start=5, end=9, source_ids=["s1"])],
        )
        f = NumericCitationFormatter()
        out = f.render_inline(r)
        assert "[1]" in out

    def test_render_combines_inline_and_references(self):
        f = NumericCitationFormatter()
        r = make_result(citations=2)
        r.mappings = [CitationMapping(sentence="Alpha.", start=0, end=6, source_ids=["s1"]),
                      CitationMapping(sentence="Beta.", start=7, end=13, source_ids=["s1"])]
        out = f.render(r)
        assert "[1]" in out and "[2]" in out
        assert "[1] John Smith, Geography Notes" in out


class TestNumericFormatter:
    def test_inline_positions(self):
        f = NumericCitationFormatter()
        r = make_result(text="The capital of France is Paris. It is a city in Europe.", citations=2)
        r.mappings = [
            CitationMapping(sentence="The capital of France is Paris.", start=0, end=31, source_ids=["s1"]),
            CitationMapping(sentence="It is a city in Europe.", start=32, end=55, source_ids=["s1"]),
        ]
        out = f.render_inline(r)
        assert out == "The capital of France is Paris.[1] It is a city in Europe.[2]"

    def test_references(self):
        f = NumericCitationFormatter()
        r = make_result(text="A. B.", sources=[make_source(page="12")])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert "[1] John Smith, Geography Notes, https://example.com/geo" in f.render_references(r)

    def test_references_empty_entry(self):
        f = NumericCitationFormatter()
        s = CitationSource(source_id="s9", content="x")
        r = make_result(text="A. B.", sources=[s])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s9"])]
        assert "[1] s9" in f.render_references(r)


class TestIEEECitationFormatter:
    def test_marker(self):
        f = IEEECitationFormatter()
        r = make_result(text="A. B.")
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert f.render_inline(r) == "A.[1] B."

    def test_references(self):
        f = IEEECitationFormatter()
        s = make_source(page="5", section="2")
        r = make_result(text="A. B.", sources=[s])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        refs = f.render_references(r)
        assert "John Smith" in refs
        assert '"Geography Notes"' in refs
        assert "p. 5" in refs
        assert "sec. 2" in refs
        assert "2021" in refs

    def test_references_minimal(self):
        f = IEEECitationFormatter()
        s = CitationSource(source_id="s9", content="x")
        r = make_result(text="A. B.", sources=[s])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s9"])]
        assert f.render_references(r) == "[1] s9"


class TestAPACitationFormatter:
    def test_inline_with_page(self):
        f = APACitationFormatter()
        r = make_result(text="A. B.", sources=[make_source(page="12")])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert f.render_inline(r) == "A.(Smith, 2021, p. 12) B."

    def test_inline_no_author(self):
        f = APACitationFormatter()
        s = CitationSource(source_id="s9", content="x", title="Report", published_at="2020")
        r = make_result(text="A. B.", sources=[s])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s9"])]
        assert "n.d." not in f.render_inline(r)
        assert "(Report, 2020)" in f.render_inline(r)

    def test_inline_no_metadata(self):
        f = APACitationFormatter()
        s = CitationSource(source_id="s9", content="x")
        r = make_result(text="A. B.", sources=[s])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s9"])]
        assert "(n.d.)" in f.render_inline(r)

    def test_references_deduplicated(self):
        f = APACitationFormatter()
        r = make_result(text="A. B. C.")
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        refs = f.render_references(r)
        assert refs == "Smith (2021). Geography Notes. Retrieved from https://example.com/geo"

    def test_references_no_author_no_url(self):
        f = APACitationFormatter()
        s = CitationSource(source_id="s9", content="x", title="", filename="report.pdf")
        r = make_result(text="A. B.", sources=[s])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s9"])]
        assert f.render_references(r) == "report.pdf (n.d.)."


class TestMLACitationFormatter:
    def test_inline(self):
        f = MLACitationFormatter()
        r = make_result(text="A. B.", sources=[make_source(page="12")])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert f.render_inline(r) == "A.(Smith 12) B."

    def test_inline_no_page(self):
        f = MLACitationFormatter()
        r = make_result(text="A. B.")
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert f.render_inline(r) == "A.(Smith) B."

    def test_inline_no_author(self):
        f = MLACitationFormatter()
        s = CitationSource(source_id="s9", content="x", filename="notes.txt")
        r = make_result(text="A. B.", sources=[s])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s9"])]
        assert f.render_inline(r) == "A.(notes.txt) B."

    def test_inline_no_source(self):
        f = MLACitationFormatter()
        r = make_result(text="A. B.", sources=[])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert f.render_inline(r) == "A.(n.p.) B."

    def test_references(self):
        f = MLACitationFormatter()
        r = make_result(text="A. B.")
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert f.render_references(r) == 'Smith, John. "Geography Notes." 2021, https://example.com/geo.'

    def test_references_single_name_author(self):
        f = MLACitationFormatter()
        s = CitationSource(source_id="s9", content="x", author="Homer")
        r = make_result(text="A. B.", sources=[s])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s9"])]
        assert f.render_references(r).startswith("Homer.")


class TestMarkdownFormatter:
    def test_inline(self):
        f = MarkdownCitationFormatter()
        r = make_result(text="A. B.")
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert f.render_inline(r) == "A.[^1] B."

    def test_references(self):
        f = MarkdownCitationFormatter()
        r = make_result(text="A. B.", sources=[make_source(page="3")])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        refs = f.render_references(r)
        assert "[^1]: John Smith, *Geography Notes*, p. 3, https://example.com/geo" in refs


class TestJSONFormatter:
    def test_render_payload(self):
        f = JSONCitationFormatter()
        r = make_result()
        r.mappings = [CitationMapping(sentence="Alpha.", start=0, end=6, source_ids=["s1"])]
        payload = json.loads(f.render(r))
        assert payload["text"] == "Alpha. Beta."
        assert len(payload["citations"]) == 1
        assert len(payload["references"]) == 1
        assert payload["references"][0]["source_id"] == "s1"

    def test_render_references_empty(self):
        assert JSONCitationFormatter().render_references(make_result()) == ""

    def test_indent(self):
        f = JSONCitationFormatter(CitationConfig(json_indent=4))
        assert "\n    " in f.render(make_result())

    def test_render_inline_equals_render(self):
        f = JSONCitationFormatter()
        r = make_result()
        assert f.render_inline(r) == f.render(r)


class TestCustomFormatter:
    def test_default_template(self):
        f = CustomCitationFormatter()
        s = make_source()
        assert f._ref_entry(s) == 'John Smith. "Geography Notes." https://example.com/geo'

    def test_custom_template_fields(self):
        f = CustomCitationFormatter(template="{author}|{title}|{year}|{page}|{url}|{index}|{filename}|{section}|{document_id}|{chunk_id}")
        s = make_source(page="2", section="s", filename="f.pdf", document_id="d1", chunk_id="s1")
        assert f._ref_entry(s) == "John Smith|Geography Notes|2021|2|https://example.com/geo||f.pdf|s|d1|s1"

    def test_invalid_template(self):
        f = CustomCitationFormatter(template="{missing_field}")
        with pytest.raises(CitationFormatError):
            f._ref_entry(make_source())

    def test_inline_uses_numeric_markers(self):
        f = CustomCitationFormatter()
        r = make_result(text="A. B.")
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert f.render_inline(r) == "A.[1] B."


class TestFormatFactory:
    def test_create_all_defaults(self):
        f = FormatFactory()
        for name in ("numeric", "ieee", "apa", "mla", "markdown", "json", "custom"):
            assert f.create(name).name == name

    def test_unknown(self):
        with pytest.raises(UnknownCitationFormatError):
            FormatFactory().create("nope")

    def test_register(self):
        f = FormatFactory()

        class Custom:
            name = "myfmt"
            def render_inline(self, r):
                return "inline"
            def render_references(self, r):
                return "refs"
            def render(self, r):
                return "all"

        f.register("myfmt", Custom())
        assert f.create("myfmt").name == "myfmt"
        assert "myfmt" in f.names()

    def test_names(self):
        names = FormatFactory().names()
        assert "numeric" in names and "json" in names

    def test_is_supported(self):
        f = FormatFactory()
        assert f.is_supported("apa")
        assert not f.is_supported("nope")

    def test_register_override_default(self):
        f = FormatFactory()

        class Fake:
            name = "fake"
            def render_inline(self, r):
                return "x"
            def render_references(self, r):
                return "y"
            def render(self, r):
                return "z"

        f.register("numeric", Fake())
        assert f.create("numeric").name == "fake"
        assert "numeric" in f.names()


# ============================================================
# Builder
# ============================================================
class TestBuilder:
    def test_build_defaults(self):
        b = CitationResultBuilder("hello")
        r = b.build()
        assert r.text == "hello"
        assert r.citations == []
        assert r.sources == []
        assert r.rendered == ""
        assert r.confidence == 0.0

    def test_fluent(self):
        b = CitationResultBuilder("t")
        r = (b.with_text("t2")
              .with_format("apa")
              .with_sources([make_source()])
              .add_source(make_source(source_id="s2"))
              .with_mappings([CitationMapping(sentence="a", source_ids=["s1"])])
              .add_mapping(CitationMapping(sentence="b"))
              .with_citations([Citation(citation_id="c1", sentence="a", source_ids=["s1"])])
              .add_citation(Citation(citation_id="c2", sentence="b"))
              .with_rendered("r")
              .with_references("refs")
              .with_confidence(1.5)
              .with_errors(["e"])
              .add_error("e2")
              .with_warnings(["w"])
              .add_warning("w2")
              .build())
        assert r.text == "t2"
        assert r.format == CitationFormat.APA
        assert len(r.sources) == 2
        assert len(r.mappings) == 2
        assert len(r.citations) == 2
        assert r.confidence == 1.0
        assert r.errors == ["e", "e2"]
        assert r.warnings == ["w", "w2"]
        assert r.rendered == "r"
        assert r.references == "refs"

    def test_string_format(self):
        r = CitationResultBuilder("t", "markdown").build()
        assert r.format == CitationFormat.MARKDOWN

    def test_reset(self):
        b = CitationResultBuilder("t").add_error("e")
        b.reset()
        r = b.build()
        assert r.errors == []
        assert r.citations == []


# ============================================================
# Engine
# ============================================================
class TestEngine:
    def test_generate_basic(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        assert len(r.citations) == 1
        assert r.citations[0].source_ids == ["s1"]
        assert r.confidence > 0.5
        assert r.errors == []
        assert "[1]" in r.rendered
        assert "References" not in r.rendered

    def test_generate_with_request_object(self):
        e = make_engine()
        req = CitationRequest(text="The capital of France is Paris.", sources=[make_source()])
        r = e.generate(request=req)
        assert r.citations[0].source_ids == ["s1"]

    def test_generate_unknown_format_raises(self):
        e = make_engine()
        with pytest.raises(UnknownCitationFormatError):
            e.generate("x", sources=[make_source()], fmt="bogus")

    def test_generate_invalid_format_type(self):
        e = make_engine()
        with pytest.raises(CitationGenerationError):
            e.generate("x", sources=[make_source()], fmt=123)

    def test_generate_empty_text_raises(self):
        e = make_engine()
        with pytest.raises(CitationValidationError):
            e.generate("   ", sources=[make_source()])

    def test_generate_unsupported_source_raises(self):
        e = make_engine()
        with pytest.raises(CitationResolutionError):
            e.generate("x", sources=[42])

    def test_generate_no_resolution(self):
        e = make_engine()
        r = e.generate("x", sources=[], fmt="numeric")
        assert r.sources == []
        assert r.errors  # no sources validation error

    def test_generate_resolve_false(self):
        e = make_engine()
        src = make_source()
        r = e.generate("x", sources=[src], request=CitationRequest(text="x", sources=[src], resolve=False))
        assert r.sources == [src]

    def test_generate_validate_false(self):
        e = make_engine(config=CitationConfig(validate_on_generate=True))
        src = make_source()
        r = e.generate("x", sources=[src], request=CitationRequest(text="x", sources=[src], validate=False))
        assert r.errors == []

    def test_generate_validation_off_in_config(self):
        e = make_engine(config=CitationConfig(validate_on_generate=False))
        r = e.generate("x", sources=[], request=CitationRequest(text="x", sources=[], validate=True))
        assert r.errors == []

    def test_generate_resolution_off_in_config(self):
        e = make_engine(config=CitationConfig(resolve_on_generate=False))
        src = make_source()
        r = e.generate("x", sources=[src], request=CitationRequest(text="x", sources=[src]))
        assert r.sources == [src]

    def test_citation_ids_sequential(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris. It is a city in Europe.",
                       sources=[make_source()])
        assert [c.citation_id for c in r.citations] == ["c1", "c2"]

    def test_source_attribution_score_updated(self):
        e = make_engine()
        src = make_source(content="The capital of France is Paris.")
        r = e.generate("The capital of France is Paris.", sources=[src])
        assert src.attribution_score == pytest.approx(1.0)

    def test_unattributed_sentence_warning(self):
        e = make_engine()
        src = make_source(content="Nothing about quantum.")
        r = e.generate("The capital of France is Paris. Quantum entanglement is weird.",
                       sources=[src])
        assert any("without supporting" in w for w in r.warnings)

    def test_low_confidence_error(self):
        e = make_engine()
        src = make_source(content="The capital of France is Paris.", retrieval_score=0.0, rerank_score=0.0)
        r = e.generate("The capital of France is Paris.", sources=[src])
        assert any("below threshold" in err for err in r.errors)

    def test_multi_source_citation(self):
        e = make_engine(config=CitationConfig(max_sources_per_citation=3))
        s1 = make_source(content="The capital of France is Paris. It is a city.")
        s2 = make_source(source_id="s2", content="The capital of France is Paris. Europe!")
        r = e.generate("The capital of France is Paris.", sources=[s1, s2])
        assert r.citations[0].source_ids == ["s1", "s2"]

    def test_generate_async(self):
        e = make_engine()
        r = asyncio.run(e.generate_async("The capital of France is Paris.", sources=[make_source()]))
        assert r.citations[0].source_ids == ["s1"]
        assert r.confidence > 0

    def test_generate_async_empty_text(self):
        e = make_engine()
        with pytest.raises(CitationValidationError):
            asyncio.run(e.generate_async("", sources=[make_source()]))

    def test_generate_async_embedding_strategy(self):
        vectors = {
            "The capital of France is Paris.": [1.0, 0.0, 0.0],
            "content text": [0.0, 1.0, 0.0],
            "The capital of France is Paris. Gold.": [1.0, 0.0, 0.0],
        }
        e = make_engine(embedder=lambda t: vectors.get(t, [0.0, 0.0, 0.0]))
        src = make_source(content="The capital of France is Paris. Gold.")
        r = asyncio.run(e.generate_async("The capital of France is Paris.", sources=[src]))
        assert r.citations[0].source_ids == ["s1"]

    def test_batch_generate(self):
        e = make_engine()
        reqs = [
            CitationRequest(text="The capital of France is Paris.", sources=[make_source()]),
            CitationRequest(text="The capital of Italy is Rome.", sources=[make_source()], format="apa"),
        ]
        results = asyncio.run(e.batch_generate(reqs))
        assert len(results) == 2
        assert results[0].citations
        assert results[1].format == CitationFormat.APA

    def test_batch_generate_error(self):
        e = make_engine()
        with pytest.raises(CitationGenerationError):
            asyncio.run(e.batch_generate([CitationRequest(text="", sources=[])]))

    def test_validate(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        v = e.validate(r)
        assert v.valid is True

    def test_validate_async(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        v = asyncio.run(e.validate_async(r))
        assert v.valid is True

    def test_resolve(self):
        e = make_engine()
        out = e.resolve([make_source()])
        assert len(out) == 1

    def test_resolve_async(self):
        e = make_engine()
        out = asyncio.run(e.resolve_async([make_source()]))
        assert len(out) == 1

    def test_format_style(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        out = e.format(r, "apa")
        assert "(Smith, 2021" in out

    def test_format_default_style(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        out = e.format(r)
        assert "[1] John Smith" in out

    def test_format_json(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        payload = json.loads(e.format(r, "json"))
        assert payload["citations"]

    def test_format_unknown_style(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        with pytest.raises(UnknownCitationFormatError):
            e.format(r, "bogus")

    def test_register_format(self):
        e = make_engine()

        class Loud:
            name = "loud"
            def render_inline(self, r):
                return r.text.upper()
            def render_references(self, r):
                return "REFS"
            def render(self, r):
                return self.render_inline(r) + "\n" + self.render_references(r)

        e.register_format("loud", Loud())
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        assert e.format(r, "loud").startswith("THE CAPITAL")

    def test_get_metrics(self):
        e = make_engine()
        e.generate("The capital of France is Paris.", sources=[make_source()])
        asyncio.run(e.generate_async("The capital of France is Paris.", sources=[make_source()]))
        m = e.get_metrics()
        assert m.total_generations == 2
        assert m.total_async_generations == 1

    def test_embedder_injects_embedding_strategy(self):
        e = make_engine(embedder=lambda t: [1.0])
        assert e._attribution.name == "embedding"

    def test_generate_rag_chunks_integration(self):
        e = make_engine()
        chunk = RetrievedChunk(
            chunk_id="ch-1",
            content="Gold prices rallied in Q3 2026.",
            score=0.9,
            rerank_score=0.8,
            metadata={"filename": "gold.pdf", "title": "Gold Report",
                      "author": "K. Lee", "published_at": "2026-01-01", "url": "https://g"},
        )
        r = e.generate("Gold prices rallied in Q3 2026.", sources=[chunk], fmt="apa")
        assert r.citations[0].source_ids == ["ch-1"]
        assert "Lee" in r.rendered
        assert "Gold Report" in r.references

    def test_generate_memory_items_integration(self):
        e = make_engine()
        item = MemoryItem(id="mem-1", content="User prefers low-risk trades.",
                          metadata={"title": "Profile"})
        r = e.generate("The user prefers low-risk trades.", sources=[item])
        assert r.citations[0].source_ids == ["mem-1"]

    def test_generate_error_logging(self):
        e = make_engine()
        with pytest.raises(CitationValidationError):
            e.generate("", sources=[make_source()])
        m = e.get_metrics()
        assert m.total_errors >= 1


# ============================================================
# Logger & Metrics
# ============================================================
class TestLogger:
    def test_log_event_disabled(self):
        with patch("app.citations.logging.logging.getLogger") as mock_get:
            mock_logger = MagicMock()
            mock_logger.isEnabledFor.return_value = False
            mock_get.return_value = mock_logger
            CitationLogger().log_event("generate", make_result())
            mock_logger.info.assert_not_called()

    def test_log_event_enabled(self):
        with patch("app.citations.logging.logging.getLogger") as mock_get:
            mock_logger = MagicMock()
            mock_logger.isEnabledFor.return_value = True
            mock_get.return_value = mock_logger
            CitationLogger().log_event("generate", make_result())
            mock_logger.info.assert_called_once()

    def test_log_event_no_result(self):
        with patch("app.citations.logging.logging.getLogger") as mock_get:
            mock_logger = MagicMock()
            mock_logger.isEnabledFor.return_value = True
            mock_get.return_value = mock_logger
            CitationLogger().log_event("resolve", extra="1")
            payload = mock_logger.info.call_args[0][0]
            assert "citation_resolve" in payload

    def test_log_error(self):
        with patch("app.citations.logging.logging.getLogger") as mock_get:
            mock_logger = MagicMock()
            mock_logger.isEnabledFor.return_value = True
            mock_get.return_value = mock_logger
            CitationLogger().log_error(ValueError("bad"), context="test")
            mock_logger.error.assert_called_once()
            payload = mock_logger.error.call_args[0][0]
            assert "ValueError" in payload
            assert "bad" in payload


class TestMetricsTracker:
    def test_all_records(self):
        t = CitationMetricsTracker()
        t.record_generation(2, 3, 1.5)
        t.record_async_generation(1, 1, 0.5)
        t.record_batch(4, 8)
        t.record_validation()
        t.record_resolution(3)
        t.record_format()
        t.record_error()
        m = t.get_metrics()
        assert m.total_generations == 2
        assert m.total_async_generations == 1
        assert m.total_batch_items == 4
        assert m.total_citations == 11
        assert m.total_sources == 7
        assert m.total_validations == 1
        assert m.total_resolutions == 1
        assert m.total_formats == 1
        assert m.total_errors == 1
        assert m.total_latency_ms == pytest.approx(2.0)

    def test_async_metrics(self):
        e = make_engine()
        asyncio.run(e.generate_async("The capital of France is Paris.", sources=[make_source()]))
        assert e.get_metrics().total_async_generations == 1


# ============================================================
# Factory
# ============================================================
class TestFactory:
    def test_create_default(self):
        from app.citations import create_citation_engine
        e = create_citation_engine()
        assert isinstance(e, CitationEngine)

    def test_create_with_config(self):
        from app.citations import create_citation_engine
        e = create_citation_engine(config=CitationConfig(default_format="mla"))
        assert e._config.default_format == "mla"

    def test_create_with_kwargs(self):
        from app.citations import create_citation_engine
        e = create_citation_engine(config=CitationConfig(), logger=CitationLogger())
        assert isinstance(e._logger, CitationLogger)

    def test_public_exports(self):
        from app.citations import (  # noqa: F401
            Citation,
            CitationConfig,
            CitationEngine,
            CitationFormat,
            CitationMapping,
            CitationMetrics,
            CitationRequest,
            CitationResult,
            CitationSource,
            ValidationResult,
            create_citation_engine,
        )
        assert True


# ============================================================
# Coverage edge cases
# ============================================================
class TestCoverageEdges:
    def test_splitter_leading_punctuation_kept(self):
        parts = SentenceSplitter().split(". Hello.")
        assert [p[0] for p in parts] == [".", "Hello."]

    def test_numeric_citation_index_fallback(self):
        f = NumericCitationFormatter()
        r = make_result()
        assert f._citation_index(r, Citation(citation_id="zzz", sentence="x")) == 1

    def test_numeric_reference_filename(self):
        f = NumericCitationFormatter()
        r = make_result(text="A. B.", sources=[make_source(filename="notes.pdf")])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert "notes.pdf" in f.render_references(r)

    def test_apa_inline_no_matching_source(self):
        f = APACitationFormatter()
        r = CitationResult(
            text="A. B.",
            citations=[Citation(citation_id="c1", sentence="A.", source_ids=["ghost"], confidence=0.9)],
            sources=[make_source()],
        )
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["ghost"])]
        assert f.render_inline(r) == "A.(n.d.) B."

    def test_apa_references_dedupe(self):
        f = APACitationFormatter()
        r = make_result(text="Alpha. Beta.", citations=2)
        r.mappings = [CitationMapping(sentence="Alpha.", start=0, end=6, source_ids=["s1"]),
                      CitationMapping(sentence="Beta.", start=7, end=13, source_ids=["s1"])]
        refs = f.render_references(r)
        assert refs.count("Geography Notes") == 1

    def test_mla_references_dedupe(self):
        f = MLACitationFormatter()
        r = make_result(text="Alpha. Beta.", citations=2)
        r.mappings = [CitationMapping(sentence="Alpha.", start=0, end=6, source_ids=["s1"]),
                      CitationMapping(sentence="Beta.", start=7, end=13, source_ids=["s1"])]
        refs = f.render_references(r)
        assert refs.count("Geography Notes") == 1

    def test_markdown_reference_filename(self):
        f = MarkdownCitationFormatter()
        r = make_result(text="A. B.", sources=[make_source(filename="notes.pdf")])
        r.mappings = [CitationMapping(sentence="A.", start=0, end=2, source_ids=["s1"])]
        assert "notes.pdf" in f.render_references(r)

    def test_resolver_empty_chunk_id_fallback(self):
        chunk = RetrievedChunk(chunk_id="", content="x", score=0.5)
        s = SourceResolver().resolve([chunk])[0]
        assert s.source_id == ""

    def test_generate_wraps_mapper_error(self):
        e = make_engine()
        e._mapper = MagicMock()
        e._mapper.map.side_effect = RuntimeError("boom")
        with pytest.raises(CitationGenerationError):
            e.generate("The capital of France is Paris.", sources=[make_source()])

    def test_generate_async_wraps_mapper_error(self):
        e = make_engine()
        e._mapper = MagicMock()
        e._mapper.map_async = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(CitationGenerationError):
            asyncio.run(e.generate_async("The capital of France is Paris.", sources=[make_source()]))

    def test_generate_async_resolve_false(self):
        e = make_engine()
        src = make_source()
        r = asyncio.run(e.generate_async(
            "The capital of France is Paris.", sources=[src],
            request=CitationRequest(text="x", sources=[src], resolve=False),
        ))
        assert r.sources == [src]

    def test_format_with_enum_style(self):
        e = make_engine()
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        out = e.format(r, CitationFormat.APA)
        assert "(Smith, 2021" in out

    def test_format_wraps_render_error(self):
        e = make_engine()

        class Broken:
            name = "broken"
            def render_inline(self, r):
                return "x"
            def render_references(self, r):
                return "y"
            def render(self, r):
                raise RuntimeError("boom")

        e.register_format("broken", Broken())
        r = e.generate("The capital of France is Paris.", sources=[make_source()])
        with pytest.raises(CitationGenerationError):
            e.format(r, "broken")
