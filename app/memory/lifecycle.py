from __future__ import annotations

import time
from typing import Any

from app.memory.config import MEMORY_TYPE_TTL_DAYS, MemoryVectorConfig
from app.memory.exceptions import MemoryLifecycleError
from app.memory.models import MemoryItem, MemoryScope


class MemoryLifecycleManager:
    def __init__(
        self,
        config: MemoryVectorConfig | None = None,
        repository: Any | None = None,
    ):
        self._config = config or MemoryVectorConfig()
        self._repository = repository

    async def check_ttl(self, item: MemoryItem, now: float | None = None) -> bool:
        ttl_days = self._ttl_for(item)
        if ttl_days is None or not self._config.enable_ttl:
            return False
        now = now if now is not None else time.time()
        age_days = (now - item.created_at) / 86400.0
        return age_days > ttl_days

    def _ttl_for(self, item: MemoryItem) -> float | None:
        if item.metadata.get("ttl_days") is not None:
            return float(item.metadata["ttl_days"])
        return MEMORY_TYPE_TTL_DAYS.get(item.memory_type.value, self._config.ttl_days)

    async def run_maintenance(
        self,
        scope: MemoryScope,
        now: float | None = None,
    ) -> dict[str, Any]:
        try:
            now = now if now is not None else time.time()
            items = [i for i in self._repository.list(scope) if not i.archived]
            expired = [i for i in items if await self.check_ttl(i, now)]
            archived: list[MemoryItem] = []
            pruned: list[MemoryItem] = []
            for item in items:
                if item.id in {e.id for e in expired}:
                    continue
                age_days = (now - item.last_accessed_at) / 86400.0
                if self._config.enable_archival and age_days > self._config.archive_after_days:
                    item.archived = True
                    archived.append(item)

            if self._config.enable_ttl:
                for item in expired:
                    await self._repository.delete(item.id)
                pruned = expired

            if self._config.enable_pruning:
                active = [i for i in items if i.id not in {e.id for e in expired}]
                pruned += self._prune(active)

            archived += await self._collect_archived(items)
            return {
                "expired": [e.id for e in expired],
                "archived": [a.id for a in archived],
                "pruned": [p.id for p in pruned],
            }
        except MemoryLifecycleError:
            raise
        except Exception as e:
            raise MemoryLifecycleError(f"Memory maintenance failed: {e}") from e

    def _prune(self, items: list[MemoryItem]) -> list[MemoryItem]:
        if not self._config.enable_pruning:
            return []
        if len(items) <= self._config.max_entries:
            return []
        excess = len(items) - self._config.max_entries
        excess = min(excess, self._config.prune_batch_size)
        sorted_items = sorted(
            items,
            key=lambda i: (i.importance, i.last_accessed_at),
        )
        pruned = sorted_items[:excess]
        for item in pruned:
            self._repository.items.pop(item.id, None)
            item.deleted = True
        return pruned

    async def _collect_archived(self, items: list[MemoryItem]) -> list[MemoryItem]:
        archived: list[MemoryItem] = []
        for item in items:
            if item.archived:
                archived.append(item)
                if self._config.enable_gc:
                    self._repository.items.pop(item.id, None)
                    item.deleted = True
        return archived

    async def compact(
        self,
        scope: MemoryScope,
        threshold: float | None = None,
    ) -> list[MemoryItem]:
        if not self._config.enable_compaction:
            return []
        threshold = threshold or self._config.compaction_similarity_threshold
        items = self._repository.list(scope)
        merged: list[MemoryItem] = []
        used: set[str] = set()
        for i, item in enumerate(items):
            if item.id in used:
                continue
            base = item
            for j in range(i + 1, len(items)):
                other = items[j]
                if other.id in used:
                    continue
                if self._similarity(base.content, other.content) >= threshold:
                    used.add(other.id)
                    base = self._merge(base, other)
            merged.append(base)
        return merged

    def _similarity(self, a: str, b: str) -> float:
        ta = set(a.lower().split())
        tb = set(b.lower().split())
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / min(len(ta), len(tb))

    def _merge(self, a: MemoryItem, b: MemoryItem) -> MemoryItem:
        separator = "\n\n" if not a.content.endswith("\n") else ""
        return MemoryItem(
            id=a.id,
            content=a.content + separator + b.content,
            memory_type=a.memory_type,
            category=a.category,
            tenant_id=a.tenant_id,
            workspace_id=a.workspace_id,
            user_id=a.user_id,
            session_id=a.session_id,
            importance=max(a.importance, b.importance),
            confidence=max(a.confidence, b.confidence),
            access_count=a.access_count + b.access_count,
            metadata={**a.metadata, **b.metadata},
            embedding=a.embedding,
        )
