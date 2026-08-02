from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.reranker.models import RerankerResult


class BaseReranker(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @abstractmethod
    async def warmup(self) -> None:
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        ...

    @abstractmethod
    async def score(
        self,
        query: str,
        candidate: dict[str, Any],
        **kwargs: Any,
    ) -> float:
        ...

    @abstractmethod
    async def batch_score(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[float]:
        ...

    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[RerankerResult]:
        ...

    async def rerank_async(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[RerankerResult]:
        return await self.rerank(query, candidates, top_k, **kwargs)
