from __future__ import annotations

from app.citations.config import CitationConfig
from app.citations.exceptions import CitationScoringError
from app.citations.models import Citation, CitationSource


class CitationScorer:
    def __init__(self, config: CitationConfig | None = None):
        self._config = config or CitationConfig()

    def score(
        self,
        source: CitationSource,
        attribution_score: float,
    ) -> float:
        if not (0.0 <= attribution_score <= 1.0):
            raise CitationScoringError("Attribution score must be within [0, 1]")
        raw = (
            self._config.retrieval_weight * min(1.0, max(0.0, source.retrieval_score))
            + self._config.rerank_weight * min(1.0, max(0.0, source.rerank_score))
            + self._config.attribution_weight * attribution_score
        )
        return min(1.0, max(0.0, raw))

    def score_citation(
        self,
        source_ids: list[str],
        sources: list[CitationSource],
        attribution_scores: dict[str, float] | None = None,
    ) -> float:
        if not source_ids:
            return 0.0
        total = 0.0
        count = 0
        for source in sources:
            if source.source_id in source_ids:
                attribution = (attribution_scores or {}).get(source.source_id, 0.0)
                total += self.score(source, attribution)
                count += 1
        return total / count if count else 0.0

    def score_result(
        self,
        citations: list[Citation],
        sources: list[CitationSource],
    ) -> float:
        if not citations:
            return 0.0
        return sum(c.confidence for c in citations) / len(citations)

    def aggregate(
        self,
        citation_scores: list[float],
    ) -> float:
        if not citation_scores:
            return 0.0
        return sum(citation_scores) / len(citation_scores)
