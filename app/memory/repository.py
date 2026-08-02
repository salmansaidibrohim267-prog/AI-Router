from __future__ import annotations

import asyncio
import copy
import time
from typing import Any

from app.memory.config import MemoryVectorConfig
from app.memory.exceptions import MemoryStorageError, MemoryTenantError
from app.memory.models import (
    MemoryItem,
    MemoryScope,
    MemorySearchResult,
    MemoryType,
)
from app.memory.scoring import MemoryScorer


class MemoryRepository:
    def __init__(
        self,
        config: MemoryVectorConfig | None = None,
        vector_store: Any | None = None,
        embedder: Any | None = None,
        scorer: MemoryScorer | None = None,
    ):
        self._config = config or MemoryVectorConfig()
        self._vector_store = vector_store
        self._embedder = embedder
        self._scorer = scorer or MemoryScorer(self._config)
        self._items: dict[str, MemoryItem] = {}

    @property
    def embedder(self) -> Any | None:
        return self._embedder

    @property
    def items(self) -> dict[str, MemoryItem]:
        return self._items

    async def store(self, item: MemoryItem) -> MemoryItem:
        await self._assert_scope(item)
        item.last_updated_at = time.time()
        self._items[item.id] = copy.copy(item)
        if self._vector_store is not None and item.embedding:
            try:
                await self._vector_store.upsert(
                    self._to_vector_record(item)
                )
            except Exception:
                pass
        return item

    async def store_batch(self, items: list[MemoryItem]) -> list[MemoryItem]:
        results: list[MemoryItem] = []
        for item in items:
            results.append(await self.store(item))
        return results

    def get(self, item_id: str) -> MemoryItem | None:
        item = self._items.get(item_id)
        if item is None or item.deleted:
            return None
        return item

    def list(
        self,
        scope: MemoryScope,
        memory_types: list[MemoryType] | None = None,
    ) -> list[MemoryItem]:
        items = [
            item for item in self._items.values()
            if not item.deleted and not item.archived and scope.is_isolated(item)
        ]
        if memory_types:
            types = set(memory_types)
            items = [i for i in items if i.memory_type in types]
        return sorted(items, key=lambda i: i.last_accessed_at, reverse=True)

    def all(self) -> list[MemoryItem]:
        return list(self._items.values())

    def count(self, scope: MemoryScope | None = None) -> int:
        if scope is None or not scope:
            return sum(1 for i in self._items.values() if not i.deleted)
        return sum(
            1 for i in self._items.values()
            if not i.deleted and not i.archived and scope.is_isolated(i)
        )

    async def update(self, item: MemoryItem) -> MemoryItem:
        existing = self._items.get(item.id)
        if existing is None or existing.deleted:
            raise MemoryStorageError(f"Memory entry {item.id} not found")
        if existing.tenant_id and item.tenant_id and existing.tenant_id != item.tenant_id:
            raise MemoryTenantError("Cannot change tenant of existing entry")
        item.last_updated_at = time.time()
        item.created_at = existing.created_at
        self._items[item.id] = copy.copy(item)
        if self._vector_store is not None and item.embedding:
            try:
                await self._vector_store.upsert(
                    self._to_vector_record(item)
                )
            except Exception:
                pass
        return item

    async def delete(self, item_id: str) -> bool:
        item = self._items.get(item_id)
        if item is None:
            return False
        item.deleted = True
        if self._vector_store is not None:
            try:
                await self._vector_store.delete(
                    ids=[item_id],
                    namespace=self._config.namespace,
                )
            except Exception:
                pass
        return True

    async def search(
        self,
        query: str,
        scope: MemoryScope,
        top_k: int = 10,
        memory_types: list[MemoryType] | None = None,
    ) -> list[MemorySearchResult]:
        query_vector: list[float] | None = None
        if self._embedder is not None:
            try:
                result = await self._embedder(query)
                if isinstance(result, list):
                    query_vector = result
                elif hasattr(result, "vector"):
                    query_vector = result.vector
            except Exception:
                query_vector = None

        candidates: list[MemoryItem] = []
        similarity_map: dict[str, float] = {}
        if self._vector_store is not None and query_vector is not None:
            try:
                filter_dict = scope.filter()
                results = await self._vector_store.search(
                    vector=query_vector,
                    top_k=top_k * 4,
                    filter=filter_dict,
                    namespace=self._config.namespace,
                    include_metadata=True,
                )
                ids = {r.id for r in results}
                candidates = [
                    self._items[i] for i in ids
                    if i in self._items
                    and not self._items[i].deleted
                    and not self._items[i].archived
                ]
                similarity_map = {
                    r.id: r.score for r in results if r.id in self._items
                }
            except Exception:
                candidates = []
        if not candidates:
            candidates = self.list(scope)

        if memory_types:
            types = set(memory_types)
            candidates = [c for c in candidates if c.memory_type in types]

        scored = [
            self._scorer.score(item, similarity_map.get(item.id, 0.0))
            for item in candidates
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def find_duplicate(
        self,
        content: str,
        threshold: float = 0.85,
    ) -> MemoryItem | None:
        target = set(content.lower().split())
        if not target:
            return None
        best: tuple[float, MemoryItem] = (0.0, None)  # type: ignore[assignment]
        for item in self._items.values():
            if item.deleted:
                continue
            other = set(item.content.lower().split())
            if not other:
                continue
            overlap = len(target & other) / min(len(target), len(other))
            if overlap > best[0]:
                best = (overlap, item)
        return best[1] if best[0] >= threshold else None

    def _to_vector_record(self, item: MemoryItem) -> Any:
        from app.knowledge.vector_store.models import VectorRecord

        return VectorRecord(
            id=item.id,
            vector=item.embedding or [],
            namespace=self._config.namespace,
            metadata={
                "tenant_id": item.tenant_id,
                "workspace_id": item.workspace_id,
                "user_id": item.user_id,
                "session_id": item.session_id,
                "memory_type": item.memory_type.value,
                "category": item.category.value,
                "content": item.content,
            },
        )

    async def _assert_scope(self, item: MemoryItem) -> None:
        if not item.content.strip():
            raise MemoryStorageError("Memory content must not be empty")
