"""Benchmark suite registry and runner."""

from __future__ import annotations

from typing import Any, Callable

from .base import BenchmarkReport, SuiteResult, Target
from .suites import (
    ConcurrencySuite,
    CpuSuite,
    FailoverSuite,
    LatencySuite,
    MemorySuite,
    RagQualitySuite,
    ThroughputSuite,
)

SUITE_BUILDERS: dict[str, Callable[..., Any]] = {
    "throughput": ThroughputSuite,
    "latency": LatencySuite,
    "memory": MemorySuite,
    "cpu": CpuSuite,
    "concurrency": ConcurrencySuite,
    "failover": FailoverSuite,
    "rag": RagQualitySuite,
}


class SuiteRunner:
    """Runs a selection of benchmark suites against a target."""

    def __init__(self, target: Target | None = None, target_name: str = "default") -> None:
        self.target = target
        self.target_name = target_name
        self.suites: dict[str, Any] = {}

    def register(self, name: str, suite: Any) -> None:
        self.suites[name] = suite

    def run(self, names: list[str] | None = None, target: Target | None = None) -> BenchmarkReport:
        target = target or self.target
        if target is None:
            raise ValueError("a target callable is required to run benchmarks")
        selected = list(names) if names else list(SUITE_BUILDERS)
        for name in selected:
            if name not in self.suites:
                if name not in SUITE_BUILDERS:
                    raise ValueError(f"unknown suite {name!r}")
                self.suites[name] = SUITE_BUILDERS[name]()
        report = BenchmarkReport(target_name=self.target_name)
        for name in selected:
            suite = self.suites[name]
            if isinstance(suite, RagQualitySuite):
                result = suite.run(target)  # type: ignore[arg-type]
            else:
                result = suite.run(target)
            if not isinstance(result, SuiteResult):
                raise TypeError(f"suite {name!r} returned {type(result).__name__}, expected SuiteResult")
            report.results.append(result)
        return report
