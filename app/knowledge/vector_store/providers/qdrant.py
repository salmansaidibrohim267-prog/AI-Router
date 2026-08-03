from __future__ import annotations

import time
import uuid
from typing import Any

from app.knowledge.vector_store.exceptions import (
    CollectionAlreadyExistsError,
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
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False


_DISTANCE_MAP: dict[DistanceMetric, str] = {
    DistanceMetric.COSINE: "Cosine",
    DistanceMetric.EUCLIDEAN: "Euclid",
    DistanceMetric.DOT_PRODUCT: "Dot",
}


class QdrantVectorStore:
    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str = "",
        prefer_grpc: bool = False,
        dimensions: int = 384,
        distance: DistanceMetric = DistanceMetric.COSINE,
        validator: VectorStoreValidator | None = None,
        statistics: VectorStoreStatistics | None = None,
    ):
        self._url = url
        self._api_key = api_key
        self._prefer_grpc = prefer_grpc
        self._dimensions = dimensions
        self._distance = distance
        self._validator = validator or VectorStoreValidator(dimensions=dimensions)
        self._stats = statistics or VectorStoreStatistics()
        self._client: QdrantClient | None = None

    @property
    def provider_name(self) -> str:
        return "qdrant"

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            if not HAS_QDRANT:
                raise RuntimeError("qdrant_client is required. Install with: pip install qdrant-client")
            self._client = QdrantClient(
                url=self._url,
                api_key=self._api_key or None,
                prefer_grpc=self._prefer_grpc,
            )
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
        dims = dimensions or self._dimensions
        dist = distance or self._distance
        qd_dist = _DISTANCE_MAP.get(dist, "Cosine")
        try:
            client.create_collection(
                collection_name=name,
                vectors_config=qmodels.VectorParams(size=dims, distance=qd_dist),
            )
        except Exception as e:
            if "already exists" in str(e).lower():
                raise CollectionAlreadyExistsError(name) from e
            raise VectorStoreError(f"Failed to create collection: {e}") from e
        coll = VectorCollection(name=name, dimensions=dims, distance=dist, namespace=namespace, metadata=metadata or {})
        self._stats.set_collections(len(client.get_collections().collections))
        return coll

    async def delete_collection(self, name: str) -> bool:
        client = self._get_client()
        try:
            client.delete_collection(collection_name=name)
            return True
        except Exception:
            return False

    async def list_collections(self) -> list[VectorCollection]:
        client = self._get_client()
        colls = client.get_collections().collections
        results: list[VectorCollection] = []
        for c in colls:
            info = client.get_collection(c.name)
            dims = info.config.params.vectors.size if info.config.params.vectors else 384
            results.append(VectorCollection(name=c.name, dimensions=dims))
        self._stats.set_collections(len(results))
        return results

    async def collection_exists(self, name: str) -> bool:
        client = self._get_client()
        try:
            info = client.get_collection(name)
            return info is not None
        except Exception:
            return False

    async def rename_collection(self, old_name: str, new_name: str) -> VectorCollection:
        raise VectorStoreError("Qdrant does not support renaming collections. Create a new one and copy data.")

    async def upsert(self, record: VectorRecord) -> VectorRecord:
        client = self._get_client()
        record.id = record.id or uuid.uuid4().hex[:16]
        self._validator.validate_vector(record.vector)
        point_id = record.id
        try:
            int(point_id)
        except ValueError:
            point_id = uuid.uuid4().hex[:16]
        payload: dict[str, Any] = dict(record.metadata)
        payload["_namespace"] = record.namespace
        client.upsert(
            collection_name="default",
            points=[qmodels.PointStruct(id=point_id, vector=record.vector, payload=payload)],
        )
        self._stats.record_upsert(1)
        return record

    async def upsert_batch(self, records: list[VectorRecord]) -> list[VectorRecord]:
        client = self._get_client()
        points: list[qmodels.PointStruct] = []
        coll_name = "default"
        for rec in records:
            rec.id = rec.id or uuid.uuid4().hex[:16]
            self._validator.validate_vector(rec.vector)
            point_id = rec.id
            try:
                int(point_id)
            except ValueError:
                point_id = uuid.uuid4().hex[:16]
            payload: dict[str, Any] = dict(rec.metadata)
            payload["_namespace"] = rec.namespace
            points.append(qmodels.PointStruct(id=point_id, vector=rec.vector, payload=payload))
        if points:
            client.upsert(collection_name=coll_name, points=points)
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
        qfilter = None
        if filter or namespace != "default":
            conditions = []
            if namespace != "default":
                conditions.append(qmodels.FieldCondition(key="_namespace", match=qmodels.MatchValue(value=namespace)))
            for k, v in (filter or {}).items():
                conditions.append(qmodels.FieldCondition(key=k, match=qmodels.MatchValue(value=v)))
            if conditions:
                qfilter = qmodels.Filter(must=conditions)
        try:
            result = client.search(
                collection_name=coll_name,
                query_vector=vector,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=qfilter,
                with_payload=include_metadata,
                with_vector=include_vector,
            )
        except Exception as e:
            raise VectorStoreError(f"Search failed: {e}") from e
        results = [
            SearchResult(
                id=str(hit.id),
                score=hit.score,
                vector=hit.vector if include_vector else None,
                metadata=hit.payload or {},
                namespace=(hit.payload or {}).get("_namespace", "default"),
            )
            for hit in result
        ]
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
        count = 0
        if ids:
            points_ids: list[Any] = []
            for id in ids:
                try:
                    points_ids.append(int(id))
                except ValueError:
                    points_ids.append(id)
            _ = client.delete(
                collection_name=coll_name,
                points_selector=qmodels.PointIdsList(points=points_ids),
            )
            count = len(ids)
        elif filter or namespace != "default":
            conditions = []
            if namespace != "default":
                conditions.append(qmodels.FieldCondition(key="_namespace", match=qmodels.MatchValue(value=namespace)))
            for k, v in (filter or {}).items():
                conditions.append(qmodels.FieldCondition(key=k, match=qmodels.MatchValue(value=v)))
            qfilter = qmodels.Filter(must=conditions) if conditions else None
            client.delete(
                collection_name=coll_name,
                points_selector=qmodels.FilterSelector(filter=qfilter),
            )
            count = -1
        self._stats.record_delete(count)
        return count

    async def clear(self, collection: str = "", namespace: str = "default") -> int:
        client = self._get_client()
        coll_name = collection or "default"
        qfilter = None
        if namespace != "default":
            qfilter = qmodels.Filter(
                must=[qmodels.FieldCondition(key="_namespace", match=qmodels.MatchValue(value=namespace))]
            )
        _ = client.delete(
            collection_name=coll_name,
            points_selector=(
                qmodels.FilterSelector(filter=qfilter) if qfilter else qmodels.FilterSelector(filter=qmodels.Filter())
            ),
        )
        return -1

    async def statistics(self) -> VectorStoreStats:
        client = self._get_client()
        colls = client.get_collections().collections
        stats = self._stats.snapshot()
        stats.total_collections = len(colls)
        stats.provider = self.provider_name
        stats.dimensions = self._dimensions
        try:
            info = client.get_collection("default")
            if info.points_count:
                stats.total_vectors = info.points_count
        except Exception:
            pass
        return stats
