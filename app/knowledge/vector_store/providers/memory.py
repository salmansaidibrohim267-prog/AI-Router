from __future__ import annotations

import time
import uuid
from typing import Any

from app.knowledge.vector_store.exceptions import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
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


class InMemoryVectorStore:
    def __init__(
        self,
        dimensions: int = 384,
        distance: DistanceMetric = DistanceMetric.COSINE,
        validator: VectorStoreValidator | None = None,
        statistics: VectorStoreStatistics | None = None,
    ):
        self._dimensions = dimensions
        self._distance = distance
        self._validator = validator or VectorStoreValidator(dimensions=dimensions)
        self._stats = statistics or VectorStoreStatistics()
        self._collections: dict[str, VectorCollection] = {}
        self._vectors: dict[str, dict[str, list[VectorRecord]]] = {}
        self._default_collection = "default"

    @property
    def provider_name(self) -> str:
        return "memory"

    async def create_collection(
        self,
        name: str,
        dimensions: int | None = None,
        distance: DistanceMetric | None = None,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> VectorCollection:
        name = self._validator.validate_collection_name(name)
        if name in self._collections:
            raise CollectionAlreadyExistsError(name)
        dims = dimensions or self._dimensions
        coll = VectorCollection(
            name=name,
            dimensions=dims,
            distance=distance or self._distance,
            namespace=namespace,
            metadata=metadata or {},
            created_at=time.time(),
        )
        self._collections[name] = coll
        self._vectors[name] = {}
        self._stats.set_collections(len(self._collections))
        return coll

    async def delete_collection(self, name: str) -> bool:
        self._validator.check_collection_exists(name, name in self._collections)
        del self._collections[name]
        self._vectors.pop(name, None)
        self._stats.set_collections(len(self._collections))
        return True

    async def list_collections(self) -> list[VectorCollection]:
        return list(self._collections.values())

    async def collection_exists(self, name: str) -> bool:
        return name in self._collections

    async def rename_collection(self, old_name: str, new_name: str) -> VectorCollection:
        self._validator.check_collection_exists(old_name, old_name in self._collections)
        if old_name == new_name:
            return self._collections[old_name]
        coll = self._collections.pop(old_name)
        coll.name = self._validator.validate_collection_name(new_name)
        self._collections[new_name] = coll
        self._vectors[new_name] = self._vectors.pop(old_name, {})
        return coll

    async def upsert(self, record: VectorRecord) -> VectorRecord:
        record.id = record.id or uuid.uuid4().hex[:16]
        self._validator.validate_vector(record.vector)
        coll_name = self._default_collection
        rc = await self.create_collection(coll_name) if coll_name not in self._collections else None
        ns_map = self._vectors.setdefault(coll_name, {})
        ns = self._validator.validate_namespace(record.namespace)
        records = ns_map.setdefault(ns, [])
        existing = [r for r in records if r.id == record.id]
        if existing:
            records.remove(existing[0])
        records.append(record)
        coll = self._collections.get(coll_name)
        if coll:
            coll.vector_count = sum(len(v) for v in self._vectors[coll_name].values())
        self._stats.record_upsert(1)
        return record

    async def upsert_batch(self, records: list[VectorRecord]) -> list[VectorRecord]:
        results: list[VectorRecord] = []
        for rec in records:
            r = await self.upsert(rec)
            results.append(r)
        return results

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
        self._validator.validate_vector(vector)
        coll_name = collection or self._default_collection
        self._validator.check_collection_exists(coll_name, coll_name in self._collections)

        ns_map = self._vectors.get(coll_name, {})
        ns = namespace or "default"
        records = ns_map.get(ns, [])

        filtered = self._apply_filter(records, filter or {})
        scored = self._score_all(vector, filtered)
        scored.sort(key=lambda x: x[0], reverse=True)

        if score_threshold is not None:
            scored = [(s, r) for s, r in scored if s >= score_threshold]

        top = scored[:top_k]
        results = [
            SearchResult(
                id=r.id,
                score=s,
                vector=r.vector if include_vector else None,
                metadata=r.metadata if include_metadata else {},
                namespace=r.namespace,
            )
            for s, r in top
        ]
        self._stats.record_search(time.time() - start)
        return results

    def _apply_filter(
        self,
        records: list[VectorRecord],
        filter: dict[str, Any],
    ) -> list[VectorRecord]:
        if not filter:
            return records
        result = list(records)
        for key, value in filter.items():
            result = [r for r in result if r.metadata.get(key) == value]
        return result

    def _score_all(
        self, query: list[float], records: list[VectorRecord]
    ) -> list[tuple[float, VectorRecord]]:
        import math

        results: list[tuple[float, VectorRecord]] = []
        for rec in records:
            score = self._compute_similarity(query, rec.vector)
            results.append((score, rec))
        return results

    def _compute_similarity(self, a: list[float], b: list[float]) -> float:
        import math

        if self._distance == DistanceMetric.COSINE:
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(y * y for y in b))
            if na == 0 or nb == 0:
                return 0.0
            return (dot / (na * nb) + 1) / 2
        elif self._distance == DistanceMetric.EUCLIDEAN:
            dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
            return 1.0 / (1.0 + dist)
        elif self._distance == DistanceMetric.DOT_PRODUCT:
            return sum(x * y for x, y in zip(a, b))
        return 0.0

    async def delete(
        self,
        ids: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        collection: str = "",
        namespace: str = "default",
    ) -> int:
        coll_name = collection or self._default_collection
        self._validator.check_collection_exists(coll_name, coll_name in self._collections)
        ns_map = self._vectors.get(coll_name, {})
        ns = namespace or "default"
        records = ns_map.get(ns, [])
        count = len(records)

        if ids:
            records = [r for r in records if r.id not in ids]
        if filter:
            records = self._apply_filter(records, filter)
            records = [r for r in ns_map.get(ns, []) if r not in records]

        deleted = count - len(records)
        ns_map[ns] = records
        self._stats.record_delete(deleted)
        return deleted

    async def clear(self, collection: str = "", namespace: str = "default") -> int:
        coll_name = collection or self._default_collection
        ns_map = self._vectors.get(coll_name, {})
        ns = namespace or "default"
        records = ns_map.get(ns, [])
        count = len(records)
        if ns == "default" and not namespace:
            for ns_name in ns_map:
                count += len(ns_map[ns_name])
            self._vectors[coll_name] = {}
        else:
            ns_map[ns] = []
        self._stats.record_delete(count)
        return count

    async def statistics(self) -> VectorStoreStats:
        stats = self._stats.snapshot()
        stats.total_vectors = sum(
            sum(len(v) for v in ns_map.values())
            for ns_map in self._vectors.values()
        )
        stats.total_collections = len(self._collections)
        stats.provider = self.provider_name
        stats.dimensions = self._dimensions
        return stats
