from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any


class NormalizationStrategy(ABC):
    @abstractmethod
    def normalize(self, scores: list[float]) -> list[float]:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...


class MinMaxNormalization(NormalizationStrategy):
    @property
    def name(self) -> str:
        return "min_max"

    def normalize(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        mn = min(scores)
        mx = max(scores)
        if mx == mn:
            return [1.0] * len(scores)
        return [(s - mn) / (mx - mn) for s in scores]


class ZScoreNormalization(NormalizationStrategy):
    @property
    def name(self) -> str:
        return "z_score"

    def normalize(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        n = len(scores)
        mean = sum(scores) / n
        variance = sum((s - mean) ** 2 for s in scores) / n
        std = math.sqrt(variance) if variance > 0 else 1.0
        normalized = [(s - mean) / std for s in scores]
        mn = min(normalized)
        mx = max(normalized)
        if mx == mn:
            return [0.5] * n
        return [(x - mn) / (mx - mn) for x in normalized]


class SoftmaxNormalization(NormalizationStrategy):
    @property
    def name(self) -> str:
        return "softmax"

    def normalize(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        shifted = [s - max(scores) for s in scores]
        exp_scores = [math.exp(s) for s in shifted]
        total = sum(exp_scores)
        if total == 0:
            return [1.0 / len(scores)] * len(scores)
        return [e / total for e in exp_scores]


class RankBasedNormalization(NormalizationStrategy):
    @property
    def name(self) -> str:
        return "rank_based"

    def normalize(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        n = len(scores)
        sorted_pairs = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        result = [0.0] * n
        for rank, (orig_idx, _) in enumerate(sorted_pairs):
            result[orig_idx] = 1.0 - (rank / max(n - 1, 1))
        return result


_NORM_MAP: dict[str, type[NormalizationStrategy]] = {
    "min_max": MinMaxNormalization,
    "z_score": ZScoreNormalization,
    "softmax": SoftmaxNormalization,
    "rank_based": RankBasedNormalization,
}


def create_normalization_strategy(name: str) -> NormalizationStrategy:
    cls = _NORM_MAP.get(name)
    if cls is None:
        raise ValueError(f"Unknown normalization strategy: {name}")
    return cls()
