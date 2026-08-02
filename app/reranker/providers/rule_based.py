from __future__ import annotations

import re
import time
from typing import Any

from app.reranker.calibration import CalibrationStrategy, create_calibration_strategy
from app.reranker.exceptions import RerankerInputError
from app.reranker.models import RerankerResult
from app.reranker.protocol import BaseReranker


class RuleBasedReranker(BaseReranker):
    def __init__(
        self,
        calibration: str | None = None,
        calibration_strategy: CalibrationStrategy | None = None,
    ):
        self._calibration = calibration_strategy or (
            create_calibration_strategy(calibration) if calibration else None
        )
        self._warmed = False

    @property
    def model_name(self) -> str:
        return "rule_based"

    async def warmup(self) -> None:
        self._warmed = True

    async def shutdown(self) -> None:
        self._warmed = False

    async def score(
        self,
        query: str,
        candidate: dict[str, Any],
        **kwargs: Any,
    ) -> float:
        text = self._get_candidate_text(candidate)
        if not query or not text:
            return 0.0
        q_tokens = set(self._tokenize(query))
        c_tokens = self._tokenize(text)
        if not c_tokens:
            return 0.0
        matches = sum(1 for t in c_tokens if t in q_tokens)
        return matches / max(len(q_tokens), 1)

    async def batch_score(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[float]:
        return [await self.score(query, c, **kwargs) for c in candidates]

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

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def _get_candidate_text(self, candidate: dict[str, Any]) -> str:
        text = candidate.get("text") or candidate.get("content") or ""
        meta = candidate.get("metadata") or {}
        if isinstance(meta, dict):
            text += " " + " ".join(str(v) for v in meta.values() if isinstance(v, str))
        return text
