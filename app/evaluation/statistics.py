from __future__ import annotations

import statistics
import time
from typing import Any


def distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    n = len(ordered)
    mean = statistics.fmean(ordered)
    variance = statistics.pvariance(ordered) if n > 1 else 0.0
    if n % 2 == 0:
        p50 = (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    else:
        p50 = ordered[n // 2]
    return {
        "mean": round(mean, 4),
        "std": round(variance**0.5, 4),
        "min": round(ordered[0], 4),
        "max": round(ordered[-1], 4),
        "p50": round(p50, 4),
        "p90": round(ordered[min(n - 1, int(n * 0.9))], 4),
        "p95": round(ordered[min(n - 1, int(n * 0.95))], 4),
    }


class EvaluationMetricsTracker:
    def __init__(self, config: Any | None = None):
        from .config import EvaluationConfig

        self._config = config or EvaluationConfig()
        self._enabled = self._config.track_metrics
        self._scores: dict[str, list[float]] = {}
        self._by_evaluator: dict[str, list[float]] = {}
        self._started_at = time.time()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record(self, metric: str, value: float, evaluator: str = "") -> None:
        if not self._enabled:
            return
        self._scores.setdefault(metric, []).append(value)
        if evaluator:
            self._by_evaluator.setdefault(f"{evaluator}.{metric}", []).append(value)

    def aggregate(self, metric: str) -> dict[str, float]:
        return distribution(self._scores.get(metric, []))

    def by_evaluator(self) -> dict[str, float]:
        return {key: distribution(values)["mean"] for key, values in self._by_evaluator.items()}

    def summary(self) -> dict[str, dict[str, float]]:
        return {metric: distribution(v) for metric, v in self._scores.items()}

    def reset(self) -> None:
        self._scores = {}
        self._by_evaluator = {}

    def uptime(self) -> float:
        return round(time.time() - self._started_at, 4)
