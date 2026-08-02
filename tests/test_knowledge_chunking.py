import math

import pytest

from app.knowledge.chunking.config import ChunkingConfig
from app.knowledge.chunking.metadata import ChunkMetadataBuilder
from app.knowledge.chunking.statistics import ChunkStatistics
from app.knowledge.chunking.strategies import (
    FixedSizeChunkStrategy,
    RecursiveChunkStrategy,
    ParagraphChunkStrategy,
    SentenceChunkStrategy,
    SlidingWindowChunkStrategy,
    create_strategy,
)
from app.knowledge.chunking.tokenizer import HeuristicTokenEstimator
from app.knowledge.chunking.validator import ChunkValidator, ChunkValidationError
from app.knowledge.chunking.pipeline import ChunkingPipeline
from app.knowledge.models import KnowledgeDocument, KnowledgeMetadata
from app.knowledge.service import KnowledgeService
from app.knowledge.repository import InMemoryKnowledgeRepository


# ---------------------------------------------------------------------------
# Token Estimator
# ---------------------------------------------------------------------------

class TestTokenEstimator:
    def test_empty(self):
        est = HeuristicTokenEstimator()
        assert est.estimate("") == 0

    def test_ascii(self):
        est = HeuristicTokenEstimator()
        t = est.estimate("hello world")
        assert t == math.ceil(11 / 4)

    def test_mixed(self):
        est = HeuristicTokenEstimator()
        t = est.estimate("hello 世界")
        assert t == math.ceil(7 / 4) + math.ceil(2 / 2)

    def test_non_ascii(self):
        est = HeuristicTokenEstimator()
        t = est.estimate("世界你好")
        assert t == math.ceil(4 / 2)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestChunkingConfig:
    def test_default(self):
        c = ChunkingConfig()
        assert c.strategy == "fixed"
        assert c.chunk_size == 1000
        assert c.chunk_overlap == 200

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("CHUNK_STRATEGY", "recursive")
        monkeypatch.setenv("CHUNK_SIZE", "500")
        c = ChunkingConfig.from_env()
        assert c.strategy == "recursive"
        assert c.chunk_size == 500


# ---------------------------------------------------------------------------
# Fixed Size Strategy
# ---------------------------------------------------------------------------

class TestFixedSizeStrategy:
    @pytest.mark.asyncio
    async def test_small_text(self):
        strategy = FixedSizeChunkStrategy(max_characters=1000)
        doc = KnowledgeDocument(content="Hello World")
        chunks = await strategy.split(doc)
        assert len(chunks) == 1
        assert chunks[0].content == "Hello World"
        assert chunks[0].chunk_index == 0

    @pytest.mark.asyncio
    async def test_splits_into_multiple(self):
        strategy = FixedSizeChunkStrategy(max_characters=10, overlap=0)
        doc = KnowledgeDocument(content="Hello World ABCDEFGHIJ")
        chunks = await strategy.split(doc)
        assert len(chunks) >= 2

    @pytest.mark.asyncio
    async def test_overlap(self):
        strategy = FixedSizeChunkStrategy(max_characters=20, overlap=5)
        doc = KnowledgeDocument(content="A" * 100)
        chunks = await strategy.split(doc)
        assert len(chunks) >= 5
        if len(chunks) > 1:
            overlap_chars = set(chunks[0].content) & set(chunks[1].content)
            assert len(overlap_chars) > 0

    @pytest.mark.asyncio
    async def test_offsets(self):
        strategy = FixedSizeChunkStrategy(max_characters=10, overlap=0)
        doc = KnowledgeDocument(content="0123456789ABCDEF")
        chunks = await strategy.split(doc)
        assert len(chunks) == 2
        assert chunks[0].start_offset == 0
        assert chunks[0].end_offset == 10
        assert chunks[0].content == "0123456789"
        assert chunks[1].start_offset == 10

    @pytest.mark.asyncio
    async def test_token_estimate(self):
        strategy = FixedSizeChunkStrategy(max_characters=1000)
        doc = KnowledgeDocument(content="hello world")
        chunks = await strategy.split(doc)
        assert chunks[0].token_estimate > 0

    @pytest.mark.asyncio
    async def test_empty_document(self):
        strategy = FixedSizeChunkStrategy(max_characters=1000)
        doc = KnowledgeDocument(content="")
        chunks = await strategy.split(doc)
        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_character_count(self):
        strategy = FixedSizeChunkStrategy(max_characters=1000)
        doc = KnowledgeDocument(content="Hello")
        chunks = await strategy.split(doc)
        assert chunks[0].character_count == 5


# ---------------------------------------------------------------------------
# Recursive Strategy
# ---------------------------------------------------------------------------

class TestRecursiveStrategy:
    @pytest.mark.asyncio
    async def test_small_text(self):
        strategy = RecursiveChunkStrategy(max_characters=1000)
        doc = KnowledgeDocument(content="Hello World")
        chunks = await strategy.split(doc)
        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_splits_by_heading(self):
        strategy = RecursiveChunkStrategy(max_characters=30, overlap=0)
        text = "# Intro\n\nHello\n\n# Section 1\n\n" + "A" * 40 + "\n\n# Section 2\n\n" + "B" * 40
        doc = KnowledgeDocument(content=text)
        chunks = await strategy.split(doc)
        assert len(chunks) >= 2

    @pytest.mark.asyncio
    async def test_heading_section_metadata(self):
        strategy = RecursiveChunkStrategy(max_characters=30, overlap=0)
        doc = KnowledgeDocument(
            content="# Chapter 1\n\nText\n\n## Sub 1\n\n" + "A" * 50
        )
        chunks = await strategy.split(doc)
        sections = [c.section for c in chunks if c.section]
        assert len(sections) > 0

    @pytest.mark.asyncio
    async def test_heading_awareness(self):
        strategy = RecursiveChunkStrategy(max_characters=30, overlap=0)
        doc = KnowledgeDocument(
            content="# Introduction\n\n## Installation\n\n## Usage\n\n" +
                    "A" * 50 + "\n\n## Configuration\n\nDetails"
        )
        chunks = await strategy.split(doc)
        for c in chunks:
            if "Introduction" in c.content:
                assert any("Introduction" in (s or []) for s in [c.section])
            elif "Installation" in c.content:
                assert any("Installation" in (s or []) for s in [c.section])

    @pytest.mark.asyncio
    async def test_recursive_word_fallback(self):
        strategy = RecursiveChunkStrategy(max_characters=20, overlap=0)
        text = "word " * 50
        doc = KnowledgeDocument(content=text)
        chunks = await strategy.split(doc)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.content) <= 25


# ---------------------------------------------------------------------------
# Paragraph Strategy
# ---------------------------------------------------------------------------

class TestParagraphStrategy:
    @pytest.mark.asyncio
    async def test_one_paragraph(self):
        strategy = ParagraphChunkStrategy(max_characters=1000)
        doc = KnowledgeDocument(content="This is a single paragraph.")
        chunks = await strategy.split(doc)
        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_multiple_paragraphs(self):
        strategy = ParagraphChunkStrategy(max_characters=1000)
        doc = KnowledgeDocument(content="Para one.\n\nPara two.\n\nPara three.")
        chunks = await strategy.split(doc)
        assert len(chunks) == 3

    @pytest.mark.asyncio
    async def test_large_paragraph(self):
        strategy = ParagraphChunkStrategy(max_characters=50, overlap=0)
        doc = KnowledgeDocument(content="A" * 30 + "\n\n" + "B" * 120 + "\n\n" + "C" * 30)
        chunks = await strategy.split(doc)
        assert len(chunks) > 3

    @pytest.mark.asyncio
    async def test_empty_paragraphs_skipped(self):
        strategy = ParagraphChunkStrategy(max_characters=1000)
        doc = KnowledgeDocument(content="One\n\n\n\nTwo\n\n\n\n\nThree")
        chunks = await strategy.split(doc)
        assert len(chunks) == 3


# ---------------------------------------------------------------------------
# Sentence Strategy
# ---------------------------------------------------------------------------

class TestSentenceStrategy:
    @pytest.mark.asyncio
    async def test_few_sentences(self):
        strategy = SentenceChunkStrategy(sentences_per_chunk=5)
        doc = KnowledgeDocument(content="One. Two. Three.")
        chunks = await strategy.split(doc)
        assert len(chunks) == 1

    @pytest.mark.asyncio
    async def test_many_sentences(self):
        strategy = SentenceChunkStrategy(sentences_per_chunk=2, overlap_sentences=0)
        doc = KnowledgeDocument(content="A. B. C. D. E. F.")
        chunks = await strategy.split(doc)
        assert len(chunks) == 3

    @pytest.mark.asyncio
    async def test_sentence_overlap(self):
        strategy = SentenceChunkStrategy(sentences_per_chunk=3, overlap_sentences=2)
        doc = KnowledgeDocument(content="A. B. C. D. E. F.")
        chunks = await strategy.split(doc)
        assert len(chunks) >= 2
        if len(chunks) >= 2:
            assert "B." in chunks[1].content

    @pytest.mark.asyncio
    async def test_single_sentence(self):
        strategy = SentenceChunkStrategy(sentences_per_chunk=5)
        doc = KnowledgeDocument(content="Just one sentence here.")
        chunks = await strategy.split(doc)
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# Sliding Window Strategy
# ---------------------------------------------------------------------------

class TestSlidingWindowStrategy:
    @pytest.mark.asyncio
    async def test_basic(self):
        strategy = SlidingWindowChunkStrategy(window_size=10, stride=5)
        doc = KnowledgeDocument(content="A" * 30)
        chunks = await strategy.split(doc)
        assert len(chunks) > 1

    @pytest.mark.asyncio
    async def test_window_size(self):
        strategy = SlidingWindowChunkStrategy(window_size=10, stride=10)
        doc = KnowledgeDocument(content="0123456789ABCDEF")
        chunks = await strategy.split(doc)
        assert all(len(c.content) <= 10 for c in chunks)

    @pytest.mark.asyncio
    async def test_stride(self):
        strategy = SlidingWindowChunkStrategy(window_size=10, stride=5)
        doc = KnowledgeDocument(content="0123456789ABCDEFGHIJ")
        chunks = await strategy.split(doc)
        assert len(chunks) == 4
        assert chunks[0].content == "0123456789"
        assert chunks[1].content == "56789ABCDE"

    @pytest.mark.asyncio
    async def test_stride_greater_than_window(self):
        strategy = SlidingWindowChunkStrategy(window_size=5, stride=10)
        doc = KnowledgeDocument(content="0123456789ABCDEF")
        chunks = await strategy.split(doc)
        assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_empty(self):
        strategy = SlidingWindowChunkStrategy()
        doc = KnowledgeDocument(content="")
        chunks = await strategy.split(doc)
        assert len(chunks) == 0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestCreateStrategy:
    def test_fixed(self):
        s = create_strategy("fixed")
        assert isinstance(s, FixedSizeChunkStrategy)

    def test_recursive(self):
        s = create_strategy("recursive")
        assert isinstance(s, RecursiveChunkStrategy)

    def test_paragraph(self):
        s = create_strategy("paragraph")
        assert isinstance(s, ParagraphChunkStrategy)

    def test_sentence(self):
        s = create_strategy("sentence")
        assert isinstance(s, SentenceChunkStrategy)

    def test_sliding_window(self):
        s = create_strategy("sliding_window")
        assert isinstance(s, SlidingWindowChunkStrategy)

    def test_unknown(self):
        with pytest.raises(ValueError):
            create_strategy("unknown")


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class TestChunkValidator:
    @pytest.fixture
    def valid_chunk(self, sample_chunk):
        return sample_chunk

    def test_valid(self, sample_chunk):
        validator = ChunkValidator(min_chunk_size=5, max_chunk_size=2000)
        result = validator.validate(sample_chunk)
        assert result is sample_chunk

    def test_empty_content(self):
        validator = ChunkValidator()
        from app.knowledge.chunking.models import ChunkPreview
        chunk = ChunkPreview(
            content="", chunk_index=0, start_offset=0, end_offset=0,
            token_estimate=0, character_count=0,
        )
        with pytest.raises(ChunkValidationError):
            validator.validate(chunk)

    def test_too_small(self, sample_chunk):
        validator = ChunkValidator(min_chunk_size=1000, max_chunk_size=2000)
        with pytest.raises(ChunkValidationError):
            validator.validate(sample_chunk)

    def test_too_large(self, sample_chunk):
        validator = ChunkValidator(min_chunk_size=1, max_chunk_size=5)
        with pytest.raises(ChunkValidationError):
            validator.validate(sample_chunk)

    def test_invalid_offsets(self):
        from app.knowledge.chunking.models import ChunkPreview
        chunk = ChunkPreview(
            content="hello", chunk_index=0, start_offset=10, end_offset=5,
            token_estimate=3, character_count=5,
        )
        validator = ChunkValidator()
        with pytest.raises(ChunkValidationError):
            validator.validate(chunk)

    def test_invalid_token_estimate(self):
        from app.knowledge.chunking.models import ChunkPreview
        chunk = ChunkPreview(
            content="hello", chunk_index=0, start_offset=0, end_offset=5,
            token_estimate=0, character_count=5,
        )
        validator = ChunkValidator()
        with pytest.raises(ChunkValidationError):
            validator.validate(chunk)


@pytest.fixture
def sample_chunk():
    from app.knowledge.chunking.models import ChunkPreview
    return ChunkPreview(
        content="Hello World",
        chunk_index=0,
        start_offset=0,
        end_offset=11,
        token_estimate=3,
        character_count=11,
    )


# ---------------------------------------------------------------------------
# Metadata Builder
# ---------------------------------------------------------------------------

class TestChunkMetadataBuilder:
    @pytest.mark.asyncio
    async def test_basic_metadata(self):
        builder = ChunkMetadataBuilder()
        doc = KnowledgeDocument(
            id="doc1", collection_id="c1", title="Test Doc",
            source="test.txt", tags=["ai"], version=2,
        )
        meta = await builder.build(doc, chunk_index=0, content="hello")
        assert meta["document_title"] == "Test Doc"
        assert meta["document_id"] == "doc1"
        assert meta["chunk_index"] == 0
        assert meta["source"] == "test.txt"
        assert meta["tags"] == ["ai"]
        assert meta["version"] == 2

    @pytest.mark.asyncio
    async def test_section_metadata(self):
        builder = ChunkMetadataBuilder()
        doc = KnowledgeDocument(id="d1", collection_id="c1", title="T")
        meta = await builder.build(doc, chunk_index=0, content="h", section=["Intro", "Sub"])
        assert meta["section"] == ["Intro", "Sub"]

    @pytest.mark.asyncio
    async def test_page_number(self):
        builder = ChunkMetadataBuilder()
        doc = KnowledgeDocument(id="d1", collection_id="c1", title="T")
        meta = await builder.build(doc, chunk_index=0, content="h", page_number=3)
        assert meta["page_number"] == 3

    @pytest.mark.asyncio
    async def test_document_metadata_propagation(self):
        builder = ChunkMetadataBuilder()
        doc = KnowledgeDocument(
            id="d1", collection_id="c1", title="T",
            metadata=[KnowledgeMetadata(key="language", value="fr")],
        )
        meta = await builder.build(doc, chunk_index=0, content="h")
        assert meta["language"] == "fr"

    @pytest.mark.asyncio
    async def test_extra_metadata(self):
        builder = ChunkMetadataBuilder()
        doc = KnowledgeDocument(id="d1", collection_id="c1", title="T")
        meta = await builder.build(doc, chunk_index=0, content="h", custom_key="custom_val")
        assert meta["custom_key"] == "custom_val"


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestChunkStatistics:
    def test_empty(self):
        stats = ChunkStatistics.compute([])
        assert stats["total_chunks"] == 0
        assert stats["average_size"] == 0

    def test_basic_stats(self, sample_chunk):
        from app.knowledge.chunking.models import ChunkPreview
        c2 = ChunkPreview(
            content="Hello World!!", chunk_index=1, start_offset=0, end_offset=13,
            token_estimate=4, character_count=13,
        )
        stats = ChunkStatistics.compute([sample_chunk, c2])
        assert stats["total_chunks"] == 2
        assert stats["total_characters"] == 24
        assert stats["max_size"] == 13
        assert stats["min_size"] == 11
        assert stats["average_size"] == 12.0

    def test_overlap_percentage(self):
        from app.knowledge.chunking.models import ChunkPreview
        chunks = [
            ChunkPreview(content="AAAAA", chunk_index=0, start_offset=0, end_offset=5,
                         token_estimate=2, character_count=5),
            ChunkPreview(content="AAAAA", chunk_index=1, start_offset=3, end_offset=8,
                         token_estimate=2, character_count=5),
        ]
        pct = ChunkStatistics.overlap_percentage(chunks, 8)
        assert pct == 25.0

    def test_overlap_percentage_empty(self):
        assert ChunkStatistics.overlap_percentage([], 100) == 0.0


# ---------------------------------------------------------------------------
# Pipeline Integration
# ---------------------------------------------------------------------------

class TestChunkingPipeline:
    @pytest.fixture
    async def svc_and_doc(self):
        repo = InMemoryKnowledgeRepository()
        svc = KnowledgeService(repo)
        coll = await svc.create_collection(name="test-coll")
        doc = await svc.create_document(
            collection_id=coll.id,
            title="Test Document",
            content="Hello World. This is a test. " * 20,
        )
        return svc, doc

    @pytest.mark.asyncio
    async def test_chunk_document(self, svc_and_doc):
        svc, doc = svc_and_doc
        pipeline = ChunkingPipeline(svc)
        result = await pipeline.chunk(doc)
        assert result.total_chunks > 0
        assert result.document_id == doc.id
        assert result.statistics["total_chunks"] > 0
        assert len(result.chunks) == result.total_chunks

    @pytest.mark.asyncio
    async def test_chunk_document_by_id(self, svc_and_doc):
        svc, doc = svc_and_doc
        pipeline = ChunkingPipeline(svc)
        result = await pipeline.chunk_document(doc.id)
        assert result.total_chunks > 0
        assert result.document_id == doc.id

    @pytest.mark.asyncio
    async def test_chunk_nonexistent(self, svc_and_doc):
        svc, _ = svc_and_doc
        pipeline = ChunkingPipeline(svc)
        with pytest.raises(ValueError):
            await pipeline.chunk_document("nonexistent")

    @pytest.mark.asyncio
    async def test_preview_no_save(self, svc_and_doc):
        svc, doc = svc_and_doc
        pipeline = ChunkingPipeline(svc)
        result = await pipeline.preview(doc)
        assert result.total_chunks > 0
        assert len(result.chunks) == 0
        assert len(result.previews) > 0

    @pytest.mark.asyncio
    async def test_save_chunks(self, svc_and_doc):
        svc, doc = svc_and_doc
        pipeline = ChunkingPipeline(svc)
        result = await pipeline.chunk(doc)
        saved = await pipeline.save_chunks(doc.id, result.chunks)
        assert len(saved) == result.total_chunks
        for s in saved:
            assert s.id
            assert s.document_id == doc.id

    @pytest.mark.asyncio
    async def test_different_strategies(self, svc_and_doc):
        svc, doc = svc_and_doc
        from app.knowledge.chunking.config import ChunkingConfig
        config = ChunkingConfig(min_chunk_size=10, max_chunk_size=5000)
        pipeline = ChunkingPipeline(svc, config=config)
        results = []
        for name in ("fixed", "recursive", "paragraph", "sentence", "sliding_window"):
            strat = create_strategy(name)
            r = await pipeline.chunk(doc, strategy=strat)
            results.append(r)
        assert all(r.total_chunks > 0 for r in results)

    @pytest.mark.asyncio
    async def test_statistics_in_result(self, svc_and_doc):
        svc, doc = svc_and_doc
        pipeline = ChunkingPipeline(svc)
        result = await pipeline.chunk(doc)
        s = result.statistics
        assert s["total_chunks"] > 0
        assert s["average_size"] > 0
        assert s["average_token"] > 0
        assert s["max_size"] > 0
        assert s["min_size"] > 0
        assert "overlap_percentage" in s

    @pytest.mark.asyncio
    async def test_chunk_metadata(self, svc_and_doc):
        svc, doc = svc_and_doc
        pipeline = ChunkingPipeline(svc)
        result = await pipeline.chunk(doc)
        for chunk in result.chunks:
            assert chunk.document_id == doc.id
            assert chunk.collection_id == doc.collection_id
            assert chunk.chunk_index >= 0
            meta_keys = [m.key for m in chunk.metadata]
            assert "document_title" in meta_keys
            assert "document_id" in meta_keys
            assert "version" in meta_keys

    @pytest.mark.asyncio
    async def test_fixed_size_chunking_with_small_max(self, svc_and_doc):
        svc, doc = svc_and_doc
        from app.knowledge.chunking.config import ChunkingConfig
        config = ChunkingConfig(min_chunk_size=10, max_chunk_size=2000)
        strat = FixedSizeChunkStrategy(max_characters=50, overlap=10)
        pipeline = ChunkingPipeline(svc, config=config, strategy=strat)
        result = await pipeline.chunk(doc)
        assert result.total_chunks > 1
        for c in result.chunks:
            assert c.character_count <= 60

    @pytest.mark.asyncio
    async def test_heading_aware_markdown(self):
        repo = InMemoryKnowledgeRepository()
        svc = KnowledgeService(repo)
        coll = await svc.create_collection(name="coll")
        doc = await svc.create_document(
            collection_id=coll.id, title="Guide",
            content="# Start\n\nBegin here.\n\n## Step 1\n\n" + "A" * 60 + "\n\n### Detail\n\n" + "B" * 60 + "\n\n## Step 2\n\nDone.",
        )
        from app.knowledge.chunking.config import ChunkingConfig
        config = ChunkingConfig(min_chunk_size=10, max_chunk_size=5000)
        strat = RecursiveChunkStrategy(max_characters=30, overlap=0)
        pipeline = ChunkingPipeline(svc, config=config, strategy=strat)
        result = await pipeline.chunk(doc)
        assert result.total_chunks > 0
        found_heading = False
        for c in result.chunks:
            meta_keys = [m.key for m in c.metadata]
            if "section" in meta_keys:
                found_heading = True
                break
        assert found_heading

    @pytest.mark.asyncio
    async def test_chunk_with_tags(self):
        repo = InMemoryKnowledgeRepository()
        svc = KnowledgeService(repo)
        coll = await svc.create_collection(name="coll")
        doc = await svc.create_document(
            collection_id=coll.id, title="Tagged", content="Hello world.",
            tags=["guide", "python"],
        )
        pipeline = ChunkingPipeline(svc)
        result = await pipeline.chunk(doc)
        for c in result.chunks:
            meta_keys = [m.key for m in c.metadata]
            assert "tags" in meta_keys

    @pytest.mark.asyncio
    async def test_statistics_overlap(self, svc_and_doc):
        svc, doc = svc_and_doc
        strat = FixedSizeChunkStrategy(max_characters=100, overlap=20)
        pipeline = ChunkingPipeline(svc, strategy=strat)
        result = await pipeline.chunk(doc)
        assert result.statistics["overlap_percentage"] >= 0

    @pytest.mark.asyncio
    async def test_empty_document(self):
        repo = InMemoryKnowledgeRepository()
        svc = KnowledgeService(repo)
        coll = await svc.create_collection(name="c")
        doc = await svc.create_document(collection_id=coll.id, title="Empty", content="")
        pipeline = ChunkingPipeline(svc)
        result = await pipeline.chunk(doc)
        assert result.total_chunks == 0
        assert result.statistics["total_chunks"] == 0

    @pytest.mark.asyncio
    async def test_preview_with_custom_strategy(self, svc_and_doc):
        svc, doc = svc_and_doc
        pipeline = ChunkingPipeline(svc)
        strat = SentenceChunkStrategy(sentences_per_chunk=3, overlap_sentences=1)
        result = await pipeline.preview(doc, strategy=strat)
        assert result.total_chunks > 0
        assert result.previews is not None
        for p in result.previews:
            assert p.content
