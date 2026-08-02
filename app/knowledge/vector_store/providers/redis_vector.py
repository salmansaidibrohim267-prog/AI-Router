from __future__ import annotations

import json
import math
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
    import redis.asyncio as aioredis

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False


class RedisVectorStore:
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        index: str = "vectors",
        prefix: str = "vec:",
        dimensions: int = 384,
        distance: DistanceMetric = DistanceMetric.COSINE,
        validator: VectorStoreValidator | None = None,
        statistics: VectorStoreStatistics | None = None,
    ):
        self._redis_url = redis_url
        self._index = index
        self._prefix = prefix
        self._dimensions = dimensions
        self._distance = distance
        self._validator = validator or VectorStoreValidator(dimensions=dimensions)
        self._stats = statistics or VectorStoreStatistics()
        self._redis: aioredis.Redis | None = None
        self._collections: dict[str, VectorCollection] = {}

    @property
    def provider_name(self) -> str:
        return "redis_vector"

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            if not HAS_REDIS:
                raise RuntimeError("redis is required. Install with: pip install redis")
            self._redis = aioredis.from_url(self._redis_url, decode_responses=False)
        return self._redis

    async def _vec_to_bytes(self, vector: list[float]) -> bytes:
        import struct
        return struct.pack(f"{len(vector)}f", *vector)

    @staticmethod
    def _bytes_to_vec(data: bytes) -> list[float]:
        import struct
        n = len(data) // 4
        return list(struct.unpack(f"{n}f", data))

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
            name=name, dimensions=dims,
            distance=distance or self._distance,
            namespace=namespace, metadata=metadata or {},
            created_at=time.time(),
        )
        self._collections[name] = coll
        return coll

    async def delete_collection(self, name: str) -> bool:
        self._validator.check_collection_exists(name, name in self._collections)
        r = await self._get_redis()
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match=f"{self._prefix}{name}:*")
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break
        self._collections.pop(name, None)
        return True

    async def list_collections(self) -> list[VectorCollection]:
        return list(self._collections.values())

    async def collection_exists(self, name: str) -> bool:
        return name in self._collections

    async def rename_collection(self, old_name: str, new_name: str) -> VectorCollection:
        self._validator.check_collection_exists(old_name, old_name in self._collections)
        coll = self._collections.pop(old_name)
        coll.name = self._validator.validate_collection_name(new_name)
        self._collections[new_name] = coll
        r = await self._get_redis()
        cursor = 0
        keys_to_rename: list[bytes] = []
        while True:
            cursor, keys = await r.scan(cursor, match=f"{self._prefix}{old_name}:*")
            keys_to_rename.extend(keys)
            if cursor == 0:
                break
        for key in keys_to_rename:
            new_key = key.replace(
                f"{self._prefix}{old_name}:".encode(),
                f"{self._prefix}{new_name}:".encode(),
            )
            await r.rename(key, new_key)
        return coll

    async def upsert(self, record: VectorRecord) -> VectorRecord:
        r = await self._get_redis()
        record.id = record.id or uuid.uuid4().hex[:16]
        self._validator.validate_vector(record.vector)
        key = f"{self._prefix}default:{record.namespace}:{record.id}"
        vec_bytes = await self._vec_to_bytes(record.vector)
        meta_json = json.dumps({**record.metadata, "_id": record.id, "_namespace": record.namespace})
        await r.set(key, vec_bytes + b"|" + meta_json.encode())
        self._stats.record_upsert(1)
        return record

    async def upsert_batch(self, records: list[VectorRecord]) -> list[VectorRecord]:
        r = await self._get_redis()
        async with r.pipeline(transaction=True) as pipe:
            for rec in records:
                rec.id = rec.id or uuid.uuid4().hex[:16]
                self._validator.validate_vector(rec.vector)
                key = f"{self._prefix}default:{rec.namespace}:{rec.id}"
                vec_bytes = await self._vec_to_bytes(rec.vector)
                meta_json = json.dumps({**rec.metadata, "_id": rec.id, "_namespace": rec.namespace})
                pipe.set(key, vec_bytes + b"|" + meta_json.encode())
            await pipe.execute()
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
        r = await self._get_redis()
        coll_name = collection or "default"
        pattern = f"{self._prefix}{coll_name}:{namespace}:*" if namespace != "default" else f"{self._prefix}{coll_name}:*"
        cursor = 0
        all_records: list[tuple[str, list[float], dict[str, Any]]] = []
        while True:
            cursor, keys = await r.scan(cursor, match=pattern)
            if keys:
                values = await r.mget(*keys)
                for key, val in zip(keys, values):
                    if val is None:
                        continue
                    parts = val.split(b"|", 1)
                    vec = self._bytes_to_vec(parts[0])
                    meta: dict[str, Any] = {}
                    if len(parts) > 1:
                        meta = json.loads(parts[1].decode())
                    if filter:
                        matched = True
                        for fk, fv in filter.items():
                            if meta.get(fk) != fv:
                                matched = False
                                break
                        if not matched:
                            continue
                    doc_id = meta.get("_id", key.decode().split(":")[-1])
                    ns = meta.get("_namespace", namespace)
                    all_records.append((doc_id, vec, meta))
            if cursor == 0:
                break

        scored: list[tuple[float, str, list[float], dict[str, Any]]] = []
        for doc_id, vec, meta in all_records:
            s = self._compute_similarity(vector, vec)
            if score_threshold is not None and s < score_threshold:
                continue
            scored.append((s, doc_id, vec, meta))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]
        results = [
            SearchResult(
                id=doc_id,
                score=s,
                vector=vec if include_vector else None,
                metadata=meta if include_metadata else {},
                namespace=meta.get("_namespace", "default"),
            )
            for s, doc_id, vec, meta in top
        ]
        self._stats.record_search(time.time() - start)
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
        r = await self._get_redis()
        coll_name = collection or "default"
        pattern = f"{self._prefix}{coll_name}:*"
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await r.scan(cursor, match=pattern)
            if keys:
                if ids:
                    keys_to_delete = [
                        k for k in keys
                        if k.decode().split(":")[-1] in ids
                    ]
                else:
                    keys_to_delete = list(keys)
                if keys_to_delete:
                    await r.delete(*keys_to_delete)
                    deleted += len(keys_to_delete)
            if cursor == 0:
                break
        self._stats.record_delete(deleted)
        return deleted

    async def clear(self, collection: str = "", namespace: str = "default") -> int:
        r = await self._get_redis()
        coll_name = collection or "default"
        pattern = f"{self._prefix}{coll_name}:{namespace}:*" if namespace != "default" else f"{self._prefix}{coll_name}:*"
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await r.scan(cursor, match=pattern)
            if keys:
                await r.delete(*keys)
                deleted += len(keys)
            if cursor == 0:
                break
        return deleted

    async def statistics(self) -> VectorStoreStats:
        stats = self._stats.snapshot()
        stats.total_collections = len(self._collections)
        stats.provider = self.provider_name
        stats.dimensions = self._dimensions
        r = await self._get_redis()
        cursor = 0
        total = 0
        while True:
            cursor, keys = await r.scan(cursor, match=f"{self._prefix}*")
            total += len(keys)
            if cursor == 0:
                break
        stats.total_vectors = total
        return stats
