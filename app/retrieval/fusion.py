from __future__ import annotations

from abc import ABC, abstractmethod


class FusionStrategy(ABC):
    @abstractmethod
    def fuse(
        self,
        semantic_scores: dict[str, float],
        keyword_scores: dict[str, float],
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
    ) -> list[tuple[str, float]]: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class WeightedSumFusion(FusionStrategy):
    @property
    def name(self) -> str:
        return "weighted_sum"

    def fuse(
        self,
        semantic_scores: dict[str, float],
        keyword_scores: dict[str, float],
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
    ) -> list[tuple[str, float]]:
        all_ids = set(semantic_scores) | set(keyword_scores)
        fused: dict[str, float] = {}
        for doc_id in all_ids:
            s = semantic_scores.get(doc_id, 0.0) * semantic_weight
            k = keyword_scores.get(doc_id, 0.0) * keyword_weight
            fused[doc_id] = s + k
        return sorted(fused.items(), key=lambda x: x[1], reverse=True)


class RRFusion(FusionStrategy):
    @property
    def name(self) -> str:
        return "rrf"

    def fuse(
        self,
        semantic_scores: dict[str, float],
        keyword_scores: dict[str, float],
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
    ) -> list[tuple[str, float]]:
        semantic_ranks = self._compute_ranks(semantic_scores)
        keyword_ranks = self._compute_ranks(keyword_scores)
        all_ids = set(semantic_ranks) | set(keyword_ranks)
        k = 60.0
        fused: dict[str, float] = {}
        for doc_id in all_ids:
            sr = semantic_ranks.get(doc_id, len(semantic_scores) + 1)
            kr = keyword_ranks.get(doc_id, len(keyword_scores) + 1)
            rrf_score = (1.0 / (k + sr)) * semantic_weight + (1.0 / (k + kr)) * keyword_weight
            fused[doc_id] = rrf_score
        return sorted(fused.items(), key=lambda x: x[1], reverse=True)

    def _compute_ranks(self, scores: dict[str, float]) -> dict[str, int]:
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return {doc_id: rank + 1 for rank, doc_id in enumerate(sorted_ids)}


class CombSUMFusion(FusionStrategy):
    @property
    def name(self) -> str:
        return "combsum"

    def fuse(
        self,
        semantic_scores: dict[str, float],
        keyword_scores: dict[str, float],
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
    ) -> list[tuple[str, float]]:
        all_ids = set(semantic_scores) | set(keyword_scores)
        fused: dict[str, float] = {}
        for doc_id in all_ids:
            s = semantic_scores.get(doc_id, 0.0)
            k = keyword_scores.get(doc_id, 0.0)
            fused[doc_id] = s + k
        return sorted(fused.items(), key=lambda x: x[1], reverse=True)


class CombMNZFusion(FusionStrategy):
    @property
    def name(self) -> str:
        return "combmnz"

    def fuse(
        self,
        semantic_scores: dict[str, float],
        keyword_scores: dict[str, float],
        semantic_weight: float = 0.5,
        keyword_weight: float = 0.5,
    ) -> list[tuple[str, float]]:
        all_ids = set(semantic_scores) | set(keyword_scores)
        fused: dict[str, float] = {}
        for doc_id in all_ids:
            s = semantic_scores.get(doc_id, 0.0)
            k = keyword_scores.get(doc_id, 0.0)
            count = sum(1 for sc in [s, k] if sc > 0)
            if count > 0:
                fused[doc_id] = (s + k) * count
            else:
                fused[doc_id] = 0.0
        return sorted(fused.items(), key=lambda x: x[1], reverse=True)


_FUSION_MAP: dict[str, type[FusionStrategy]] = {
    "weighted_sum": WeightedSumFusion,
    "rrf": RRFusion,
    "combsum": CombSUMFusion,
    "combmnz": CombMNZFusion,
}


def create_fusion_strategy(name: str) -> FusionStrategy:
    cls = _FUSION_MAP.get(name)
    if cls is None:
        raise ValueError(f"Unknown fusion strategy: {name}")
    return cls()
