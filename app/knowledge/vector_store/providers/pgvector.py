from __future__ import annotations

import json
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
    import asyncpg

    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


_DISTANCE_FN: dict[DistanceMetric, str] = {
    DistanceMetric.COSINE: "1 - (embedding <=> $1)",
    DistanceMetric.EUCLIDEAN: "embedding <-> $1",
    DistanceMetric.DOT_PRODUCT: "1 - (embedding <#> $1)",
}


class PgVectorStore:
    def __init__(
        self,
        dsn: str = "postgresql://postgres:postgres@localhost:5432/vectordb",
        table: str = "vectors",
        pool_size: int = 10,
        dimensions: int = 384,
        distance: DistanceMetric = DistanceMetric.COSINE,
        validator: VectorStoreValidator | None = None,
        statistics: VectorStoreStatistics | None = None,
    ):
        self._dsn = dsn
        self._table = table
        self._pool_size = pool_size
        self._dimensions = dimensions
        self._distance = distance
        self._validator = validator or VectorStoreValidator(dimensions=dimensions)
        self._stats = statistics or VectorStoreStatistics()
        self._pool: asyncpg.Pool | None = None

    @property
    def provider_name(self) -> str:
        return "pgvector"

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            if not HAS_PGVECTOR:
                raise RuntimeError("asyncpg is required. Install with: pip install asyncpg")
            self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=self._pool_size)
            async with self._pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._table} (
                        id TEXT PRIMARY KEY,
                        embedding vector({self._dimensions}),
                        metadata JSONB DEFAULT '{{}}'::jsonb,
                        namespace TEXT DEFAULT 'default',
                        created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())
                    )
                """)
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self._table}_namespace
                    ON {self._table}(namespace)
                """)
        return self._pool

    async def create_collection(
        self,
        name: str,
        dimensions: int | None = None,
        distance: DistanceMetric | None = None,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> VectorCollection:
        name = self._validator.validate_collection_name(name)
        pool = await self._get_pool()
        dims = dimensions or self._dimensions
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", name
            )
            if exists:
                raise CollectionAlreadyExistsError(name)
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {name} (
                    id TEXT PRIMARY KEY,
                    embedding vector({dims}),
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    namespace TEXT DEFAULT 'default',
                    created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())
                )
            """)
        return VectorCollection(
            name=name, dimensions=dims, distance=distance or self._distance,
            namespace=namespace, metadata=metadata or {},
        )

    async def delete_collection(self, name: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                await conn.execute(f"DROP TABLE IF EXISTS {name}")
                return True
            except Exception:
                return False

    async def list_collections(self) -> list[VectorCollection]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tablename FROM pg_tables
                WHERE tablename NOT LIKE 'pg_%' AND tablename NOT LIKE 'sql_%'
                  AND tablename != 'vectors'
            """)
            return [VectorCollection(name=r["tablename"], dimensions=self._dimensions) for r in rows]

    async def collection_exists(self, name: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_tables WHERE tablename = $1)", name
            )

    async def rename_collection(self, old_name: str, new_name: str) -> VectorCollection:
        pool = await self._get_pool()
        new_name = self._validator.validate_collection_name(new_name)
        async with pool.acquire() as conn:
            await conn.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
        return VectorCollection(name=new_name, dimensions=self._dimensions)

    async def upsert(self, record: VectorRecord) -> VectorRecord:
        record.id = record.id or uuid.uuid4().hex[:16]
        self._validator.validate_vector(record.vector)
        pool = await self._get_pool()
        vec_str = f"[{','.join(str(x) for x in record.vector)}]"
        meta_json = json.dumps(record.metadata)
        async with pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO {self._table} (id, embedding, metadata, namespace)
                VALUES ($1, $2::vector, $3::jsonb, $4)
                ON CONFLICT (id) DO UPDATE SET
                    embedding = $2::vector,
                    metadata = $3::jsonb,
                    namespace = $4
            """, record.id, vec_str, meta_json, record.namespace)
        self._stats.record_upsert(1)
        return record

    async def upsert_batch(self, records: list[VectorRecord]) -> list[VectorRecord]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            for rec in records:
                rec.id = rec.id or uuid.uuid4().hex[:16]
                self._validator.validate_vector(rec.vector)
                vec_str = f"[{','.join(str(x) for x in rec.vector)}]"
                meta_json = json.dumps(rec.metadata)
                await conn.execute(f"""
                    INSERT INTO {self._table} (id, embedding, metadata, namespace)
                    VALUES ($1, $2::vector, $3::jsonb, $4)
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = $2::vector,
                        metadata = $3::jsonb,
                        namespace = $4
                """, rec.id, vec_str, meta_json, rec.namespace)
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
        pool = await self._get_pool()
        vec_str = f"[{','.join(str(x) for x in vector)}]"
        dist_fn = _DISTANCE_FN.get(self._distance, _DISTANCE_FN[DistanceMetric.COSINE])
        conditions: list[str] = []
        params: list[Any] = [vec_str]
        if namespace != "default":
            conditions.append(f"namespace = ${len(params) + 1}")
            params.append(namespace)
        if filter:
            for k, v in filter.items():
                conditions.append(f"metadata->>${len(params) + 1} = ${len(params) + 2}")
                params.append(k)
                params.append(str(v))
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        select_vec = ", embedding" if include_vector else ""
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, {dist_fn} AS score, metadata{select_vec}
                FROM {self._table}
                WHERE {where_clause}
                ORDER BY score ASC
                LIMIT $1
            """, top_k, *params[1:])
        results: list[SearchResult] = []
        for row in rows:
            score = float(row["score"])
            if self._distance == DistanceMetric.COSINE:
                score = 1.0 - score
            elif self._distance == DistanceMetric.EUCLIDEAN:
                score = 1.0 / (1.0 + score)
            elif self._distance == DistanceMetric.DOT_PRODUCT:
                score = 1.0 - score
            if score_threshold is not None and score < score_threshold:
                continue
            meta = dict(row["metadata"]) if include_metadata else {}
            vec = list(row["embedding"]) if include_vector else None
            results.append(SearchResult(
                id=row["id"],
                score=score,
                vector=vec,
                metadata=meta,
                namespace=meta.get("_namespace", "default"),
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
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if ids:
                placeholders = ", ".join(f"${i+1}" for i in range(len(ids)))
                result = await conn.execute(f"DELETE FROM {self._table} WHERE id IN ({placeholders})", *ids)
                count = len(ids)
            else:
                conditions: list[str] = []
                params: list[Any] = []
                if namespace != "default":
                    conditions.append(f"namespace = ${len(params) + 1}")
                    params.append(namespace)
                if filter:
                    for k, v in filter.items():
                        conditions.append(f"metadata->>${len(params) + 1} = ${len(params) + 2}")
                        params.append(k)
                        params.append(str(v))
                where = " AND ".join(conditions) if conditions else "TRUE"
                result = await conn.execute(f"DELETE FROM {self._table} WHERE {where}", *params)
                count = int(result.split()[-1]) if result else 0
        self._stats.record_delete(count)
        return count

    async def clear(self, collection: str = "", namespace: str = "default") -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if namespace != "default":
                result = await conn.execute(
                    f"DELETE FROM {self._table} WHERE namespace = $1", namespace
                )
                count = int(result.split()[-1]) if result else 0
            else:
                result = await conn.execute(f"TRUNCATE {self._table}")
                count = -1
        return count

    async def statistics(self) -> VectorStoreStats:
        pool = await self._get_pool()
        stats = self._stats.snapshot()
        stats.provider = self.provider_name
        stats.dimensions = self._dimensions
        async with pool.acquire() as conn:
            try:
                row = await conn.fetchrow(f"SELECT COUNT(*) AS cnt FROM {self._table}")
                stats.total_vectors = row["cnt"] if row else 0
            except Exception:
                pass
            try:
                rows = await conn.fetch("""
                    SELECT tablename FROM pg_tables
                    WHERE tablename NOT LIKE 'pg_%' AND tablename NOT LIKE 'sql_%'
                      AND tablename != 'vectors'
                """)
                stats.total_collections = len(rows)
            except Exception:
                stats.total_collections = 0
        return stats

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
