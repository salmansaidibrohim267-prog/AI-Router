"""Base types for benchmark suites."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable

Target = Callable[[], Any]
"""A callable benchmark target (pure or async-aware wrapper)."""


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 4) if values else 0.0


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(len(ordered) * p)
    return round(ordered[min(index, len(ordered) - 1)], 4)


@dataclass
class SuiteResult:
    """Outcome of a single suite run."""

    name: str
    passed: bool = True
    metrics: dict[str, float] = field(default_factory=dict)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "metrics": dict(self.metrics),
            "detail": self.detail,
        }


@dataclass
class BenchmarkReport:
    """Aggregated report over several suites."""

    target_name: str
    timestamp: float = field(default_factory=time.time)
    results: list[SuiteResult] = field(default_factory=list)

    def overall_passed(self) -> bool:
        return bool(self.results) and all(r.passed for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_name": self.target_name,
            "timestamp": self.timestamp,
            "overall_passed": self.overall_passed(),
            "results": [r.to_dict() for r in self.results],
        }
