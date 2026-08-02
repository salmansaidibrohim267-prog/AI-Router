from __future__ import annotations

import time
import uuid
from typing import Any

from app.knowledge.vector_store.exceptions import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    VectorStoreError,
)
from app.knowledge.vector_store.models import (
    DistanceMetric,
    SearchResult,
    VectorCollection,
    VectorRecord,
    VectorStoreStats,
)
from app.knowledge.vector_store.statistics import VectorStoreStatistics
from app.knowledge.vector_store.validation import VectorStoreValidator

try:
    import chromadb
    from chromadb.config import Settings

    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


_DISTANCE_MAP: dict[DistanceMetric, str] = {
    DistanceMetric.COSINE: "cosine",
    DistanceMetric.EUCLIDEAN: "l2",
    DistanceMetric.DOT_PRODUCT: "ip",
}


class ChromaVectorStore:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        auth: str = "",
        dimensions: int = 384,
        distance: DistanceMetric = DistanceMetric.COSINE,
        validator: VectorStoreValidator | None = None,
        statistics: VectorStoreStatistics | None = None,
    ):
        self._host = host
        self._port = port
        self._auth = auth
        self._dimensions = dimensions
        self._distance = distance
        self._validator = validator or VectorStoreValidator(dimensions=dimensions)
        self._stats = statistics or VectorStoreStatistics()
        self._client: chromadb.ClientAPI | None = None

    @property
    def provider_name(self) -> str:
        return "chroma"

    def _get_client(self) -> chromadb.ClientAPI:
        if self._client is None:
            if not HAS_CHROMA:
                raise RuntimeError("chromadb is required. Install with: pip install chromadb")
            settings = Settings()
            if self._auth:
                settings = Settings(chroma_client_auth_credentials=self._auth)
            self._client = chromadb.HttpClient(host=self._host, port=self._port, settings=settings)
        return self._client

    async def create_collection(
        self,
        name: str,
        dimensions: int | None = None,
        distance: DistanceMetric | None = None,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> VectorCollection:
        name = self._validator.validate_collection_name(name)
        client = self._get_client()
        dist = distance or self._distance
        try:
            existing = client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": _DISTANCE_MAP.get(dist, "cosine")},
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to create collection: {e}") from e
        coll = VectorCollection(
            name=name, dimensions=dimensions or self._dimensions,
            distance=dist, namespace=namespace, metadata=metadata or {},
        )
        return coll

    async def delete_collection(self, name: str) -> bool:
        client = self._get_client()
        try:
            client.delete_collection(name)
            return True
        except Exception:
            return False

    async def list_collections(self) -> list[VectorCollection]:
        client = self._get_client()
        colls = client.list_collections()
        results: list[VectorCollection] = []
        for c in colls:
            meta = getattr(c, "metadata", None) or {}
            results.append(VectorCollection(
                name=c.name,
                dimensions=self._dimensions,
                metadata=meta,
            ))
        return results

    async def collection_exists(self, name: str) -> bool:
        collections = await self.list_collections()
        return any(c.name == name for c in collections)

    async def rename_collection(self, old_name: str, new_name: str) -> VectorCollection:
        raise VectorStoreError("Chroma does not support renaming collections. Create a new one and copy data.")

    async def upsert(self, record: VectorRecord) -> VectorRecord:
        client = self._get_client()
        record.id = record.id or uuid.uuid4().hex[:16]
        self._validator.validate_vector(record.vector)
        coll = client.get_or_create_collection("default")
        coll.upsert(
            ids=[record.id],
            embeddings=[record.vector],
            metadatas=[{**record.metadata, "_namespace": record.namespace}],
        )
        self._stats.record_upsert(1)
        return record

    async def upsert_batch(self, records: list[VectorRecord]) -> list[VectorRecord]:
        client = self._get_client()
        coll = client.get_or_create_collection("default")
        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []
        for rec in records:
            rec.id = rec.id or uuid.uuid4().hex[:16]
            self._validator.validate_vector(rec.vector)
            ids.append(rec.id)
            embeddings.append(rec.vector)
            metadatas.append({**rec.metadata, "_namespace": rec.namespace})
        if ids:
            coll.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)
        self._stats.record_upsert(len(records))
        return records

    async def search(
        self,
        vector: list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        collection: str = "",
        namespace: str = "default",
        filter: dict[str, Any] | None = None,
        include_metadata: bool = True,
        include_vector: bool = False,
    ) -> list[SearchResult]:
        start = time.time()
        client = self._get_client()
        coll_name = collection or "default"
        coll = client.get_or_create_collection(coll_name)
        where_filter = None
        conditions: dict[str, Any] = {}
        if namespace != "default":
            conditions["_namespace"] = namespace
        if filter:
            conditions.update(filter)
        if conditions:
            where_filter = conditions
        try:
            result = coll.query(
                query_embeddings=[vector],
                n_results=top_k,
                where=where_filter,
                include=["metadatas", "distances", "embeddings"] if include_vector else ["metadatas", "distances"],
            )
        except Exception as e:
            raise VectorStoreError(f"Search failed: {e}") from e
        results: list[SearchResult] = []
        if result["ids"] and result["ids"][0]:
            for i, id in enumerate(result["ids"][0]):
                dist = result["distances"][0][i] if result.get("distances") else 0.0
                score = 1.0 - dist
                if score_threshold is not None and score < score_threshold:
                    continue
                meta = result["metadatas"][0][i] if result.get("metadatas") else {}
                vec = result["embeddings"][0][i] if include_vector and result.get("embeddings") else None
                results.append(SearchResult(
                    id=id,
                    score=score,
                    vector=vec,
                    metadata=meta or {},
                    namespace=(meta or {}).get("_namespace", "default"),
                ))
        self._stats.record_search(time.time() - start)
        return results

    async def delete(
        self,
        ids: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        collection: str = "",
        namespace: str = "default",
    ) -> int:
        client = self._get_client()
        coll_name = collection or "default"
        coll = client.get_or_create_collection(coll_name)
        where_filter = None
        if filter or namespace != "default":
            conditions: dict[str, Any] = {}
            if namespace != "default":
                conditions["_namespace"] = namespace
            if filter:
                conditions.update(filter)
            where_filter = conditions
        try:
            if ids:
                count = len(ids)
                coll.delete(ids=ids)
            else:
                coll.delete(where=where_filter)
                count = -1
        except Exception:
            count = 0
        self._stats.record_delete(count)
        return count

    async def clear(self, collection: str = "", namespace: str = "default") -> int:
        client = self._get_client()
        coll_name = collection or "default"
        try:
            client.delete_collection(coll_name)
            client.get_or_create_collection(coll_name)
        except Exception:
            pass
        return -1

    async def statistics(self) -> VectorStoreStats:
        client = self._get_client()
        colls = client.list_collections()
        stats = self._stats.snapshot()
        stats.total_collections = len(colls)
        stats.provider = self.provider_name
        stats.dimensions = self._dimensions
        try:
            coll = client.get_or_create_collection("default")
            stats.total_vectors = coll.count()
        except Exception:
            pass
        return stats
