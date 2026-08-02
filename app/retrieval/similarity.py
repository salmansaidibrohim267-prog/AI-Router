from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any

from app.retrieval.exceptions import InvalidSimilarityMetricError
from app.retrieval.models import SimilarityMetric


class SimilarityStrategy(ABC):
    @abstractmethod
    def compute(self, query: list[float], candidate: list[float]) -> float:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class CosineSimilarity(SimilarityStrategy):
    @property
    def name(self) -> str:
        return "cosine"

    def compute(self, query: list[float], candidate: list[float]) -> float:
        dot = sum(a * b for a, b in zip(query, candidate))
        nq = math.sqrt(sum(a * a for a in query))
        nc = math.sqrt(sum(b * b for b in candidate))
        if nq == 0 or nc == 0:
            return 0.0
        return dot / (nq * nc)


class DotProductSimilarity(SimilarityStrategy):
    @property
    def name(self) -> str:
        return "dot_product"

    def compute(self, query: list[float], candidate: list[float]) -> float:
        return sum(a * b for a, b in zip(query, candidate))


class EuclideanSimilarity(SimilarityStrategy):
    @property
    def name(self) -> str:
        return "euclidean"

    def compute(self, query: list[float], candidate: list[float]) -> float:
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(query, candidate)))
        return 1.0 / (1.0 + dist)


_SIMILARITY_MAP: dict[str, type[SimilarityStrategy]] = {
    "cosine": CosineSimilarity,
    "dot_product": DotProductSimilarity,
    "euclidean": EuclideanSimilarity,
}


def create_similarity_strategy(
    metric: str | SimilarityMetric,
) -> SimilarityStrategy:
    key = metric.value if isinstance(metric, SimilarityMetric) else metric
    cls = _SIMILARITY_MAP.get(key)
    if cls is None:
        raise InvalidSimilarityMetricError(key)
    return cls()
