import hashlib
import json
import os
import tempfile
import uuid

import pytest

from app.knowledge.ingestion.cleaner import TextCleaner
from app.knowledge.ingestion.config import IngestionConfig
from app.knowledge.ingestion.deduplication import DuplicateDetector
from app.knowledge.ingestion.language import HeuristicLanguageDetector
from app.knowledge.ingestion.loaders import (
    TextLoader,
    MarkdownLoader,
    PDFLoader,
    HTMLLoader,
    JSONLoader,
    create_loader,
)
from app.knowledge.ingestion.metadata import MetadataExtractor
from app.knowledge.ingestion.models import LoadedDocument
from app.knowledge.ingestion.parsers import (
    PlainTextParser,
    MarkdownParser,
    PDFParser,
    HTMLParser,
    JSONParser,
    create_parser,
)
from app.knowledge.ingestion.pipeline import IngestionPipeline
from app.knowledge.ingestion.validation import (
    DocumentValidator,
    FileTooLargeError,
    UnsupportedFormatError,
    CorruptedFileError,
)
from app.knowledge.service import KnowledgeService
from app.knowledge.repository import InMemoryKnowledgeRepository


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestIngestionConfig:
    def test_default_config(self):
        config = IngestionConfig()
        assert config.document_max_size == 10 * 1024 * 1024
        assert ".txt" in config.supported_document_types
        assert config.allow_duplicate_document is False
        assert config.default_language == "en"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("DOCUMENT_MAX_SIZE", "512")
        monkeypatch.setenv("ALLOW_DUPLICATE_DOCUMENT", "1")
        monkeypatch.setenv("DEFAULT_LANGUAGE", "fr")
        config = IngestionConfig.from_env()
        assert config.document_max_size == 512
        assert config.allow_duplicate_document is True
        assert config.default_language == "fr"


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------

class TestLoaders:
    @pytest.mark.asyncio
    async def test_text_loader(self):
        loader = TextLoader()
        doc = await loader.load_bytes(b"hello world", "test.txt")
        assert doc.filename == "test.txt"
        assert doc.extension == ".txt"
        assert doc.mime_type == "text/plain"
        assert doc.content == b"hello world"
        assert doc.size == 11

    @pytest.mark.asyncio
    async def test_text_loader_from_file(self):
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write(b"file content")
            tmp = f.name
        try:
            loader = TextLoader()
            doc = await loader.load(tmp)
            assert doc.filename.endswith(".txt")
            assert doc.content == b"file content"
        finally:
            os.unlink(tmp)

    @pytest.mark.asyncio
    async def test_markdown_loader(self):
        loader = MarkdownLoader()
        doc = await loader.load_bytes(b"# Hello", "test.md")
        assert doc.extension == ".md"
        assert doc.mime_type == "text/markdown"

    @pytest.mark.asyncio
    async def test_markdown_loader_mdx(self):
        loader = MarkdownLoader()
        doc = await loader.load_bytes(b"# Hello", "test.mdx")
        assert doc.extension == ".mdx"

    @pytest.mark.asyncio
    async def test_pdf_loader(self):
        loader = PDFLoader()
        doc = await loader.load_bytes(b"%PDF-1.4 fake", "test.pdf")
        assert doc.extension == ".pdf"
        assert doc.mime_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_html_loader(self):
        loader = HTMLLoader()
        doc = await loader.load_bytes(b"<html></html>", "test.html")
        assert doc.extension == ".html"
        assert doc.mime_type == "text/html"

    @pytest.mark.asyncio
    async def test_html_loader_htm(self):
        loader = HTMLLoader()
        doc = await loader.load_bytes(b"<html></html>", "test.htm")
        assert doc.extension == ".htm"

    @pytest.mark.asyncio
    async def test_json_loader(self):
        loader = JSONLoader()
        doc = await loader.load_bytes(b'{"key": "val"}', "test.json")
        assert doc.extension == ".json"
        assert doc.mime_type == "application/json"

    def test_create_loader(self):
        assert isinstance(create_loader(".txt"), TextLoader)
        assert isinstance(create_loader(".md"), MarkdownLoader)
        assert isinstance(create_loader(".mdx"), MarkdownLoader)
        assert isinstance(create_loader(".pdf"), PDFLoader)
        assert isinstance(create_loader(".html"), HTMLLoader)
        assert isinstance(create_loader(".htm"), HTMLLoader)
        assert isinstance(create_loader(".json"), JSONLoader)

    def test_create_loader_unknown(self):
        with pytest.raises(ValueError):
            create_loader(".xyz")


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParsers:
    @pytest.mark.asyncio
    async def test_plain_text_parser(self):
        parser = PlainTextParser()
        doc = LoadedDocument(
            filename="test.txt", extension=".txt", mime_type="text/plain",
            content=b"hello world", size=11,
        )
        result = await parser.parse(doc)
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_markdown_parser(self):
        parser = MarkdownParser()
        doc = LoadedDocument(
            filename="test.md", extension=".md", mime_type="text/markdown",
            content=b"# Title\n\nHello", size=100,
        )
        result = await parser.parse(doc)
        assert "# Title" in result

    @pytest.mark.asyncio
    async def test_pdf_parser_simple(self):
        parser = PDFParser()
        doc = LoadedDocument(
            filename="test.pdf", extension=".pdf", mime_type="application/pdf",
            content=b"%PDF-1.4\n(Hello World) Tj\nendstream", size=100,
        )
        result = await parser.parse(doc)
        assert "Hello World" in result

    @pytest.mark.asyncio
    async def test_pdf_parser_empty(self):
        parser = PDFParser()
        doc = LoadedDocument(
            filename="test.pdf", extension=".pdf", mime_type="application/pdf",
            content=b"not a pdf at all", size=100,
        )
        result = await parser.parse(doc)
        assert "PDF content could not be fully extracted" in result

    @pytest.mark.asyncio
    async def test_html_parser_lxml(self):
        parser = HTMLParser()
        doc = LoadedDocument(
            filename="test.html", extension=".html", mime_type="text/html",
            content=b"<html><body><p>Hello</p><script>x</script></body></html>",
            size=100,
        )
        result = await parser.parse(doc)
        assert "Hello" in result
        assert "x" not in result

    @pytest.mark.asyncio
    async def test_html_parser_simple(self):
        parser = HTMLParser()
        doc = LoadedDocument(
            filename="test.html", extension=".html", mime_type="text/html",
            content=b"<p>Hello <b>World</b></p>", size=100,
        )
        result = await parser.parse(doc)
        assert "Hello" in result
        assert "World" in result

    @pytest.mark.asyncio
    async def test_json_parser_dict(self):
        parser = JSONParser()
        doc = LoadedDocument(
            filename="test.json", extension=".json", mime_type="application/json",
            content=b'{"name": "test", "value": 42}', size=100,
        )
        result = await parser.parse(doc)
        assert "name:" in result
        assert "test" in result
        assert "42" in result

    @pytest.mark.asyncio
    async def test_json_parser_list(self):
        parser = JSONParser()
        doc = LoadedDocument(
            filename="test.json", extension=".json", mime_type="application/json",
            content=b'["a", "b", "c"]', size=100,
        )
        result = await parser.parse(doc)
        assert "a" in result
        assert "b" in result

    @pytest.mark.asyncio
    async def test_json_parser_invalid(self):
        parser = JSONParser()
        doc = LoadedDocument(
            filename="test.json", extension=".json", mime_type="application/json",
            content=b"not json", size=100,
        )
        result = await parser.parse(doc)
        assert result == "not json"

    def test_create_parser(self):
        assert isinstance(create_parser(".txt"), PlainTextParser)
        assert isinstance(create_parser(".md"), MarkdownParser)
        assert isinstance(create_parser(".pdf"), PDFParser)
        assert isinstance(create_parser(".html"), HTMLParser)
        assert isinstance(create_parser(".json"), JSONParser)

    def test_create_parser_unknown(self):
        with pytest.raises(ValueError):
            create_parser(".xyz")


# ---------------------------------------------------------------------------
# Cleaner tests
# ---------------------------------------------------------------------------

class TestTextCleaner:
    @pytest.mark.asyncio
    async def test_remove_bom(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("\ufeffHello")
        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_normalize_newlines(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("a\r\nb\rc")
        assert result == "a\nb\nc"

    @pytest.mark.asyncio
    async def test_collapse_newlines(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("a\n\n\n\n\nb")
        assert result == "a\n\nb"

    @pytest.mark.asyncio
    async def test_trim_lines(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("  hello  \n  world  ")
        assert result == "hello\nworld"

    @pytest.mark.asyncio
    async def test_normalize_tabs(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("a\tb")
        assert result == "a b"

    @pytest.mark.asyncio
    async def test_remove_control_chars(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("hello\x00world\x1b")
        assert result == "helloworld"

    @pytest.mark.asyncio
    async def test_unicode_normalization(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("\u00e9\u0065\u0301")
        assert result == "\u00e9\u00e9" or result == "\u00e9"

    @pytest.mark.asyncio
    async def test_full_clean(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("  \ufeffHello\r\n  World\tTest  \n\n\nEnd  ")
        assert "Hello" in result
        assert "World Test" in result
        assert "End" in result
        assert result.startswith("Hello")

    @pytest.mark.asyncio
    async def test_preserve_newlines(self):
        cleaner = TextCleaner()
        result = await cleaner.clean("a\nb\nc")
        assert result == "a\nb\nc"


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

class TestMetadataExtractor:
    @pytest.mark.asyncio
    async def test_basic_metadata(self):
        extractor = MetadataExtractor()
        doc = LoadedDocument(
            filename="test.txt", extension=".txt", mime_type="text/plain",
            content=b"hello world", size=11,
        )
        meta = await extractor.extract(doc)
        assert meta["filename"] == "test.txt"
        assert meta["extension"] == ".txt"
        assert meta["mime_type"] == "text/plain"
        assert meta["size"] == 11
        assert len(meta["checksum"]) == 64
        assert meta["encoding"] in ("utf-8", "ascii")

    @pytest.mark.asyncio
    async def test_checksum_consistency(self):
        extractor = MetadataExtractor()
        doc = LoadedDocument(
            filename="a.txt", extension=".txt", mime_type="text/plain",
            content=b"same content", size=12,
        )
        meta1 = await extractor.extract(doc)
        doc2 = LoadedDocument(
            filename="b.txt", extension=".txt", mime_type="text/plain",
            content=b"same content", size=12,
        )
        meta2 = await extractor.extract(doc2)
        assert meta1["checksum"] == meta2["checksum"]

    @pytest.mark.asyncio
    async def test_custom_metadata(self):
        extractor = MetadataExtractor()
        doc = LoadedDocument(
            filename="t.txt", extension=".txt", mime_type="text/plain",
            content=b"data", size=4,
        )
        meta = await extractor.extract(doc, custom_metadata={"source": "test"})
        assert meta["custom"]["source"] == "test"

    @pytest.mark.asyncio
    async def test_stat_metadata(self):
        import tempfile
        extractor = MetadataExtractor()
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".txt", delete=False) as f:
            f.write(b"data")
            tmp = f.name
        try:
            stat = os.stat(tmp)
            doc = LoadedDocument(
                filename=os.path.basename(tmp), extension=".txt",
                mime_type="text/plain", content=b"data", size=4,
            )
            meta = await extractor.extract(doc, stat=stat, path=tmp)
            assert "created_at" in meta
            assert "modified_at" in meta
            assert meta["modified_at"] == stat.st_mtime
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# Language detection tests
# ---------------------------------------------------------------------------

class TestLanguageDetector:
    @pytest.mark.asyncio
    async def test_detect_english(self):
        detector = HeuristicLanguageDetector()
        lang, conf = await detector.detect("The quick brown fox jumps over the lazy dog")
        assert lang == "en"
        assert conf > 0

    @pytest.mark.asyncio
    async def test_detect_french(self):
        detector = HeuristicLanguageDetector()
        lang, conf = await detector.detect(
            "Le renard brun rapide saute par-dessus le chien paresseux. "
            "Il est très rapide et il court dans la forêt avec les autres animaux. "
            "Nous avons vu le renard et nous avons été surpris par sa vitesse."
        )
        assert lang == "fr"
        assert conf > 0

    @pytest.mark.asyncio
    async def test_detect_german(self):
        detector = HeuristicLanguageDetector()
        lang, conf = await detector.detect(
            "Der schnelle braune Fuchs springt über den faulen Hund"
        )
        assert lang == "de"
        assert conf > 0

    @pytest.mark.asyncio
    async def test_detect_chinese(self):
        detector = HeuristicLanguageDetector()
        lang, conf = await detector.detect("快速棕狐跳过懒狗。今天的天气非常好，我们去公园散步了。")
        assert lang == "zh"
        assert conf > 0

    @pytest.mark.asyncio
    async def test_detect_russian(self):
        detector = HeuristicLanguageDetector()
        lang, conf = await detector.detect("Быстрая коричневая лиса прыгает через ленивую собаку")
        assert lang == "ru"
        assert conf > 0

    @pytest.mark.asyncio
    async def test_detect_spanish(self):
        detector = HeuristicLanguageDetector()
        lang, conf = await detector.detect(
            "El rápido zorro marrón salta sobre el perro perezoso"
        )
        assert lang == "es"

    @pytest.mark.asyncio
    async def test_empty_text(self):
        detector = HeuristicLanguageDetector()
        lang, conf = await detector.detect("")
        assert lang == "en"
        assert conf == 0.0

    @pytest.mark.asyncio
    async def test_japanese(self):
        detector = HeuristicLanguageDetector()
        lang, conf = await detector.detect("日本語のテキストです。これはテスト用の文章で、ひらがなとカタカナが含まれています。")
        assert lang == "ja"
        assert conf > 0


# ---------------------------------------------------------------------------
# Duplicate detection tests
# ---------------------------------------------------------------------------

class TestDuplicateDetector:
    def test_checksum(self):
        detector = DuplicateDetector()
        doc1 = LoadedDocument(
            filename="a.txt", extension=".txt", mime_type="text/plain",
            content=b"hello", size=5,
        )
        doc2 = LoadedDocument(
            filename="b.txt", extension=".txt", mime_type="text/plain",
            content=b"hello", size=5,
        )
        assert detector.checksum(doc1) == detector.checksum(doc2)

    def test_checksum_different(self):
        detector = DuplicateDetector()
        doc1 = LoadedDocument(
            filename="a.txt", extension=".txt", mime_type="text/plain",
            content=b"hello", size=5,
        )
        doc2 = LoadedDocument(
            filename="b.txt", extension=".txt", mime_type="text/plain",
            content=b"world", size=5,
        )
        assert detector.checksum(doc1) != detector.checksum(doc2)

    @pytest.mark.asyncio
    async def test_is_duplicate(self):
        detector = DuplicateDetector()
        doc = LoadedDocument(
            filename="a.txt", extension=".txt", mime_type="text/plain",
            content=b"hello", size=5,
        )
        cs = detector.checksum(doc)
        detector.add_checksum(cs)
        is_dup, _ = await detector.check(doc)
        assert is_dup is True

    @pytest.mark.asyncio
    async def test_not_duplicate(self):
        detector = DuplicateDetector()
        doc = LoadedDocument(
            filename="a.txt", extension=".txt", mime_type="text/plain",
            content=b"hello", size=5,
        )
        is_dup, _ = await detector.check(doc)
        assert is_dup is False

    @pytest.mark.asyncio
    async def test_bulk_add(self):
        detector = DuplicateDetector()
        detector.bulk_add({"abc", "def"})
        is_dup, cs = await detector.check(
            LoadedDocument(
                filename="a.txt", extension=".txt",
                mime_type="text/plain", content=b"x", size=1,
            )
        )
        assert cs not in {"abc", "def"}
        assert is_dup is False


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestDocumentValidator:
    @pytest.mark.asyncio
    async def test_valid_text_file(self):
        config = IngestionConfig(document_max_size=1000)
        validator = DocumentValidator(config)
        doc = LoadedDocument(
            filename="test.txt", extension=".txt", mime_type="text/plain",
            content=b"hello", size=5,
        )
        result = await validator.validate(doc)
        assert result is doc

    @pytest.mark.asyncio
    async def test_file_too_large(self):
        config = IngestionConfig(document_max_size=10)
        validator = DocumentValidator(config)
        doc = LoadedDocument(
            filename="test.txt", extension=".txt", mime_type="text/plain",
            content=b"x" * 20, size=20,
        )
        with pytest.raises(FileTooLargeError):
            await validator.validate(doc)

    @pytest.mark.asyncio
    async def test_empty_file(self):
        config = IngestionConfig(document_max_size=1000)
        validator = DocumentValidator(config)
        doc = LoadedDocument(
            filename="test.txt", extension=".txt", mime_type="text/plain",
            content=b"", size=0,
        )
        with pytest.raises(CorruptedFileError):
            await validator.validate(doc)

    @pytest.mark.asyncio
    async def test_unsupported_extension(self):
        config = IngestionConfig(supported_document_types=[".txt"])
        validator = DocumentValidator(config)
        doc = LoadedDocument(
            filename="test.pdf", extension=".pdf", mime_type="application/pdf",
            content=b"%PDF", size=100,
        )
        with pytest.raises(UnsupportedFormatError):
            await validator.validate(doc)

    @pytest.mark.asyncio
    async def test_unsupported_mime(self):
        config = IngestionConfig(supported_mime_types=["text/plain"])
        validator = DocumentValidator(config)
        doc = LoadedDocument(
            filename="test.txt", extension=".txt", mime_type="application/pdf",
            content=b"hello", size=5,
        )
        with pytest.raises(UnsupportedFormatError):
            await validator.validate(doc)

    @pytest.mark.asyncio
    async def test_pdf_corrupted(self):
        validator = DocumentValidator()
        doc = LoadedDocument(
            filename="test.pdf", extension=".pdf", mime_type="application/pdf",
            content=b"not a pdf", size=10,
        )
        with pytest.raises(CorruptedFileError):
            await validator.validate(doc)

    @pytest.mark.asyncio
    async def test_json_corrupted(self):
        validator = DocumentValidator()
        doc = LoadedDocument(
            filename="test.json", extension=".json", mime_type="application/json",
            content=b"not-json", size=10,
        )
        with pytest.raises(CorruptedFileError):
            await validator.validate(doc)

    @pytest.mark.asyncio
    async def test_valid_json(self):
        validator = DocumentValidator()
        doc = LoadedDocument(
            filename="test.json", extension=".json", mime_type="application/json",
            content=b'{"a": 1}', size=10,
        )
        result = await validator.validate(doc)
        assert result is doc

    @pytest.mark.asyncio
    async def test_validation_error_inheritance(self):
        assert isinstance(FileTooLargeError(100, 50), ValueError)
        assert isinstance(UnsupportedFormatError(".x", "a", []), ValueError)
        assert isinstance(CorruptedFileError(), ValueError)


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------

class TestIngestionPipeline:
    @pytest.fixture
    async def svc(self):
        repo = InMemoryKnowledgeRepository()
        return KnowledgeService(repo)

    @pytest.mark.asyncio
    async def test_ingest_bytes_txt(self, svc):
        coll = await svc.create_collection(name="test-coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"hello world",
            filename="test.txt",
            collection_id=coll.id,
        )
        assert result.document_id
        assert result.title == "test"
        assert "hello world" in result.content
        assert result.language == "en"
        assert result.is_duplicate is False
        assert result.mime_type == "text/plain"
        assert result.checksum

    @pytest.mark.asyncio
    async def test_ingest_bytes_markdown(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"# Title\n\nHello **world**",
            filename="test.md",
            collection_id=coll.id,
        )
        assert result.document_id
        assert "# Title" in result.content

    @pytest.mark.asyncio
    async def test_ingest_bytes_json(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b'{"name": "test", "value": 42}',
            filename="data.json",
            collection_id=coll.id,
        )
        assert result.document_id
        assert "name:" in result.content

    @pytest.mark.asyncio
    async def test_ingest_bytes_html(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"<html><body><p>Hello World</p></body></html>",
            filename="page.html",
            collection_id=coll.id,
        )
        assert result.document_id
        assert "Hello World" in result.content

    @pytest.mark.asyncio
    async def test_ingest_bytes_pdf(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"%PDF-1.4\n(Hello from PDF) Tj\nendstream",
            filename="doc.pdf",
            collection_id=coll.id,
        )
        assert result.document_id
        assert "Hello from PDF" in result.content or "PDF content" in result.content

    @pytest.mark.asyncio
    async def test_ingest_bytes_custom_title(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"hello",
            filename="test.txt",
            collection_id=coll.id,
            title="My Custom Title",
        )
        assert result.title == "My Custom Title"

    @pytest.mark.asyncio
    async def test_ingest_file(self, svc):
        coll = await svc.create_collection(name="coll")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("file content here")
            tmp = f.name
        try:
            pipeline = IngestionPipeline(svc)
            result = await pipeline.ingest_file(
                path=tmp,
                collection_id=coll.id,
            )
            assert result.document_id
            assert "file content here" in result.content
            assert result.source == f"ingestion:{os.path.basename(tmp)}"
        finally:
            os.unlink(tmp)

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, svc):
        coll = await svc.create_collection(name="coll")
        config = IngestionConfig(allow_duplicate_document=False)
        pipeline = IngestionPipeline(svc, config=config)
        result1 = await pipeline.ingest_bytes(
            data=b"same content",
            filename="a.txt",
            collection_id=coll.id,
        )
        assert result1.is_duplicate is False
        result2 = await pipeline.ingest_bytes(
            data=b"same content",
            filename="b.txt",
            collection_id=coll.id,
        )
        assert result2.is_duplicate is True
        assert result2.document_id == result1.document_id

    @pytest.mark.asyncio
    async def test_allow_duplicate(self, svc):
        coll = await svc.create_collection(name="coll")
        config = IngestionConfig(allow_duplicate_document=True)
        pipeline = IngestionPipeline(svc, config=config)
        result1 = await pipeline.ingest_bytes(
            data=b"dup content",
            filename="a.txt",
            collection_id=coll.id,
        )
        result2 = await pipeline.ingest_bytes(
            data=b"dup content",
            filename="b.txt",
            collection_id=coll.id,
        )
        assert result1.is_duplicate is False
        assert result2.is_duplicate is True
        assert result2.document_id != result1.document_id

    @pytest.mark.asyncio
    async def test_ingestion_stages(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"hello",
            filename="test.txt",
            collection_id=coll.id,
        )
        expected_stages = ["load", "validate", "parse", "clean", "metadata", "language", "dedup", "store"]
        for stage in expected_stages:
            assert stage in result.stages_completed, f"Stage {stage} not completed"

    @pytest.mark.asyncio
    async def test_metadata_extraction_in_pipeline(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"hello world",
            filename="data.txt",
            collection_id=coll.id,
        )
        assert result.metadata["filename"] == "data.txt"
        assert result.metadata["extension"] == ".txt"
        assert result.metadata["size"] == 11
        assert len(result.metadata["checksum"]) == 64

    @pytest.mark.asyncio
    async def test_invalid_file_validation(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        with pytest.raises(Exception):
            await pipeline.ingest_bytes(
                data=b"",
                filename="empty.txt",
                collection_id=coll.id,
            )

    @pytest.mark.asyncio
    async def test_custom_metadata_in_pipeline(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"test",
            filename="t.txt",
            collection_id=coll.id,
            custom_metadata={"source": "unit-test"},
        )
        assert result.metadata["custom"]["source"] == "unit-test"
        doc = await svc.get_document(result.document_id)
        assert doc is not None
        meta_keys = [m.key for m in doc.metadata]
        assert "custom" in meta_keys

    @pytest.mark.asyncio
    async def test_language_detected(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        result = await pipeline.ingest_bytes(
            data=b"Le renard brun rapide saute par-dessus le chien paresseux. "
                 b"Il est tres rapide et il court dans la foret avec les autres animaux. "
                 b"Nous avons vu le renard et nous etions surpris par sa vitesse.",
            filename="french.txt",
            collection_id=coll.id,
        )
        assert result.language == "fr"

    @pytest.mark.asyncio
    async def test_concurrent_uploads(self, svc):
        coll = await svc.create_collection(name="coll")
        pipeline = IngestionPipeline(svc)
        import asyncio
        results = await asyncio.gather(*[
            pipeline.ingest_bytes(
                data=f"doc{i}".encode(),
                filename=f"doc{i}.txt",
                collection_id=coll.id,
            )
            for i in range(5)
        ])
        assert len(results) == 5
        assert len(set(r.document_id for r in results)) == 5

    @pytest.mark.asyncio
    async def test_pipeline_config(self, svc):
        config = IngestionConfig(document_max_size=1)
        pipeline = IngestionPipeline(svc, config=config)
        with pytest.raises(Exception):
            await pipeline.ingest_bytes(
                data=b"too large content",
                filename="big.txt",
                collection_id="x",
            )


# ---------------------------------------------------------------------------
# Exception tests
# ---------------------------------------------------------------------------

class TestIngestionExceptions:
    def test_file_too_large_error(self):
        err = FileTooLargeError(100, 50)
        assert "100" in str(err)
        assert err.size == 100
        assert err.max_size == 50

    def test_unsupported_format_error(self):
        err = UnsupportedFormatError(".xyz", "text/xyz", [".txt"])
        assert ".xyz" in str(err)
        assert err.extension == ".xyz"

    def test_corrupted_file_error(self):
        err = CorruptedFileError("bad file")
        assert "bad file" in str(err)
