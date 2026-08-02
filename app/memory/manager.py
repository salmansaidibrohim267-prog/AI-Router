from __future__ import annotations

import time
from typing import Any, Callable

from app.memory.config import MemoryVectorConfig
from app.memory.dedup import MemoryDeduplicator
from app.memory.exceptions import (
    MemoryError,
    MemoryLifecycleError,
    MemoryNotFoundError,
    MemoryValidationError,
)
from app.memory.extractor import MemoryExtractor
from app.memory.lifecycle import MemoryLifecycleManager
from app.memory.logging import MemoryLogger
from app.memory.models import (
    ExtractedMemory,
    MemoryCategory,
    MemoryEventType,
    MemoryItem,
    MemoryMetrics,
    MemoryQuery,
    MemoryScope,
    MemorySearchResult,
    MemorySummary,
    MemoryType,
)
from app.memory.repository import MemoryRepository
from app.memory.statistics import MemoryMetricsTracker
from app.memory.summarizer import MemorySummarizer


class MemoryManager:
    def __init__(
        self,
        config: MemoryVectorConfig | None = None,
        repository: MemoryRepository | None = None,
        extractor: MemoryExtractor | None = None,
        scorer: Any | None = None,
        lifecycle: MemoryLifecycleManager | None = None,
        summarizer: MemorySummarizer | None = None,
        deduplicator: MemoryDeduplicator | None = None,
        logger: MemoryLogger | None = None,
        metrics: MemoryMetricsTracker | None = None,
    ):
        self._config = config or MemoryVectorConfig()
        self._repository = repository or MemoryRepository(self._config)
        self._extractor = extractor or MemoryExtractor()
        self._scorer = scorer
        self._lifecycle = lifecycle or MemoryLifecycleManager(self._config, self._repository)
        self._summarizer = summarizer or MemorySummarizer()
        self._deduplicator = deduplicator or MemoryDeduplicator(self._config)
        self._logger = logger or MemoryLogger()
        self._metrics = metrics or MemoryMetricsTracker()
        self._observers: list[Callable[[MemoryEventType, MemoryItem | None, dict[str, Any]], Any]] = []

    def subscribe(self, observer: Callable) -> None:
        self._observers.append(observer)

    def unsubscribe(self, observer: Callable) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    async def _notify(self, event: MemoryEventType, item: MemoryItem | None, **extra: Any) -> None:
        for observer in self._observers:
            try:
                result = observer(event, item, extra)
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                pass

    async def store(
        self,
        content: str,
        scope: MemoryScope | None = None,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
        category: MemoryCategory | None = None,
        importance: float = 0.5,
        confidence: float = 0.8,
        metadata: dict[str, Any] | None = None,
        embed: bool = True,
    ) -> MemoryItem:
        t0 = time.perf_counter()
        scope = scope or MemoryScope()
        try:
            if not content or not content.strip():
                raise MemoryValidationError("Memory content must not be empty")
            category = category or MemoryCategory.GENERAL
            item = MemoryItem(
                content=content.strip(),
                memory_type=memory_type,
                category=category,
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                user_id=scope.user_id,
                session_id=scope.session_id,
                importance=min(1.0, max(0.0, importance)),
                confidence=min(1.0, max(0.0, confidence)),
                metadata=metadata or {},
            )
            existing = self._deduplicator.find_duplicate(item.content, self._repository.all())
            if existing is not None and existing.id:
                item.id = existing.id
                item.created_at = existing.created_at
                item.access_count = existing.access_count
                item.importance = max(existing.importance, item.importance)
                item.confidence = max(existing.confidence, item.confidence)
                item.metadata = {**existing.metadata, **(metadata or {})}
            if embed:
                await self._embed_item(item)
            await self._repository.store(item)
            latency = (time.perf_counter() - t0) * 1000
            self._logger.log_event(MemoryEventType.STORE, item, latency_ms=round(latency, 4))
            self._metrics.record(MemoryEventType.STORE, latency)
            await self._notify(MemoryEventType.STORE, item)
            return item
        except MemoryError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MemoryError(f"Memory store failed: {e}") from e

    async def retrieve(
        self,
        scope: MemoryScope,
        memory_types: list[MemoryType] | None = None,
        top_k: int | None = None,
    ) -> list[MemoryItem]:
        t0 = time.perf_counter()
        try:
            top_k = top_k or self._config.default_top_k
            items = self._repository.list(scope, memory_types)[:top_k]
            for item in items:
                item.touch()
            latency = (time.perf_counter() - t0) * 1000
            self._logger.log_event(
                MemoryEventType.RETRIEVE,
                None,
                scope=scope.filter(),
                count=len(items),
                latency_ms=round(latency, 4),
            )
            self._metrics.record(MemoryEventType.RETRIEVE, latency)
            return items
        except Exception as e:
            self._metrics.record_error()
            raise MemoryError(f"Memory retrieve failed: {e}") from e

    async def update(
        self,
        item_id: str,
        content: str | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        t0 = time.perf_counter()
        try:
            item = self._repository.get(item_id)
            if item is None:
                raise MemoryNotFoundError(f"Memory entry {item_id} not found")
            if content is not None:
                if not content.strip():
                    raise MemoryValidationError("Memory content must not be empty")
                item.content = content.strip()
            if importance is not None:
                item.importance = min(1.0, max(0.0, importance))
            if confidence is not None:
                item.confidence = min(1.0, max(0.0, confidence))
            if metadata is not None:
                item.metadata.update(metadata)
            await self._repository.update(item)
            latency = (time.perf_counter() - t0) * 1000
            self._logger.log_event(MemoryEventType.UPDATE, item, latency_ms=round(latency, 4))
            self._metrics.record(MemoryEventType.UPDATE, latency)
            await self._notify(MemoryEventType.UPDATE, item)
            return item
        except MemoryError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MemoryError(f"Memory update failed: {e}") from e

    async def delete(self, item_id: str) -> bool:
        t0 = time.perf_counter()
        try:
            item = self._repository.get(item_id)
            deleted = await self._repository.delete(item_id)
            latency = (time.perf_counter() - t0) * 1000
            self._logger.log_event(MemoryEventType.DELETE, item, latency_ms=round(latency, 4))
            self._metrics.record(MemoryEventType.DELETE, latency)
            await self._notify(MemoryEventType.DELETE, item)
            return deleted
        except Exception as e:
            self._metrics.record_error()
            raise MemoryError(f"Memory delete failed: {e}") from e

    async def summarize(
        self,
        scope: MemoryScope,
        style: str = "concise",
        memory_types: list[MemoryType] | None = None,
    ) -> MemorySummary:
        t0 = time.perf_counter()
        try:
            items = self._repository.list(scope, memory_types)[: self._config.summarize_max_entries]
            text = await self._summarizer.summarize(items, style=style)
            categories: dict[str, int] = {}
            for item in items:
                categories[item.category.value] = categories.get(item.category.value, 0) + 1
            summary = MemorySummary(
                text=text,
                scope=scope,
                entries_count=len(items),
                categories=categories,
            )
            latency = (time.perf_counter() - t0) * 1000
            self._logger.log_event(
                MemoryEventType.RETRIEVE,
                None,
                scope=scope.filter(),
                summary="summarize",
                latency_ms=round(latency, 4),
            )
            self._metrics.record_summarization()
            return summary
        except MemoryError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            raise MemoryError(f"Memory summarize failed: {e}") from e

    async def search(
        self,
        query: MemoryQuery | None = None,
        text: str | None = None,
        scope: MemoryScope | None = None,
        top_k: int | None = None,
    ) -> list[MemorySearchResult]:
        t0 = time.perf_counter()
        try:
            q = query or MemoryQuery(text=text or "", scope=scope or MemoryScope())
            top_k = top_k or q.top_k
            results = await self._repository.search(
                query=q.text,
                scope=q.scope,
                top_k=top_k,
                memory_types=q.memory_types or None,
            )
            if q.min_score > 0:
                results = [r for r in results if r.score >= q.min_score]
            for r in results:
                r.item.touch()
            latency = (time.perf_counter() - t0) * 1000
            self._logger.log_event(
                MemoryEventType.RETRIEVE,
                None,
                scope=q.scope.filter(),
                count=len(results),
                latency_ms=round(latency, 4),
            )
            self._metrics.record_search(latency)
            return results
        except Exception as e:
            self._metrics.record_error()
            raise MemoryError(f"Memory search failed: {e}") from e

    async def batch_store(
        self,
        entries: list[dict[str, Any]],
        scope: MemoryScope | None = None,
    ) -> list[MemoryItem]:
        scope = scope or MemoryScope()
        results: list[MemoryItem] = []
        for entry in entries:
            item = await self.store(
                content=entry.get("content", ""),
                scope=scope,
                memory_type=MemoryType(entry.get("memory_type", "short_term")),
                category=MemoryCategory(entry.get("category", "general")),
                importance=entry.get("importance", 0.5),
                confidence=entry.get("confidence", 0.8),
                metadata=entry.get("metadata"),
                embed=entry.get("embed", True),
            )
            results.append(item)
        return results

    async def batch_retrieve(
        self,
        item_ids: list[str],
        scope: MemoryScope | None = None,
    ) -> list[MemoryItem]:
        scope = scope or MemoryScope()
        items: list[MemoryItem] = []
        for item_id in item_ids:
            item = self._repository.get(item_id)
            if item is not None and (not scope or scope.is_isolated(item)):
                items.append(item)
        return items

    async def extract(
        self,
        text: str,
        scope: MemoryScope | None = None,
        auto_store: bool = False,
    ) -> list[ExtractedMemory]:
        scope = scope or MemoryScope()
        extracted = self._extractor.extract(text)
        self._metrics.record_extraction()
        if auto_store:
            for mem in extracted:
                await self.store(
                    content=mem.content,
                    scope=scope,
                    category=mem.category,
                    importance=mem.importance,
                    confidence=mem.confidence,
                    metadata=mem.metadata,
                )
        return extracted

    async def run_maintenance(
        self,
        scope: MemoryScope,
        now: float | None = None,
    ) -> dict[str, Any]:
        try:
            return await self._lifecycle.run_maintenance(scope, now)
        except MemoryLifecycleError as e:
            self._metrics.record_error()
            raise

    async def compact(
        self,
        scope: MemoryScope,
        threshold: float | None = None,
    ) -> list[MemoryItem]:
        merged = await self._lifecycle.compact(scope, threshold)
        if merged:
            await self._repository.store_batch(merged)
            self._metrics.record(MemoryEventType.COMPACT)
            for item in merged:
                await self._notify(MemoryEventType.COMPACT, item)
        return merged

    def get_metrics(self) -> MemoryMetrics:
        return self._metrics.get_metrics()

    async def _embed_item(self, item: MemoryItem) -> None:
        if self._repository.embedder is None:
            return
        try:
            result = await self._repository.embedder(item.content)
            if isinstance(result, list):
                item.embedding = result
            elif hasattr(result, "vector"):
                item.embedding = result.vector
        except Exception:
            item.embedding = None
