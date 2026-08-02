from __future__ import annotations

import time
from typing import Any

from .config import EvaluationConfig
from .logging import EvaluationLogger
from .models import BenchmarkResult, EvaluationResult


class EvaluationDashboard:
    def __init__(
        self,
        config: EvaluationConfig | None = None,
        logger: EvaluationLogger | None = None,
    ):
        self._config = config or EvaluationConfig()
        self._logger = logger or EvaluationLogger()
        self._history: list[dict[str, Any]] = []

    @property
    def history(self) -> list[dict[str, Any]]:
        return self._history

    def record(self, result: EvaluationResult | BenchmarkResult) -> None:
        snapshot = {
            "recorded_at": time.time(),
            "name": result.name if isinstance(result, BenchmarkResult) else result.evaluator,
            "summary": result.summary() if hasattr(result, "summary") else {},
            "duration_ms": result.duration_ms,
        }
        if isinstance(result, BenchmarkResult):
            snapshot["dataset"] = result.dataset_name
            snapshot["gate"] = result.gate
        self._history.append(snapshot)
        self._logger.log_event("dashboard_recorded", name=snapshot["name"])

    def snapshot(self) -> dict[str, Any]:
        if not self._history:
            return {"records": 0, "metrics": {}, "latest": None}
        latest = self._history[-1]
        merged: dict[str, float] = {}
        for entry in self._history:
            for metric, value in entry["summary"].items():
                merged[metric] = value
        return {
            "records": len(self._history),
            "metrics": merged,
            "latest": latest,
            "updated_at": time.time(),
        }

    def series(self, metric: str) -> list[float]:
        return [
            entry["summary"][metric]
            for entry in self._history
            if metric in entry["summary"]
        ]

    def summary(self) -> dict[str, Any]:
        return self.snapshot()
