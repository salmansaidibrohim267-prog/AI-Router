from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field

DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "recall_at_k": {"min": 0.4},
    "precision_at_k": {"min": 0.3},
    "mrr": {"min": 0.5},
    "map": {"min": 0.4},
    "ndcg_at_k": {"min": 0.5},
    "faithfulness": {"min": 0.7},
    "relevance": {"min": 0.5},
    "groundedness": {"min": 0.7},
    "hallucination_rate": {"max": 0.3},
    "citation_precision": {"min": 0.6},
    "citation_recall": {"min": 0.5},
    "citation_verifiability": {"min": 0.8},
    "citation_density": {"min": 0.0},
    "memory_hit_rate": {"min": 0.5},
    "memory_precision": {"min": 0.4},
    "memory_recall": {"min": 0.4},
    "memory_relevance": {"min": 0.3},
    "tool_success_rate": {"min": 0.8},
    "tool_error_rate": {"max": 0.2},
    "tool_completeness": {"min": 0.7},
    "tool_precision": {"min": 0.5},
    "tool_correctness": {"min": 0.5},
}


@dataclass
class EvaluationConfig:
    recall_at_k: int = 5
    precision_at_k: int = 5
    ndcg_k: int = 5
    token_overlap_threshold: float = 0.4
    relevance_threshold: float = 0.5
    gate_enabled: bool = True
    regression_tolerance: float = 0.05
    report_dir: str = "reports/evaluation"
    report_formats: tuple[str, ...] = ("json", "markdown", "html", "csv")
    benchmark_default_evaluators: tuple[str, ...] = (
        "retrieval",
        "rag",
        "citation",
        "memory",
        "mcp_tools",
    )
    log_events: bool = True
    track_metrics: bool = True
    thresholds: dict[str, dict[str, float]] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_THRESHOLDS)
    )

    def set_threshold(self, metric: str, min: float | None = None, max: float | None = None) -> None:
        self.thresholds[metric] = {
            "min": min if min is not None else self.thresholds.get(metric, {}).get("min"),
            "max": max if max is not None else self.thresholds.get(metric, {}).get("max"),
        }

    @classmethod
    def from_env(cls) -> EvaluationConfig:
        return cls(
            recall_at_k=int(os.getenv("EVAL_RECALL_AT_K", "5")),
            precision_at_k=int(os.getenv("EVAL_PRECISION_AT_K", "5")),
            ndcg_k=int(os.getenv("EVAL_NDCG_K", "5")),
            token_overlap_threshold=float(os.getenv("EVAL_TOKEN_OVERLAP_THRESHOLD", "0.4")),
            relevance_threshold=float(os.getenv("EVAL_RELEVANCE_THRESHOLD", "0.5")),
            gate_enabled=os.getenv("EVAL_GATE_ENABLED", "1") == "1",
            regression_tolerance=float(os.getenv("EVAL_REGRESSION_TOLERANCE", "0.05")),
            report_dir=os.getenv("EVAL_REPORT_DIR", "reports/evaluation"),
            report_formats=tuple(
                os.getenv("EVAL_REPORT_FORMATS", "json,markdown,html,csv").split(",")
            ),
            log_events=os.getenv("EVAL_LOG_EVENTS", "1") == "1",
            track_metrics=os.getenv("EVAL_TRACK_METRICS", "1") == "1",
        )
