from __future__ import annotations

from typing import Any

from .benchmarks import (
    BenchmarkRegistry,
    BenchmarkRunner,
    builtin_internal_dataset,
)
from .config import DEFAULT_THRESHOLDS, EvaluationConfig
from .dashboard import EvaluationDashboard
from .evaluators import (
    CitationEvaluator,
    MCPToolUsageEvaluator,
    MemoryEvaluator,
    RAGEvaluator,
    RetrievalEvaluator,
)
from .exceptions import (
    BenchmarkRunError,
    ComparisonError,
    DatasetNotFoundError,
    EvaluationError,
    EvaluatorNotFoundError,
    QualityGateError,
    ReportGenerationError,
)
from .gates import QualityGate
from .logging import EvaluationLogger
from .models import (
    BenchmarkDataset,
    BenchmarkResult,
    ComparisonResult,
    DatasetType,
    EvaluationMetric,
    EvaluationResult,
    EvaluationSample,
    EvaluatorKind,
    GateCheck,
    GateResult,
    MetricScore,
    RetrievedItem,
)
from .orchestrator import EvaluationObserver, EvaluationOrchestrator
from .registry import BaseEvaluator, CompositeEvaluator, EvaluatorRegistry
from .report import ReportGenerator
from .statistics import EvaluationMetricsTracker, distribution

__all__ = [
    "EvaluationConfig",
    "EvaluationLogger",
    "EvaluationMetricsTracker",
    "EvaluationOrchestrator",
    "EvaluationObserver",
    "EvaluatorRegistry",
    "EvaluatorNotFoundError",
    "BaseEvaluator",
    "CompositeEvaluator",
    "RetrievalEvaluator",
    "RAGEvaluator",
    "CitationEvaluator",
    "MemoryEvaluator",
    "MCPToolUsageEvaluator",
    "QualityGate",
    "QualityGateError",
    "ReportGenerator",
    "ReportGenerationError",
    "EvaluationDashboard",
    "BenchmarkRegistry",
    "BenchmarkRunner",
    "BenchmarkDataset",
    "builtin_internal_dataset",
    "DatasetNotFoundError",
    "BenchmarkRunError",
    "ComparisonError",
    "EvaluationError",
    "EvaluationSample",
    "EvaluationResult",
    "EvaluationMetric",
    "MetricScore",
    "RetrievedItem",
    "BenchmarkResult",
    "ComparisonResult",
    "GateResult",
    "GateCheck",
    "DatasetType",
    "EvaluatorKind",
    "DEFAULT_THRESHOLDS",
    "distribution",
    "create_evaluator",
    "create_orchestrator",
    "create_benchmark_dataset",
    "load_benchmark_dataset",
]


def create_evaluator(name: str, config: EvaluationConfig | None = None, **kwargs: Any) -> BaseEvaluator:
    registry = EvaluatorRegistry.default()
    return registry.create(name, config=config, **kwargs)


def create_orchestrator(
    config: EvaluationConfig | None = None,
    registry: EvaluatorRegistry | None = None,
    logger: EvaluationLogger | None = None,
    tracker: EvaluationMetricsTracker | None = None,
    gate: QualityGate | None = None,
    report_generator: ReportGenerator | None = None,
    dashboard: EvaluationDashboard | None = None,
    benchmark_runner: BenchmarkRunner | None = None,
) -> EvaluationOrchestrator:
    return EvaluationOrchestrator(
        registry=registry,
        config=config,
        logger=logger,
        tracker=tracker,
        gate=gate,
        report_generator=report_generator,
        dashboard=dashboard,
        benchmark_runner=benchmark_runner,
    )


def create_benchmark_dataset(
    name: str,
    samples: list[EvaluationSample],
    dataset_type: DatasetType = DatasetType.CUSTOM,
    description: str = "",
    version: str = "1.0.0",
) -> BenchmarkDataset:
    return BenchmarkDataset(
        name=name,
        dataset_type=dataset_type,
        samples=samples,
        description=description,
        version=version,
    )


def load_benchmark_dataset(
    path: str,
    name: str | None = None,
    dataset_type: DatasetType = DatasetType.CUSTOM,
    registry: BenchmarkRegistry | None = None,
) -> BenchmarkDataset:
    registry = registry or BenchmarkRegistry()
    return registry.load_json(path, name=name, dataset_type=dataset_type)
