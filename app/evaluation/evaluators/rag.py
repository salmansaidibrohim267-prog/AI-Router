from __future__ import annotations

import re
from typing import Any

from ..models import EvaluationSample, MetricScore
from ..registry import BaseEvaluator


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def _token_overlap(a: str, b: str) -> float:
    tokens_a = {t for t in a.lower().split() if len(t) > 1}
    tokens_b = {t for t in b.lower().split() if len(t) > 1}
    if not tokens_a or not tokens_b:
        return 0.0
    return round(len(tokens_a & tokens_b) / len(tokens_a), 4)


def sentence_support(claim: str, contexts: list[str], threshold: float) -> bool:
    for context in contexts:
        if _token_overlap(claim, context) >= threshold:
            return True
    return False


class RAGEvaluator(BaseEvaluator):
    kind = "rag"

    def evaluate_scores(self, sample: EvaluationSample) -> list[MetricScore]:
        answer = sample.actual.get("answer", "")
        contexts = [str(c) for c in sample.actual.get("contexts", [])]
        claims = _sentences(answer)
        if self._judge is not None:
            return self._judged_scores(sample, claims, contexts)
        if not claims:
            return [
                MetricScore("faithfulness", 1.0),
                MetricScore("relevance", 0.0),
                MetricScore("groundedness", 1.0),
                MetricScore("hallucination_rate", 0.0),
            ]
        supported = [c for c in claims if sentence_support(c, contexts, self._config.token_overlap_threshold)]
        faithfulness = round(len(supported) / len(claims), 4)
        relevance = round(
            min(1.0, _token_overlap(answer, sample.query) / self._config.relevance_threshold),
            4,
        )
        return [
            MetricScore("faithfulness", faithfulness),
            MetricScore("relevance", relevance),
            MetricScore("groundedness", faithfulness),
            MetricScore("hallucination_rate", round(1.0 - faithfulness, 4)),
        ]

    def _judged_scores(self, sample: EvaluationSample, claims: list[str], contexts: list[str]) -> list[MetricScore]:
        judge = self._judge
        judge_relevance = _judge_call(judge, "relevance", sample.query, sample.actual.get("answer", ""))
        if not claims:
            return [
                MetricScore("faithfulness", 1.0),
                MetricScore("relevance", judge_relevance),
                MetricScore("groundedness", 1.0),
                MetricScore("hallucination_rate", 0.0),
            ]
        support_scores = []
        for claim in claims:
            support_scores.append(_judge_call(judge, "support", claim, contexts))
        faithfulness = round(sum(support_scores) / len(support_scores), 4)
        return [
            MetricScore("faithfulness", faithfulness),
            MetricScore("relevance", judge_relevance),
            MetricScore("groundedness", faithfulness),
            MetricScore("hallucination_rate", round(1.0 - faithfulness, 4)),
        ]


def _judge_call(judge: Any, method: str, *args: Any) -> float:
    fn = getattr(judge, method, None)
    if fn is None:
        return 0.5
    try:
        return float(fn(*args))
    except TypeError:
        return 0.5
