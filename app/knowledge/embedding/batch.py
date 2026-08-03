from __future__ import annotations

import asyncio
from typing import Any

from app.knowledge.embedding.models import EmbeddingResult
from app.knowledge.embedding.providers import EmbeddingProvider


class BatchProcessor:
    def __init__(
        self,
        provider: EmbeddingProvider,
        batch_size: int = 16,
        max_retry: int = 3,
        timeout: int = 60,
    ):
        self._provider = provider
        self._batch_size = batch_size
        self._max_retry = max_retry
        self._timeout = timeout

    async def process(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[EmbeddingResult]:
        if not texts:
            return []

        batches = self._make_batches(texts, self._batch_size)
        all_results: list[EmbeddingResult] = []
        processed = 0

        for batch in batches:
            results = await self._process_batch_with_retry(batch, **kwargs)
            all_results.extend(results)
            processed += len(batch)

        return all_results

    def _make_batches(self, texts: list[str], size: int) -> list[list[str]]:
        return [texts[i : i + size] for i in range(0, len(texts), size)]

    async def _process_batch_with_retry(
        self,
        texts: list[str],
        **kwargs: Any,
    ) -> list[EmbeddingResult]:
        last_error: Exception | None = None
        timeout = kwargs.get("timeout", self._timeout)

        for attempt in range(self._max_retry + 1):
            try:
                results = await asyncio.wait_for(
                    self._provider.embed(texts, **kwargs),
                    timeout=timeout,
                )
                if len(results) != len(texts):
                    raise ValueError(f"Expected {len(texts)} results, got {len(results)}")
                return results
            except asyncio.TimeoutError:
                last_error = asyncio.TimeoutError(f"Embedding timed out after {timeout}s")
            except Exception as e:
                last_error = e
                if not self._is_retryable(e):
                    raise

            if attempt < self._max_retry:
                await asyncio.sleep(self._backoff(attempt))

        raise RuntimeError(f"Embedding failed after {self._max_retry + 1} attempts") from last_error

    def _is_retryable(self, error: Exception) -> bool:
        msg = str(error).lower()
        if isinstance(error, asyncio.TimeoutError):
            return True
        if "rate limit" in msg or "too many" in msg:
            return True
        if "timeout" in msg or "timed out" in msg:
            return True
        if "service unavailable" in msg or "503" in msg:
            return True
        return False

    def _backoff(self, attempt: int) -> float:
        return min(2**attempt * 0.5, 10.0)
