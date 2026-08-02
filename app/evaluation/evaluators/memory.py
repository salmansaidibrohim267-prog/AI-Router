from __future__ import annotations

from typing import Any

from ..models import EvaluationSample, MetricScore
from ..registry import BaseEvaluator


class MemoryEvaluator(BaseEvaluator):
    kind = "memory"

    def evaluate_scores(self, sample: EvaluationSample) -> list[MetricScore]:
        relevant_ids = {str(r) for r in sample.expected.get("relevant_ids", [])}
        retrieved = sample.actual.get("retrieved", [])
        retrieved_ids = [str(_item_id(r)) for r in retrieved]
        retrieved_set = set(retrieved_ids)

        hit = 1.0 if (relevant_ids & retrieved_set) else 0.0
        precision = (
            round(len(relevant_ids & retrieved_set) / len(retrieved_set), 4)
            if retrieved_set
            else 0.0
        )
        recall = (
            round(len(relevant_ids & retrieved_set) / len(relevant_ids), 4)
            if relevant_ids
            else 0.0
        )
        scores = [
            MetricScore("memory_hit_rate", hit),
            MetricScore("memory_precision", precision),
            MetricScore("memory_recall", recall),
        ]
        relevance_values = [
            float(_item_score(r)) for r in retrieved if _item_score(r) is not None
        ]
        relevance = (
            round(sum(relevance_values) / len(relevance_values), 4)
            if relevance_values
            else 0.0
        )
        scores.append(MetricScore("memory_relevance", relevance))
        return scores


def _item_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("id", item.get("item_id", "")))
    return str(getattr(item, "id", getattr(item, "item_id", "")))


def _item_score(item: Any) -> float | None:
    if isinstance(item, dict):
        value = item.get("importance", item.get("score", item.get("confidence")))
    else:
        value = getattr(item, "importance", getattr(item, "score", None))
        if value is None:
            value = getattr(item, "confidence", None)
    if value is None:
        return None
    return float(value)
