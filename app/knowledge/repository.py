from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Protocol

from app.knowledge.embedding.models import EmbeddingRecord
from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeMetadata,
    KnowledgeStatus,
)


class KnowledgeRepository(Protocol):
    async def create_collection(self, collection: KnowledgeCollection) -> KnowledgeCollection:
        ...

    async def get_collection(self, collection_id: str) -> KnowledgeCollection | None:
        ...

    async def update_collection(self, collection: KnowledgeCollection) -> KnowledgeCollection | None:
        ...

    async def delete_collection(self, collection_id: str) -> bool:
        ...

    async def list_collections(self, skip: int = 0, limit: int = 100) -> list[KnowledgeCollection]:
        ...

    async def count_collections(self) -> int:
        ...

    async def create_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        ...

    async def get_document(self, document_id: str) -> KnowledgeDocument | None:
        ...

    async def update_document(self, document: KnowledgeDocument) -> KnowledgeDocument | None:
        ...

    async def delete_document(self, document_id: str) -> bool:
        ...

    async def list_documents(self, collection_id: str = "", skip: int = 0, limit: int = 100) -> list[KnowledgeDocument]:
        ...

    async def count_documents(self, collection_id: str = "") -> int:
        ...

    async def search_documents(self, query: str, collection_id: str = "", limit: int = 20) -> list[KnowledgeDocument]:
        ...

    async def get_statistics(self, collection_id: str = "") -> dict[str, Any]:
        ...

    async def create_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk:
        ...

    async def list_chunks(self, document_id: str) -> list[KnowledgeChunk]:
        ...

    async def delete_chunks_by_document(self, document_id: str) -> None:
        ...

    async def save_embedding(self, record: EmbeddingRecord) -> EmbeddingRecord:
        ...

    async def get_embedding(self, chunk_id: str) -> EmbeddingRecord | None:
        ...

    async def delete_embedding(self, chunk_id: str) -> bool:
        ...

    async def list_embeddings(self, document_id: str = "") -> list[EmbeddingRecord]:
        ...

    async def close(self) -> None:
        ...


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._collections: dict[str, KnowledgeCollection] = {}
        self._documents: dict[str, KnowledgeDocument] = {}
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._embeddings: dict[str, EmbeddingRecord] = {}

    async def create_collection(self, collection: KnowledgeCollection) -> KnowledgeCollection:
        with self._lock:
            now = time.time()
            collection.id = collection.id or uuid.uuid4().hex[:16]
            collection.created_at = now
            collection.updated_at = now
            self._collections[collection.id] = collection
            return collection

    async def get_collection(self, collection_id: str) -> KnowledgeCollection | None:
        return self._collections.get(collection_id)

    async def update_collection(self, collection: KnowledgeCollection) -> KnowledgeCollection | None:
        with self._lock:
            existing = self._collections.get(collection.id)
            if not existing:
                return None
            collection.created_at = existing.created_at
            collection.updated_at = time.time()
            collection.version = existing.version + 1
            collection.document_count = existing.document_count
            self._collections[collection.id] = collection
            return collection

    async def delete_collection(self, collection_id: str) -> bool:
        with self._lock:
            if collection_id not in self._collections:
                return False
            docs_to_delete = [
                d.id for d in self._documents.values()
                if d.collection_id == collection_id
            ]
            for doc_id in docs_to_delete:
                self._documents.pop(doc_id, None)
                self._chunks = {
                    k: v for k, v in self._chunks.items()
                    if v.document_id != doc_id
                }
            self._collections.pop(collection_id, None)
            return True

    async def list_collections(self, skip: int = 0, limit: int = 100) -> list[KnowledgeCollection]:
        all_items = list(self._collections.values())
        return all_items[skip:skip + limit]

    async def count_collections(self) -> int:
        return len(self._collections)

    async def create_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        with self._lock:
            now = time.time()
            document.id = document.id or uuid.uuid4().hex[:16]
            document.created_at = now
            document.updated_at = now
            self._documents[document.id] = document
            if document.collection_id in self._collections:
                self._collections[document.collection_id].document_count += 1
            return document

    async def get_document(self, document_id: str) -> KnowledgeDocument | None:
        return self._documents.get(document_id)

    async def update_document(self, document: KnowledgeDocument) -> KnowledgeDocument | None:
        with self._lock:
            existing = self._documents.get(document.id)
            if not existing:
                return None
            document.created_at = existing.created_at
            document.updated_at = time.time()
            document.version = existing.version + 1
            self._documents[document.id] = document
            return document

    async def delete_document(self, document_id: str) -> bool:
        with self._lock:
            doc = self._documents.pop(document_id, None)
            if not doc:
                return False
            self._chunks = {
                k: v for k, v in self._chunks.items()
                if v.document_id != document_id
            }
            if doc.collection_id in self._collections:
                coll = self._collections[doc.collection_id]
                coll.document_count = max(0, coll.document_count - 1)
            return True

    async def list_documents(
        self, collection_id: str = "", skip: int = 0, limit: int = 100
    ) -> list[KnowledgeDocument]:
        docs = list(self._documents.values())
        if collection_id:
            docs = [d for d in docs if d.collection_id == collection_id]
        return docs[skip:skip + limit]

    async def count_documents(self, collection_id: str = "") -> int:
        if collection_id:
            return sum(1 for d in self._documents.values() if d.collection_id == collection_id)
        return len(self._documents)

    async def search_documents(
        self, query: str, collection_id: str = "", limit: int = 20
    ) -> list[KnowledgeDocument]:
        q = query.lower()
        docs = list(self._documents.values())
        if collection_id:
            docs = [d for d in docs if d.collection_id == collection_id]
        matched = []
        for d in docs:
            if q in d.title.lower() or q in d.content.lower() or q in d.source.lower():
                matched.append(d)
        return matched[:limit]

    async def get_statistics(self, collection_id: str = "") -> dict[str, Any]:
        total_collections = len(self._collections)
        total_documents = len(self._documents)
        total_chunks = len(self._chunks)
        if collection_id:
            coll = self._collections.get(collection_id)
            if not coll:
                return {}
            docs = [d for d in self._documents.values() if d.collection_id == collection_id]
            chunks = [c for c in self._chunks.values() if c.collection_id == collection_id]
            total_chars = sum(len(d.content) for d in docs)
            return {
                "collection_id": collection_id,
                "collection_name": coll.name,
                "documents": len(docs),
                "chunks": len(chunks),
                "total_chars": total_chars,
                "tags": list(set(t for d in docs for t in d.tags)),
            }
        total_chars = sum(len(d.content) for d in self._documents.values())
        return {
            "collections": total_collections,
            "documents": total_documents,
            "chunks": total_chunks,
            "total_chars": total_chars,
            "collections_list": [
                {"id": c.id, "name": c.name, "documents": c.document_count}
                for c in self._collections.values()
            ],
        }

    async def create_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk:
        with self._lock:
            chunk.id = chunk.id or uuid.uuid4().hex[:16]
            chunk.created_at = time.time()
            self._chunks[chunk.id] = chunk
            doc = self._documents.get(chunk.document_id)
            if doc:
                doc.chunk_count = sum(1 for c in self._chunks.values() if c.document_id == chunk.document_id)
            return chunk

    async def list_chunks(self, document_id: str) -> list[KnowledgeChunk]:
        return sorted(
            [c for c in self._chunks.values() if c.document_id == document_id],
            key=lambda c: c.chunk_index,
        )

    async def delete_chunks_by_document(self, document_id: str) -> None:
        self._chunks = {
            k: v for k, v in self._chunks.items()
            if v.document_id != document_id
        }

    async def save_embedding(self, record: EmbeddingRecord) -> EmbeddingRecord:
        with self._lock:
            record.id = record.id or uuid.uuid4().hex[:16]
            record.created_at = time.time()
            self._embeddings[record.chunk_id] = record
            return record

    async def get_embedding(self, chunk_id: str) -> EmbeddingRecord | None:
        return self._embeddings.get(chunk_id)

    async def delete_embedding(self, chunk_id: str) -> bool:
        with self._lock:
            return self._embeddings.pop(chunk_id, None) is not None

    async def list_embeddings(self, document_id: str = "") -> list[EmbeddingRecord]:
        if document_id:
            return [
                e for e in self._embeddings.values()
                if e.document_id == document_id
            ]
        return list(self._embeddings.values())

    async def close(self) -> None:
        pass


class SQLiteKnowledgeRepository:
    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    async def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            await self._init_tables()
        return self._conn

    async def _init_tables(self) -> None:
        conn = await self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS collections (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                metadata TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                version INTEGER DEFAULT 1,
                document_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                collection_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT DEFAULT '',
                source TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                metadata TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                version INTEGER DEFAULT 1,
                chunk_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                collection_id TEXT NOT NULL,
                content TEXT NOT NULL,
                chunk_index INTEGER DEFAULT 0,
                start_offset INTEGER DEFAULT 0,
                end_offset INTEGER DEFAULT 0,
                token_estimate INTEGER DEFAULT 0,
                character_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_documents_collection ON documents(collection_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_collection ON chunks(collection_id);
            CREATE TABLE IF NOT EXISTS embeddings (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL UNIQUE,
                model TEXT DEFAULT '',
                provider TEXT DEFAULT '',
                dimensions INTEGER DEFAULT 0,
                vector TEXT DEFAULT '[]',
                token_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
                FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_embeddings_document ON embeddings(document_id);
            CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON embeddings(chunk_id);
        """)
        for col in ("start_offset", "end_offset", "token_estimate", "character_count"):
            try:
                conn.execute(f"ALTER TABLE chunks ADD COLUMN {col} INTEGER DEFAULT 0")
            except Exception:
                pass
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL UNIQUE,
                    model TEXT DEFAULT '',
                    provider TEXT DEFAULT '',
                    dimensions INTEGER DEFAULT 0,
                    vector TEXT DEFAULT '[]',
                    token_count INTEGER DEFAULT 0,
                    metadata TEXT DEFAULT '[]',
                    created_at REAL NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_document ON embeddings(document_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON embeddings(chunk_id)"
            )
        except Exception:
            pass
        conn.commit()

    def _serialize_meta(self, meta: list[KnowledgeMetadata]) -> str:
        return json.dumps([m.to_dict() for m in meta])

    def _deserialize_meta(self, raw: str) -> list[KnowledgeMetadata]:
        try:
            return [KnowledgeMetadata.from_dict(m) for m in json.loads(raw)]
        except (json.JSONDecodeError, TypeError):
            return []

    def _row_to_collection(self, row: sqlite3.Row) -> KnowledgeCollection:
        return KnowledgeCollection(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            status=KnowledgeStatus(row["status"]),
            metadata=self._deserialize_meta(row["metadata"]),
            tags=json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"],
            version=row["version"],
            document_count=row["document_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_document(self, row: sqlite3.Row) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=row["id"],
            collection_id=row["collection_id"],
            title=row["title"],
            content=row["content"],
            source=row["source"],
            status=KnowledgeStatus(row["status"]),
            metadata=self._deserialize_meta(row["metadata"]),
            tags=json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"],
            version=row["version"],
            chunk_count=row["chunk_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_chunk(self, row: sqlite3.Row) -> KnowledgeChunk:
        return KnowledgeChunk(
            id=row["id"],
            document_id=row["document_id"],
            collection_id=row["collection_id"],
            content=row["content"],
            chunk_index=row["chunk_index"],
            start_offset=row.get("start_offset", 0),
            end_offset=row.get("end_offset", 0),
            token_estimate=row.get("token_estimate", 0),
            character_count=row.get("character_count", 0),
            metadata=self._deserialize_meta(row["metadata"]),
            created_at=row["created_at"],
        )

    async def create_collection(self, collection: KnowledgeCollection) -> KnowledgeCollection:
        conn = await self._get_conn()
        with self._lock:
            now = time.time()
            collection.id = collection.id or uuid.uuid4().hex[:16]
            collection.created_at = now
            collection.updated_at = now
            conn.execute(
                """INSERT INTO collections (id, name, description, status, metadata, tags, version, document_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    collection.id, collection.name, collection.description,
                    collection.status.value, self._serialize_meta(collection.metadata),
                    json.dumps(collection.tags), collection.version,
                    collection.document_count, collection.created_at, collection.updated_at,
                ),
            )
            conn.commit()
            return collection

    async def get_collection(self, collection_id: str) -> KnowledgeCollection | None:
        conn = await self._get_conn()
        cursor = conn.execute("SELECT * FROM collections WHERE id = ?", (collection_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_collection(row)

    async def update_collection(self, collection: KnowledgeCollection) -> KnowledgeCollection | None:
        conn = await self._get_conn()
        with self._lock:
            existing = conn.execute("SELECT * FROM collections WHERE id = ?", (collection.id,)).fetchone()
            if not existing:
                return None
            now = time.time()
            collection.created_at = existing["created_at"]
            collection.updated_at = now
            collection.version = existing["version"] + 1
            collection.document_count = existing["document_count"]
            conn.execute(
                """UPDATE collections SET name=?, description=?, status=?, metadata=?, tags=?, version=?, updated_at=? WHERE id=?""",
                (
                    collection.name, collection.description, collection.status.value,
                    self._serialize_meta(collection.metadata), json.dumps(collection.tags),
                    collection.version, collection.updated_at, collection.id,
                ),
            )
            conn.commit()
            return collection

    async def delete_collection(self, collection_id: str) -> bool:
        conn = await self._get_conn()
        with self._lock:
            cursor = conn.execute("SELECT id FROM collections WHERE id = ?", (collection_id,))
            if not cursor.fetchone():
                return False
            conn.execute("DELETE FROM chunks WHERE collection_id = ?", (collection_id,))
            conn.execute("DELETE FROM documents WHERE collection_id = ?", (collection_id,))
            conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
            conn.commit()
            return True

    async def list_collections(self, skip: int = 0, limit: int = 100) -> list[KnowledgeCollection]:
        conn = await self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM collections ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, skip),
        )
        return [self._row_to_collection(row) for row in cursor.fetchall()]

    async def count_collections(self) -> int:
        conn = await self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM collections")
        return cursor.fetchone()[0]

    async def create_document(self, document: KnowledgeDocument) -> KnowledgeDocument:
        conn = await self._get_conn()
        with self._lock:
            now = time.time()
            document.id = document.id or uuid.uuid4().hex[:16]
            document.created_at = now
            document.updated_at = now
            conn.execute(
                """INSERT INTO documents (id, collection_id, title, content, source, status, metadata, tags, version, chunk_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    document.id, document.collection_id, document.title,
                    document.content, document.source, document.status.value,
                    self._serialize_meta(document.metadata), json.dumps(document.tags),
                    document.version, document.chunk_count, document.created_at,
                    document.updated_at,
                ),
            )
            conn.execute(
                "UPDATE collections SET document_count = document_count + 1, updated_at = ? WHERE id = ?",
                (now, document.collection_id),
            )
            conn.commit()
            return document

    async def get_document(self, document_id: str) -> KnowledgeDocument | None:
        conn = await self._get_conn()
        cursor = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_document(row)

    async def update_document(self, document: KnowledgeDocument) -> KnowledgeDocument | None:
        conn = await self._get_conn()
        with self._lock:
            existing = conn.execute("SELECT * FROM documents WHERE id = ?", (document.id,)).fetchone()
            if not existing:
                return None
            now = time.time()
            document.created_at = existing["created_at"]
            document.updated_at = now
            document.version = existing["version"] + 1
            conn.execute(
                """UPDATE documents SET collection_id=?, title=?, content=?, source=?, status=?, metadata=?, tags=?, version=?, updated_at=? WHERE id=?""",
                (
                    document.collection_id, document.title, document.content,
                    document.source, document.status.value,
                    self._serialize_meta(document.metadata), json.dumps(document.tags),
                    document.version, document.updated_at, document.id,
                ),
            )
            conn.commit()
            return document

    async def delete_document(self, document_id: str) -> bool:
        conn = await self._get_conn()
        with self._lock:
            cursor = conn.execute("SELECT collection_id FROM documents WHERE id = ?", (document_id,))
            row = cursor.fetchone()
            if not row:
                return False
            coll_id = row["collection_id"]
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            conn.execute(
                "UPDATE collections SET document_count = MAX(0, document_count - 1), updated_at = ? WHERE id = ?",
                (time.time(), coll_id),
            )
            conn.commit()
            return True

    async def list_documents(
        self, collection_id: str = "", skip: int = 0, limit: int = 100
    ) -> list[KnowledgeDocument]:
        conn = await self._get_conn()
        if collection_id:
            cursor = conn.execute(
                "SELECT * FROM documents WHERE collection_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (collection_id, limit, skip),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, skip),
            )
        return [self._row_to_document(row) for row in cursor.fetchall()]

    async def count_documents(self, collection_id: str = "") -> int:
        conn = await self._get_conn()
        if collection_id:
            cursor = conn.execute("SELECT COUNT(*) FROM documents WHERE collection_id = ?", (collection_id,))
        else:
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    async def search_documents(
        self, query: str, collection_id: str = "", limit: int = 20
    ) -> list[KnowledgeDocument]:
        conn = await self._get_conn()
        pattern = f"%{query}%"
        if collection_id:
            cursor = conn.execute(
                """SELECT * FROM documents WHERE collection_id = ?
                   AND (title LIKE ? OR content LIKE ? OR source LIKE ?)
                   LIMIT ?""",
                (collection_id, pattern, pattern, pattern, limit),
            )
        else:
            cursor = conn.execute(
                """SELECT * FROM documents WHERE title LIKE ? OR content LIKE ? OR source LIKE ?
                   LIMIT ?""",
                (pattern, pattern, pattern, limit),
            )
        return [self._row_to_document(row) for row in cursor.fetchall()]

    async def get_statistics(self, collection_id: str = "") -> dict[str, Any]:
        conn = await self._get_conn()
        if collection_id:
            coll = await self.get_collection(collection_id)
            if not coll:
                return {}
            doc_count = await self.count_documents(collection_id)
            chunk_count = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE collection_id = ?", (collection_id,)
            ).fetchone()[0]
            total_chars = conn.execute(
                "SELECT COALESCE(SUM(LENGTH(content)), 0) FROM documents WHERE collection_id = ?",
                (collection_id,),
            ).fetchone()[0]
            tags_raw = conn.execute(
                "SELECT tags FROM documents WHERE collection_id = ?", (collection_id,),
            ).fetchall()
            all_tags: set[str] = set()
            for row in tags_raw:
                try:
                    all_tags.update(json.loads(row[0]))
                except (json.JSONDecodeError, TypeError):
                    pass
            return {
                "collection_id": collection_id,
                "collection_name": coll.name,
                "documents": doc_count,
                "chunks": chunk_count,
                "total_chars": total_chars,
                "tags": list(all_tags),
            }
        total_collections = await self.count_collections()
        total_documents = await self.count_documents()
        total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        total_chars = conn.execute("SELECT COALESCE(SUM(LENGTH(content)), 0) FROM documents").fetchone()[0]
        coll_rows = conn.execute(
            "SELECT id, name, document_count FROM collections ORDER BY created_at DESC"
        ).fetchall()
        return {
            "collections": total_collections,
            "documents": total_documents,
            "chunks": total_chunks,
            "total_chars": total_chars,
            "collections_list": [
                {"id": r["id"], "name": r["name"], "documents": r["document_count"]}
                for r in coll_rows
            ],
        }

    async def create_chunk(self, chunk: KnowledgeChunk) -> KnowledgeChunk:
        conn = await self._get_conn()
        with self._lock:
            now = time.time()
            chunk.id = chunk.id or uuid.uuid4().hex[:16]
            chunk.created_at = now
            conn.execute(
                """INSERT INTO chunks (id, document_id, collection_id, content, chunk_index, start_offset, end_offset, token_estimate, character_count, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    chunk.id, chunk.document_id, chunk.collection_id,
                    chunk.content, chunk.chunk_index, chunk.start_offset,
                    chunk.end_offset, chunk.token_estimate, chunk.character_count,
                    self._serialize_meta(chunk.metadata), chunk.created_at,
                ),
            )
            chunk_count = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (chunk.document_id,)
            ).fetchone()[0]
            conn.execute("UPDATE documents SET chunk_count = ? WHERE id = ?", (chunk_count, chunk.document_id))
            conn.commit()
            return chunk

    async def list_chunks(self, document_id: str) -> list[KnowledgeChunk]:
        conn = await self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY chunk_index ASC",
            (document_id,),
        )
        return [self._row_to_chunk(row) for row in cursor.fetchall()]

    async def delete_chunks_by_document(self, document_id: str) -> None:
        conn = await self._get_conn()
        with self._lock:
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            conn.execute("UPDATE documents SET chunk_count = 0 WHERE id = ?", (document_id,))
            conn.commit()

    async def save_embedding(self, record: EmbeddingRecord) -> EmbeddingRecord:
        conn = await self._get_conn()
        with self._lock:
            now = time.time()
            record.id = record.id or uuid.uuid4().hex[:16]
            record.created_at = now
            import json as _json
            conn.execute(
                """INSERT OR REPLACE INTO embeddings
                   (id, document_id, chunk_id, model, provider, dimensions, vector, token_count, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id, record.document_id, record.chunk_id,
                    record.model, record.provider, record.dimensions,
                    _json.dumps(record.vector), record.token_count,
                    _json.dumps(record.metadata) if record.metadata else "[]",
                    record.created_at,
                ),
            )
            conn.commit()
            return record

    async def get_embedding(self, chunk_id: str) -> EmbeddingRecord | None:
        conn = await self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM embeddings WHERE chunk_id = ?", (chunk_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_embedding(row)

    async def delete_embedding(self, chunk_id: str) -> bool:
        conn = await self._get_conn()
        with self._lock:
            cursor = conn.execute(
                "SELECT id FROM embeddings WHERE chunk_id = ?", (chunk_id,)
            )
            if not cursor.fetchone():
                return False
            conn.execute("DELETE FROM embeddings WHERE chunk_id = ?", (chunk_id,))
            conn.commit()
            return True

    async def list_embeddings(self, document_id: str = "") -> list[EmbeddingRecord]:
        conn = await self._get_conn()
        if document_id:
            cursor = conn.execute(
                "SELECT * FROM embeddings WHERE document_id = ? ORDER BY created_at",
                (document_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM embeddings ORDER BY created_at"
            )
        return [self._row_to_embedding(row) for row in cursor.fetchall()]

    def _row_to_embedding(self, row) -> EmbeddingRecord:
        import json as _json
        vector_raw = row["vector"]
        if isinstance(vector_raw, str):
            vector = _json.loads(vector_raw)
        else:
            vector = []
        meta_raw = row["metadata"]
        if isinstance(meta_raw, str):
            metadata = _json.loads(meta_raw)
        else:
            metadata = []
        return EmbeddingRecord(
            id=row["id"],
            document_id=row["document_id"],
            chunk_id=row["chunk_id"],
            model=row["model"],
            provider=row["provider"],
            dimensions=row["dimensions"],
            vector=vector,
            token_count=row["token_count"],
            metadata=metadata,
            created_at=row["created_at"],
        )

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def create_knowledge_repository(
    backend: str = "inmemory", **kwargs: Any
) -> KnowledgeRepository:
    if backend == "sqlite":
        return SQLiteKnowledgeRepository(db_path=kwargs.get("db_path", ":memory:"))
    return InMemoryKnowledgeRepository()
