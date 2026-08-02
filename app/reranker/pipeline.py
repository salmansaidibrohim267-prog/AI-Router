from __future__ import annotations

from typing import Any

from app.reranker.config import RerankerConfig
from app.reranker.models import RerankerResult
from app.reranker.protocol import BaseReranker


class CandidateSelectionPipeline:
    def __init__(
        self,
        reranker: BaseReranker,
        config: RerankerConfig | None = None,
    ):
        self._reranker = reranker
        self._config = config or RerankerConfig()

    async def retrieve_top(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        top_k = self._config.top_k_retrieve
        if len(candidates) <= top_k:
            return candidates
        return candidates[:top_k]

    async def rerank_top(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[RerankerResult]:
        top_k = self._config.top_k_rerank
        return await self._reranker.rerank(query, candidates, top_k=top_k, **kwargs)

    async def return_top(
        self,
        results: list[RerankerResult],
    ) -> list[RerankerResult]:
        top_k = self._config.top_k_return
        return results[:top_k]

    async def run(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[RerankerResult]:
        retrieved = await self.retrieve_top(candidates)
        reranked = await self.rerank_top(query, retrieved, **kwargs)
        return await self.return_top(reranked)
