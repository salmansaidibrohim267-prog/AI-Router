from __future__ import annotations

import asyncio
from typing import Any

from app.reranker.calibration import CalibrationStrategy, create_calibration_strategy
from app.reranker.exceptions import RerankerInputError
from app.reranker.models import RerankerResult
from app.reranker.protocol import BaseReranker


class EnsembleReranker(BaseReranker):
    def __init__(
        self,
        rerankers: list[BaseReranker],
        weights: list[float] | None = None,
        calibration: str | None = None,
        calibration_strategy: CalibrationStrategy | None = None,
    ):
        if not rerankers:
            raise RerankerInputError("At least one reranker is required")
        self._rerankers = rerankers
        n = len(rerankers)
        if weights and len(weights) != n:
            raise RerankerInputError(
                f"Expected {n} weights, got {len(weights)}"
            )
        total = sum(weights) if weights else n
        self._weights = [w / total for w in (weights or [1.0] * n)]
        self._calibration = calibration_strategy or (
            create_calibration_strategy(calibration) if calibration else None
        )

    @property
    def model_name(self) -> str:
        names = "+".join(r.model_name for r in self._rerankers)
        return f"ensemble({names})"

    async def warmup(self) -> None:
        await asyncio.gather(*[r.warmup() for r in self._rerankers])

    async def shutdown(self) -> None:
        await asyncio.gather(*[r.shutdown() for r in self._rerankers])

    async def score(
        self,
        query: str,
        candidate: dict[str, Any],
        **kwargs: Any,
    ) -> float:
        scores = await asyncio.gather(*[
            r.score(query, candidate, **kwargs) for r in self._rerankers
        ])
        return sum(s * w for s, w in zip(scores, self._weights))

    async def batch_score(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[float]:
        if not candidates:
            return []
        all_scores: list[list[float]] = await asyncio.gather(*[
            r.batch_score(query, candidates, **kwargs) for r in self._rerankers
        ])
        n = len(candidates)
        fused: list[float] = []
        for i in range(n):
            weighted = sum(
                all_scores[j][i] * self._weights[j]
                for j in range(len(self._rerankers))
            )
            fused.append(weighted)
        return fused

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[RerankerResult]:
        if not candidates:
            return []
        raw_scores = await self.batch_score(query, candidates)

        calibrated = raw_scores
        if self._calibration:
            calibrated = self._calibration.calibrate(raw_scores)

        scored = list(zip(candidates, raw_scores, calibrated))
        scored.sort(key=lambda x: x[2], reverse=True)
        top = scored[:top_k]

        results: list[RerankerResult] = []
        for rank, (cand, raw, cal) in enumerate(top, 1):
            doc_id = cand.get("id", cand.get("_id", str(hash(str(cand)))))
            results.append(RerankerResult(
                id=doc_id,
                score=cal,
                original_score=raw,
                calibrated_score=cal,
                rank=rank,
                metadata=cand.get("metadata", {}),
                model=self.model_name,
            ))
        return results
