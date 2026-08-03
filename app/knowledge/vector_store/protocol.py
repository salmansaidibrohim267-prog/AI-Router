from __future__ import annotations

from typing import Any, Protocol

from app.knowledge.vector_store.models import (
    DistanceMetric,
    SearchResult,
    VectorCollection,
    VectorRecord,
    VectorStoreStats,
)


class VectorStore(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def create_collection(
        self,
        name: str,
        dimensions: int,
        distance: DistanceMetric = DistanceMetric.COSINE,
        namespace: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> VectorCollection: ...

    async def delete_collection(self, name: str) -> bool: ...

    async def list_collections(self) -> list[VectorCollection]: ...

    async def collection_exists(self, name: str) -> bool: ...

    async def rename_collection(self, old_name: str, new_name: str) -> VectorCollection: ...

    async def upsert(self, record: VectorRecord) -> VectorRecord: ...

    async def upsert_batch(self, records: list[VectorRecord]) -> list[VectorRecord]: ...

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
    ) -> list[SearchResult]: ...

    async def delete(
        self,
        ids: list[str] | None = None,
        filter: dict[str, Any] | None = None,
        collection: str = "",
        namespace: str = "default",
    ) -> int: ...

    async def clear(self, collection: str = "", namespace: str = "default") -> int: ...

    async def statistics(self) -> VectorStoreStats: ...
