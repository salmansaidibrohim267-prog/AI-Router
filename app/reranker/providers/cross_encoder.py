from __future__ import annotations

from typing import Any

from app.reranker.calibration import CalibrationStrategy, create_calibration_strategy
from app.reranker.exceptions import RerankerModelError
from app.reranker.models import RerankerResult
from app.reranker.protocol import BaseReranker

try:
    from sentence_transformers import CrossEncoder

    HAS_CROSS_ENCODER = True
except ImportError:
    HAS_CROSS_ENCODER = False


class CrossEncoderReranker(BaseReranker):
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        batch_size: int = 32,
        max_length: int = 512,
        calibration: str | None = None,
        calibration_strategy: CalibrationStrategy | None = None,
    ):
        self._model_name = model_name
        self._batch_size = batch_size
        self._max_length = max_length
        self._calibration = calibration_strategy or (create_calibration_strategy(calibration) if calibration else None)
        self._model: CrossEncoder | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    async def warmup(self) -> None:
        if not HAS_CROSS_ENCODER:
            raise RerankerModelError(
                "sentence_transformers.CrossEncoder is required. Install with: pip install sentence-transformers"
            )
        self._model = CrossEncoder(
            self._model_name,
            max_length=self._max_length,
        )

    async def shutdown(self) -> None:
        self._model = None

    async def score(
        self,
        query: str,
        candidate: dict[str, Any],
        **kwargs: Any,
    ) -> float:
        if self._model is None:
            await self.warmup()
        text = self._get_candidate_text(candidate)
        if not query or not text:
            return 0.0
        try:
            results = self._model.predict([(query, text)])
            return float(results[0])
        except Exception as e:
            raise RerankerModelError(f"Cross-encoder score failed: {e}") from e

    async def batch_score(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        **kwargs: Any,
    ) -> list[float]:
        if self._model is None:
            await self.warmup()
        pairs: list[tuple[str, str]] = []
        for c in candidates:
            text = self._get_candidate_text(c)
            pairs.append((query, text))
        if not pairs:
            return []
        try:
            scores = self._model.predict(pairs, batch_size=self._batch_size)
            return [float(s) for s in scores]
        except Exception as e:
            raise RerankerModelError(f"Cross-encoder batch score failed: {e}") from e

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

        scored = list(zip(candidates, raw_scores, calibrated, strict=False))
        scored.sort(key=lambda x: x[2], reverse=True)
        top = scored[:top_k]

        results: list[RerankerResult] = []
        for rank, (cand, raw, cal) in enumerate(top, 1):
            doc_id = cand.get("id", cand.get("_id", str(hash(str(cand)))))
            results.append(
                RerankerResult(
                    id=doc_id,
                    score=cal,
                    original_score=raw,
                    calibrated_score=cal,
                    rank=rank,
                    metadata=cand.get("metadata", {}),
                    model=self.model_name,
                )
            )
        return results

    def _get_candidate_text(self, candidate: dict[str, Any]) -> str:
        text = candidate.get("text") or candidate.get("content") or ""
        meta = candidate.get("metadata") or {}
        if isinstance(meta, dict):
            text += " " + " ".join(str(v) for v in meta.values() if isinstance(v, str))
        return text
