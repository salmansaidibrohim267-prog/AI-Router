from __future__ import annotations

from typing import Any

from app.knowledge.vector_store.config import VectorStoreConfig
from app.knowledge.vector_store.models import (
    DistanceMetric,
    SearchResult,
    VectorCollection,
    VectorRecord,
    VectorStoreStats,
)
from app.knowledge.vector_store.validation import VectorStoreValidator


class VectorStoreService:
    def __init__(
        self,
        store: Any,
        config: VectorStoreConfig | None = None,
        validator: VectorStoreValidator | None = None,
    ):
        self._store = store
        self._config = config or VectorStoreConfig.from_env()
        self._validator = validator or VectorStoreValidator(dimensions=self._config.dimensions)

    @property
    def store(self) -> Any:
        return self._store

    async def create_collection(
        self,
        name: str,
        dimensions: int | None = None,
        distance: DistanceMetric | None = None,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> VectorCollection:
        return await self._store.create_collection(
            name=name, dimensions=dimensions, distance=distance,
            namespace=namespace, metadata=metadata,
        )

    async def delete_collection(self, name: str) -> bool:
        return await self._store.delete_collection(name)

    async def list_collections(self) -> list[VectorCollection]:
        return await self._store.list_collections()

    async def upsert(self, record: VectorRecord) -> VectorRecord:
        return await self._store.upsert(record)

    async def upsert_batch(self, records: list[VectorRecord]) -> list[VectorRecord]:
        return await self._store.upsert_batch(records)

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
        return await self._store.search(
            vector=vector, top_k=top_k, score_threshold=score_threshold,
            collection=collection, namespace=namespace, filter=filter,
            include_metadata=include_metadata, include_vector=include_vector,
        )

    async def delete(
        self,
        ids: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        collection: str = "",
        namespace: str = "default",
    ) -> int:
        return await self._store.delete(
            ids=ids, filter=filter, collection=collection, namespace=namespace,
        )

    async def clear(self, collection: str = "", namespace: str = "default") -> int:
        return await self._store.clear(collection=collection, namespace=namespace)

    async def statistics(self) -> VectorStoreStats:
        return await self._store.statistics()
