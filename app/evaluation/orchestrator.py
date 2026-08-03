from __future__ import annotations

import asyncio
import time
from abc import ABC
from typing import Any

from .benchmarks import BenchmarkRegistry, BenchmarkRunner
from .config import EvaluationConfig
from .dashboard import EvaluationDashboard
from .exceptions import ComparisonError, EvaluationError
from .gates import QualityGate
from .logging import EvaluationLogger
from .models import (
    BenchmarkResult,
    ComparisonResult,
    EvaluationResult,
    EvaluationSample,
)
from .registry import BaseEvaluator, EvaluatorRegistry
from .report import ReportGenerator
from .statistics import EvaluationMetricsTracker


class EvaluationObserver(ABC):  # noqa: B024
    def handle(self, event: str, data: dict[str, Any]) -> None:
        raise NotImplementedError


class EvaluationOrchestrator:
    def __init__(
        self,
        registry: EvaluatorRegistry | None = None,
        config: EvaluationConfig | None = None,
        logger: EvaluationLogger | None = None,
        tracker: EvaluationMetricsTracker | None = None,
        gate: QualityGate | None = None,
        report_generator: ReportGenerator | None = None,
        dashboard: EvaluationDashboard | None = None,
        benchmark_runner: BenchmarkRunner | None = None,
    ):
        self._registry = registry or EvaluatorRegistry.default()
        self._config = config or EvaluationConfig()
        self._logger = logger or EvaluationLogger()
        self._tracker = tracker or EvaluationMetricsTracker(self._config)
        self._gate = gate or QualityGate(self._config, self._logger)
        self._report_generator = report_generator or ReportGenerator(self._config)
        self._dashboard = dashboard or EvaluationDashboard(self._config, self._logger)
        self._benchmark_runner = benchmark_runner or BenchmarkRunner(
            registry=BenchmarkRegistry(),
            evaluator_registry=self._registry,
            config=self._config,
            logger=self._logger,
            tracker=self._tracker,
        )
        self._observers: list[EvaluationObserver] = []

    @property
    def registry(self) -> EvaluatorRegistry:
        return self._registry

    @property
    def benchmark_runner(self) -> BenchmarkRunner:
        return self._benchmark_runner

    @property
    def dashboard(self) -> EvaluationDashboard:
        return self._dashboard

    @property
    def tracker(self) -> EvaluationMetricsTracker:
        return self._tracker

    def attach(self, observer: EvaluationObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer: EvaluationObserver) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def _notify(self, event: str, **data: Any) -> None:
        for observer in self._observers:
            observer.handle(event, data)

    def create_evaluator(self, name: str, **kwargs: Any) -> BaseEvaluator:
        kwargs.setdefault("config", self._config)
        kwargs.setdefault("logger", self._logger)
        return self._registry.create(name, **kwargs)

    async def run_async(
        self,
        evaluator: str | BaseEvaluator,
        samples: list[EvaluationSample],
    ) -> EvaluationResult:
        start = time.perf_counter()
        instance = self.create_evaluator(evaluator) if isinstance(evaluator, str) else evaluator
        self._notify("run_started", evaluator=instance.name, samples=len(samples))
        result = await instance.evaluate_batch(samples)
        for metric in result.metrics:
            self._tracker.record(metric.name, metric.value, evaluator=instance.name)
        if not result.error:
            self._gate.check(result.metrics)
        self._dashboard.record(result)
        result.duration_ms = round((time.perf_counter() - start) * 1000, 4)
        self._notify(
            "run_completed",
            evaluator=instance.name,
            metrics=result.summary(),
            error=result.error,
        )
        return result

    def run(
        self,
        evaluator: str | BaseEvaluator,
        samples: list[EvaluationSample],
    ) -> EvaluationResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async(evaluator, samples))
        raise EvaluationError("run() cannot be used inside a running event loop; use run_async() instead")

    async def benchmark(
        self,
        dataset: str | Any,
        evaluators: list[str] | None = None,
        name: str | None = None,
        apply_gate: bool = True,
    ) -> BenchmarkResult:
        self._notify("benchmark_started", dataset=str(dataset))
        result = await self._benchmark_runner.run(dataset, evaluators=evaluators, name=name, apply_gate=apply_gate)
        self._dashboard.record(result)
        self._notify(
            "benchmark_completed",
            dataset=result.dataset_name,
            gate=result.gate,
            metrics=result.summary(),
        )
        return result

    async def compare(
        self,
        base: BenchmarkResult | dict[str, Any],
        current: BenchmarkResult | dict[str, Any],
    ) -> ComparisonResult:
        base_summary = _as_summary(base)
        current_summary = _as_summary(current)
        if not base_summary:
            raise ComparisonError("Base benchmark has no metrics to compare against")
        base_name = base.name if isinstance(base, BenchmarkResult) else base.get("name", "base")
        current_name = current.name if isinstance(current, BenchmarkResult) else current.get("name", "current")
        metrics: dict[str, dict[str, float]] = {}
        regressions: list[str] = []
        tolerance = self._config.regression_tolerance
        for metric, current_value in current_summary.items():
            base_value = base_summary.get(metric)
            if base_value is None:
                continue
            delta = round(current_value - base_value, 4)
            metrics[metric] = {
                "base": base_value,
                "current": current_value,
                "delta": delta,
            }
            if delta < -tolerance:
                regressions.append(metric)
        self._logger.log_event(
            "comparison",
            base=base_name,
            current=current_name,
            regressions=regressions,
        )
        return ComparisonResult(
            base_name=base_name,
            current_name=current_name,
            metrics=metrics,
            regressions=regressions,
            passed=not regressions,
        )

    async def generate_report(
        self,
        result: EvaluationResult | BenchmarkResult,
        formats: tuple[str, ...] | None = None,
        directory: str | None = None,
    ) -> dict[str, str]:
        return self._report_generator.generate(result, formats=formats, directory=directory)


def _as_summary(source: BenchmarkResult | dict[str, Any]) -> dict[str, float]:
    if isinstance(source, BenchmarkResult):
        return source.summary()
    summary = source.get("summary")
    if isinstance(summary, dict):
        return {k: float(v) for k, v in summary.items()}
    metrics = source.get("metrics")
    if isinstance(metrics, dict):
        return {k: float(v) for k, v in metrics.items()}
    return {}
