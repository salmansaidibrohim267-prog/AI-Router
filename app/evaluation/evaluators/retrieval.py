from __future__ import annotations

from typing import Any

from ..models import EvaluationSample, MetricScore
from ..registry import BaseEvaluator


def recall_at_k(relevant_ids: list[str], ranked_ids: list[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top = set(ranked_ids[:k])
    hits = sum(1 for r in relevant_ids if r in top)
    return round(hits / len(relevant_ids), 4)


def precision_at_k(relevant_ids: list[str], ranked_ids: list[str], k: int) -> float:
    top = ranked_ids[:k]
    if not top:
        return 0.0
    relevant = set(relevant_ids)
    hits = sum(1 for r in top if r in relevant)
    return round(hits / len(top), 4)


def reciprocal_rank(relevant_ids: list[str], ranked_ids: list[str]) -> float:
    relevant = set(relevant_ids)
    for i, doc_id in enumerate(ranked_ids):
        if doc_id in relevant:
            return round(1.0 / (i + 1), 4)
    return 0.0


def average_precision(relevant_ids: list[str], ranked_ids: list[str]) -> float:
    relevant = set(relevant_ids)
    hits = 0
    precision_sum = 0.0
    for i, doc_id in enumerate(ranked_ids):
        if doc_id in relevant:
            hits += 1
            precision_sum += hits / (i + 1)
    if not relevant:
        return 0.0
    return round(precision_sum / len(relevant), 4)


def ndcg_at_k(relevant_ids: list[str], ranked_ids: list[str], k: int) -> float:
    relevant = set(relevant_ids)
    top = ranked_ids[:k]
    dcg = 0.0
    for i, doc_id in enumerate(top):
        if doc_id in relevant:
            dcg += 1.0 / (i + 2)
    ideal = sorted(
        [1.0 / (i + 2) for i in range(min(k, len(relevant)))],
        reverse=True,
    )
    idcg = sum(ideal)
    if idcg == 0:
        return 0.0
    return round(dcg / idcg, 4)


class RetrievalEvaluator(BaseEvaluator):
    kind = "retrieval"

    def evaluate_scores(self, sample: EvaluationSample) -> list[MetricScore]:
        relevant_ids = [str(r) for r in sample.expected.get("relevant_ids", [])]
        results = sample.actual.get("results", [])
        ranked_ids: list[str] = []
        for i, item in enumerate(results):
            doc_id = item.id if not isinstance(item, dict) else item.get("id", "")
            ranked_ids.append(str(doc_id))
        k = self._config.recall_at_k
        scores = [
            MetricScore("recall_at_k", recall_at_k(relevant_ids, ranked_ids, k)),
            MetricScore(
                "precision_at_k",
                precision_at_k(relevant_ids, ranked_ids, self._config.precision_at_k),
            ),
            MetricScore("mrr", reciprocal_rank(relevant_ids, ranked_ids)),
            MetricScore("map", average_precision(relevant_ids, ranked_ids)),
            MetricScore("ndcg_at_k", ndcg_at_k(relevant_ids, ranked_ids, self._config.ndcg_k)),
        ]
        return scores
