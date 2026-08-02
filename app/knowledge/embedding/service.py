from __future__ import annotations

import time
import uuid
from typing import Any

from app.knowledge.embedding.batch import BatchProcessor
from app.knowledge.embedding.cache import (
    EmbeddingCache,
    InMemoryEmbeddingCache,
    _cache_key,
)
from app.knowledge.embedding.config import EmbeddingConfig
from app.knowledge.embedding.models import EmbeddingRecord, EmbeddingResult
from app.knowledge.embedding.providers import (
    EmbeddingProvider,
    create_embedding_provider,
)
from app.knowledge.embedding.statistics import EmbeddingStatistics
from app.knowledge.embedding.validation import EmbeddingValidator
from app.knowledge.models import KnowledgeChunk
from app.knowledge.service import KnowledgeService


class EmbeddingService:
    def __init__(
        self,
        knowledge_service: KnowledgeService,
        config: EmbeddingConfig | None = None,
        provider: EmbeddingProvider | None = None,
        cache: EmbeddingCache | None = None,
        validator: EmbeddingValidator | None = None,
        statistics: EmbeddingStatistics | None = None,
    ):
        self._svc = knowledge_service
        self._config = config or EmbeddingConfig.from_env()
        self._provider = provider or create_embedding_provider(
            self._config.provider, config=self._config,
        )
        self._cache = cache or (
            InMemoryEmbeddingCache(ttl=self._config.cache_ttl)
            if self._config.cache_enabled
            else None
        )
        self._validator = validator or EmbeddingValidator()
        self._stats = statistics or EmbeddingStatistics()
        self._batch = BatchProcessor(
            provider=self._provider,
            batch_size=self._config.batch_size,
            max_retry=self._config.max_retry,
            timeout=self._config.timeout,
        )

    async def embed_text(
        self,
        text: str,
        **kwargs: Any,
    ) -> EmbeddingResult:
        validated = await self._validator.validate_text(text)
        results = await self._embed_batch([validated], **kwargs)
        return results[0]

    async def embed_texts(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[EmbeddingResult]:
        validated = await self._validator.validate_texts(texts)
        return await self._embed_batch(validated, **kwargs)

    async def embed_chunks(
        self,
        chunks: list[KnowledgeChunk],
        **kwargs: Any,
    ) -> list[EmbeddingRecord]:
        texts = [c.content for c in chunks]
        validated = await self._validator.validate_texts(texts)
        results = await self._embed_batch(validated, **kwargs)

        records: list[EmbeddingRecord] = []
        now = time.time()
        for i, chunk in enumerate(chunks):
            record = EmbeddingRecord(
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                model=results[i].model,
                provider=results[i].provider,
                dimensions=results[i].dimensions,
                vector=results[i].vector,
                token_count=results[i].token_count,
                created_at=now,
            )
            record.id = uuid.uuid4().hex[:16]
            records.append(record)
        return records

    async def _embed_batch(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[EmbeddingResult]:
        start = time.time()
        results: list[EmbeddingResult | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        if self._cache:
            for i, text in enumerate(texts):
                key = _cache_key(text, self._config.model)
                cached = await self._cache.get(key)
                if cached is not None:
                    results[i] = EmbeddingResult(
                        vector=cached,
                        model=self._config.model,
                        provider=self._config.provider,
                        dimensions=len(cached),
                    )
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
        else:
            uncached_indices = list(range(len(texts)))
            uncached_texts = texts

        if uncached_texts:
            try:
                batch_results = await self._batch.process(
                    uncached_texts, **kwargs
                )
                for idx, result in zip(uncached_indices, batch_results):
                    results[idx] = result
                    if self._cache:
                        key = _cache_key(texts[idx], self._config.model)
                        await self._cache.set(key, result.vector)
            except Exception as e:
                self._stats.record_error()
                raise

        latency = time.time() - start
        final_results = [r for r in results if r is not None]
        self._stats.record(
            count=len(final_results),
            latency=latency,
            provider=self._config.provider,
            batch_size=len(texts),
        )

        return final_results

    async def get_statistics(self) -> dict[str, Any]:
        stats = self._stats.snapshot()
        if self._cache:
            cache_stats = await self._cache.stats()
            stats["cache"] = cache_stats
        return stats

    @property
    def config(self) -> EmbeddingConfig:
        return self._config

    async def get_embedding(self, chunk_id: str) -> EmbeddingRecord | None:
        repo = self._svc._repo
        if hasattr(repo, "get_embedding"):
            return await repo.get_embedding(chunk_id)
        return None

    async def delete_embedding(self, chunk_id: str) -> bool:
        repo = self._svc._repo
        if hasattr(repo, "delete_embedding"):
            return await repo.delete_embedding(chunk_id)
        return False

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider
