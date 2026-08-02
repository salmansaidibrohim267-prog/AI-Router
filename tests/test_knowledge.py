import json
import time
import uuid

import pytest

from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeMetadata,
    KnowledgeStatus,
)
from app.knowledge.repository import (
    InMemoryKnowledgeRepository,
    SQLiteKnowledgeRepository,
    create_knowledge_repository,
)
from app.knowledge.service import KnowledgeService
from app.knowledge.validation import (
    validate_collection_name,
    validate_document_title,
    validate_tags,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class TestModels:
    def test_knowledge_metadata(self):
        km = KnowledgeMetadata(key="k", value="v", value_type="string")
        d = km.to_dict()
        assert d["key"] == "k"
        assert d["value"] == "v"
        km2 = KnowledgeMetadata.from_dict(d)
        assert km2.key == "k"

    def test_knowledge_collection(self):
        coll = KnowledgeCollection(
            name="test-coll",
            description="desc",
            tags=["ai", "rag"],
        )
        d = coll.to_dict()
        assert d["name"] == "test-coll"
        assert d["tags"] == ["ai", "rag"]
        assert d["version"] == 1
        coll2 = KnowledgeCollection.from_dict(d)
        assert coll2.name == "test-coll"
        assert coll2.tags == ["ai", "rag"]

    def test_knowledge_document(self):
        doc = KnowledgeDocument(
            collection_id="c1",
            title="Test Doc",
            content="Hello world",
            source="https://example.com",
            tags=["docs"],
        )
        d = doc.to_dict()
        assert d["title"] == "Test Doc"
        assert d["source"] == "https://example.com"
        doc2 = KnowledgeDocument.from_dict(d)
        assert doc2.title == "Test Doc"
        assert doc2.tags == ["docs"]

    def test_knowledge_chunk(self):
        chunk = KnowledgeChunk(
            document_id="d1",
            collection_id="c1",
            content="chunk text",
            chunk_index=0,
        )
        d = chunk.to_dict()
        assert d["chunk_index"] == 0
        assert d["content"] == "chunk text"
        chunk2 = KnowledgeChunk.from_dict(d)
        assert chunk2.document_id == "d1"

    def test_knowledge_status(self):
        assert KnowledgeStatus.ACTIVE.value == "active"
        assert KnowledgeStatus.ARCHIVED.value == "archived"
        assert KnowledgeStatus.DELETED.value == "deleted"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    def test_validate_collection_name(self):
        assert validate_collection_name("  my coll  ") == "my coll"
        with pytest.raises(ValidationError):
            validate_collection_name("")
        with pytest.raises(ValidationError):
            validate_collection_name(" " * 300)

    def test_validate_document_title(self):
        assert validate_document_title("  title  ") == "title"
        with pytest.raises(ValidationError):
            validate_document_title("")

    def test_validate_tags(self):
        assert validate_tags(None) == []
        assert validate_tags(["  a  ", "b"]) == ["a", "b"]
        with pytest.raises(ValidationError):
            validate_tags(["x" * 60])
        with pytest.raises(ValidationError):
            validate_tags(["t"] * 60)

    def test_validation_error(self):
        err = ValidationError("msg")
        assert isinstance(err, ValueError)
        assert str(err) == "msg"


# ---------------------------------------------------------------------------
# InMemory Repository tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_repo():
    return InMemoryKnowledgeRepository()


class TestInMemoryRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_collection(self, mem_repo):
        coll = KnowledgeCollection(name="test")
        created = await mem_repo.create_collection(coll)
        assert created.id
        assert created.name == "test"

        fetched = await mem_repo.get_collection(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    @pytest.mark.asyncio
    async def test_update_collection(self, mem_repo):
        coll = KnowledgeCollection(name="old")
        created = await mem_repo.create_collection(coll)
        created.name = "new"
        updated = await mem_repo.update_collection(created)
        assert updated is not None
        assert updated.name == "new"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_delete_collection(self, mem_repo):
        coll = KnowledgeCollection(name="del")
        created = await mem_repo.create_collection(coll)
        ok = await mem_repo.delete_collection(created.id)
        assert ok is True
        fetched = await mem_repo.get_collection(created.id)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_collection(self, mem_repo):
        ok = await mem_repo.delete_collection("nonexistent")
        assert ok is False

    @pytest.mark.asyncio
    async def test_list_collections(self, mem_repo):
        for i in range(5):
            await mem_repo.create_collection(KnowledgeCollection(name=f"c{i}"))
        cols = await mem_repo.list_collections()
        assert len(cols) == 5
        cols = await mem_repo.list_collections(skip=2, limit=2)
        assert len(cols) == 2

    @pytest.mark.asyncio
    async def test_count_collections(self, mem_repo):
        assert await mem_repo.count_collections() == 0
        await mem_repo.create_collection(KnowledgeCollection(name="c1"))
        assert await mem_repo.count_collections() == 1

    @pytest.mark.asyncio
    async def test_create_and_get_document(self, mem_repo):
        coll = await mem_repo.create_collection(KnowledgeCollection(name="coll"))
        doc = KnowledgeDocument(collection_id=coll.id, title="doc1", content="hello")
        created = await mem_repo.create_document(doc)
        assert created.id
        assert created.title == "doc1"

        fetched = await mem_repo.get_document(created.id)
        assert fetched is not None

    @pytest.mark.asyncio
    async def test_update_document(self, mem_repo):
        coll = await mem_repo.create_collection(KnowledgeCollection(name="coll"))
        doc = KnowledgeDocument(collection_id=coll.id, title="old")
        created = await mem_repo.create_document(doc)
        created.title = "new"
        updated = await mem_repo.update_document(created)
        assert updated.title == "new"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_delete_document(self, mem_repo):
        coll = await mem_repo.create_collection(KnowledgeCollection(name="coll"))
        doc = KnowledgeDocument(collection_id=coll.id, title="del")
        created = await mem_repo.create_document(doc)
        ok = await mem_repo.delete_document(created.id)
        assert ok is True
        assert await mem_repo.get_document(created.id) is None

    @pytest.mark.asyncio
    async def test_delete_document_updates_collection_count(self, mem_repo):
        coll = await mem_repo.create_collection(KnowledgeCollection(name="coll"))
        for i in range(3):
            await mem_repo.create_document(KnowledgeDocument(collection_id=coll.id, title=f"d{i}"))
        assert coll.document_count == 3
        all_docs = await mem_repo.list_documents(collection_id=coll.id)
        await mem_repo.delete_document(all_docs[0].id)
        assert coll.document_count == 2

    @pytest.mark.asyncio
    async def test_list_documents(self, mem_repo):
        coll = await mem_repo.create_collection(KnowledgeCollection(name="coll"))
        for i in range(3):
            await mem_repo.create_document(KnowledgeDocument(collection_id=coll.id, title=f"d{i}"))
        docs = await mem_repo.list_documents()
        assert len(docs) == 3
        docs = await mem_repo.list_documents(collection_id=coll.id)
        assert len(docs) == 3
        docs = await mem_repo.list_documents(collection_id="nonexistent")
        assert len(docs) == 0

    @pytest.mark.asyncio
    async def test_search_documents(self, mem_repo):
        coll = await mem_repo.create_collection(KnowledgeCollection(name="s"))
        await mem_repo.create_document(KnowledgeDocument(
            collection_id=coll.id, title="Alpha", content="hello world",
        ))
        await mem_repo.create_document(KnowledgeDocument(
            collection_id=coll.id, title="Beta", content="goodbye world",
        ))
        results = await mem_repo.search_documents("hello")
        assert len(results) == 1
        assert results[0].title == "Alpha"

    @pytest.mark.asyncio
    async def test_get_statistics(self, mem_repo):
        coll = await mem_repo.create_collection(KnowledgeCollection(name="stat"))
        await mem_repo.create_document(KnowledgeDocument(
            collection_id=coll.id, title="d1", content="abc", tags=["t1"],
        ))
        stats = await mem_repo.get_statistics()
        assert stats["collections"] == 1
        assert stats["documents"] == 1

        coll_stats = await mem_repo.get_statistics(coll.id)
        assert coll_stats["collection_name"] == "stat"
        assert coll_stats["documents"] == 1
        assert "t1" in coll_stats["tags"]

    @pytest.mark.asyncio
    async def test_chunk_crud(self, mem_repo):
        coll = await mem_repo.create_collection(KnowledgeCollection(name="c"))
        doc = await mem_repo.create_document(KnowledgeDocument(collection_id=coll.id, title="d"))
        chunk = KnowledgeChunk(document_id=doc.id, collection_id=coll.id, content="chunk1")
        created = await mem_repo.create_chunk(chunk)
        assert created.id

        chunks = await mem_repo.list_chunks(doc.id)
        assert len(chunks) == 1

        await mem_repo.delete_chunks_by_document(doc.id)
        chunks = await mem_repo.list_chunks(doc.id)
        assert len(chunks) == 0


# ---------------------------------------------------------------------------
# SQLite Repository tests
# ---------------------------------------------------------------------------

@pytest.fixture
def sql_repo():
    return SQLiteKnowledgeRepository(db_path=":memory:")


class TestSQLiteRepository:
    @pytest.mark.asyncio
    async def test_create_and_get_collection(self, sql_repo):
        coll = KnowledgeCollection(name="sql-test", description="desc")
        created = await sql_repo.create_collection(coll)
        assert created.id
        fetched = await sql_repo.get_collection(created.id)
        assert fetched is not None
        assert fetched.name == "sql-test"
        assert fetched.description == "desc"

    @pytest.mark.asyncio
    async def test_update_collection(self, sql_repo):
        coll = KnowledgeCollection(name="old")
        created = await sql_repo.create_collection(coll)
        created.name = "updated"
        updated = await sql_repo.update_collection(created)
        assert updated.name == "updated"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_delete_collection_cascades(self, sql_repo):
        coll = await sql_repo.create_collection(KnowledgeCollection(name="c"))
        doc = await sql_repo.create_document(KnowledgeDocument(
            collection_id=coll.id, title="d",
        ))
        chunk = await sql_repo.create_chunk(KnowledgeChunk(
            document_id=doc.id, collection_id=coll.id, content="ch",
        ))
        ok = await sql_repo.delete_collection(coll.id)
        assert ok is True
        assert await sql_repo.get_collection(coll.id) is None
        assert await sql_repo.get_document(doc.id) is None
        assert await sql_repo.list_chunks(doc.id) == []

    @pytest.mark.asyncio
    async def test_list_collections_pagination(self, sql_repo):
        for i in range(5):
            await sql_repo.create_collection(KnowledgeCollection(name=f"c{i}"))
        all_colls = await sql_repo.list_collections()
        assert len(all_colls) == 5
        page = await sql_repo.list_collections(skip=2, limit=2)
        assert len(page) == 2

    @pytest.mark.asyncio
    async def test_document_crud(self, sql_repo):
        coll = await sql_repo.create_collection(KnowledgeCollection(name="c"))
        doc = KnowledgeDocument(
            collection_id=coll.id, title="doc", content="data", source="src",
        )
        created = await sql_repo.create_document(doc)
        assert created.id

        fetched = await sql_repo.get_document(created.id)
        assert fetched.title == "doc"
        assert fetched.source == "src"

        created.title = "modified"
        updated = await sql_repo.update_document(created)
        assert updated.title == "modified"

        ok = await sql_repo.delete_document(created.id)
        assert ok is True
        assert await sql_repo.get_document(created.id) is None

    @pytest.mark.asyncio
    async def test_search_documents_sqlite(self, sql_repo):
        coll = await sql_repo.create_collection(KnowledgeCollection(name="c"))
        await sql_repo.create_document(KnowledgeDocument(
            collection_id=coll.id, title="Python guide", content="learn python",
        ))
        await sql_repo.create_document(KnowledgeDocument(
            collection_id=coll.id, title="Java guide", content="learn java",
        ))
        results = await sql_repo.search_documents("python")
        assert len(results) == 1
        assert "Python" in results[0].title

    @pytest.mark.asyncio
    async def test_statistics(self, sql_repo):
        coll = await sql_repo.create_collection(KnowledgeCollection(name="stats"))
        await sql_repo.create_document(KnowledgeDocument(
            collection_id=coll.id, title="d1", content="hello world",
        ))
        stats = await sql_repo.get_statistics()
        assert stats["collections"] >= 1
        assert stats["documents"] >= 1

        coll_stats = await sql_repo.get_statistics(coll.id)
        assert coll_stats["collection_name"] == "stats"
        assert coll_stats["total_chars"] >= 11

    @pytest.mark.asyncio
    async def test_close(self, sql_repo):
        await sql_repo.close()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, sql_repo):
        assert await sql_repo.delete_collection("x") is False
        assert await sql_repo.delete_document("x") is False


# ---------------------------------------------------------------------------
# KnowledgeService tests
# ---------------------------------------------------------------------------

class TestKnowledgeService:
    @pytest.fixture
    async def svc(self):
        repo = InMemoryKnowledgeRepository()
        return KnowledgeService(repo)

    @pytest.mark.asyncio
    async def test_create_and_get_collection(self, svc):
        coll = await svc.create_collection(name="my-coll", description="desc")
        assert coll.id
        assert coll.name == "my-coll"

        fetched = await svc.get_collection(coll.id)
        assert fetched is not None
        assert fetched.name == "my-coll"

    @pytest.mark.asyncio
    async def test_create_collection_validation(self, svc):
        with pytest.raises(ValidationError):
            await svc.create_collection(name="")

    @pytest.mark.asyncio
    async def test_update_collection(self, svc):
        coll = await svc.create_collection(name="old")
        updated = await svc.update_collection(coll.id, name="new", description="new desc")
        assert updated is not None
        assert updated.name == "new"
        assert updated.description == "new desc"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_update_nonexistent_collection(self, svc):
        result = await svc.update_collection("x", name="new")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_collection(self, svc):
        coll = await svc.create_collection(name="del")
        ok = await svc.delete_collection(coll.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_list_collections(self, svc):
        for i in range(3):
            await svc.create_collection(name=f"c{i}")
        cols = await svc.list_collections()
        assert len(cols) == 3

    @pytest.mark.asyncio
    async def test_create_document(self, svc):
        coll = await svc.create_collection(name="coll")
        doc = await svc.create_document(
            collection_id=coll.id,
            title="my doc",
            content="hello",
            source="src",
            tags=["guide"],
        )
        assert doc.id
        assert doc.title == "my doc"
        assert doc.tags == ["guide"]

    @pytest.mark.asyncio
    async def test_create_document_invalid_collection(self, svc):
        with pytest.raises(ValidationError):
            await svc.create_document(collection_id="x", title="doc")

    @pytest.mark.asyncio
    async def test_update_document(self, svc):
        coll = await svc.create_collection(name="c")
        doc = await svc.create_document(collection_id=coll.id, title="old")
        updated = await svc.update_document(doc.id, title="new", content="new content")
        assert updated.title == "new"
        assert updated.content == "new content"
        assert updated.version == 2

    @pytest.mark.asyncio
    async def test_update_nonexistent_document(self, svc):
        result = await svc.update_document("x", title="new")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_document(self, svc):
        coll = await svc.create_collection(name="c")
        doc = await svc.create_document(collection_id=coll.id, title="del")
        ok = await svc.delete_document(doc.id)
        assert ok is True

    @pytest.mark.asyncio
    async def test_list_documents(self, svc):
        coll = await svc.create_collection(name="c")
        for i in range(3):
            await svc.create_document(collection_id=coll.id, title=f"d{i}")
        docs = await svc.list_documents()
        assert len(docs) == 3
        docs = await svc.list_documents(collection_id=coll.id)
        assert len(docs) == 3

    @pytest.mark.asyncio
    async def test_search_documents(self, svc):
        coll = await svc.create_collection(name="c")
        await svc.create_document(collection_id=coll.id, title="Alpha", content="hello")
        await svc.create_document(collection_id=coll.id, title="Beta", content="world")
        results = await svc.search_documents("hello")
        assert len(results) == 1
        assert results[0].title == "Alpha"

    @pytest.mark.asyncio
    async def test_statistics(self, svc):
        coll = await svc.create_collection(name="stats")
        await svc.create_document(collection_id=coll.id, title="d1", content="abc")
        stats = await svc.get_statistics()
        assert stats["collections"] == 1
        assert stats["documents"] == 1

        coll_stats = await svc.get_statistics(coll.id)
        assert coll_stats["collection_name"] == "stats"

    @pytest.mark.asyncio
    async def test_add_document_tags(self, svc):
        coll = await svc.create_collection(name="c")
        doc = await svc.create_document(collection_id=coll.id, title="d", tags=["a"])
        updated = await svc.add_document_tags(doc.id, ["b", "c"])
        assert set(updated.tags) == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_remove_document_tags(self, svc):
        coll = await svc.create_collection(name="c")
        doc = await svc.create_document(collection_id=coll.id, title="d", tags=["a", "b"])
        updated = await svc.remove_document_tags(doc.id, ["a"])
        assert updated.tags == ["b"]

    @pytest.mark.asyncio
    async def test_add_collection_tags(self, svc):
        coll = await svc.create_collection(name="c", tags=["x"])
        updated = await svc.add_collection_tags(coll.id, ["y"])
        assert set(updated.tags) == {"x", "y"}

    @pytest.mark.asyncio
    async def test_remove_collection_tags(self, svc):
        coll = await svc.create_collection(name="c", tags=["x", "y"])
        updated = await svc.remove_collection_tags(coll.id, ["x"])
        assert updated.tags == ["y"]

    @pytest.mark.asyncio
    async def test_create_repository_factory(self):
        repo = create_knowledge_repository(backend="inmemory")
        assert isinstance(repo, InMemoryKnowledgeRepository)
        repo2 = create_knowledge_repository(backend="sqlite", db_path=":memory:")
        assert isinstance(repo2, SQLiteKnowledgeRepository)
