from __future__ import annotations

import json
import time

from .config import EvaluationConfig
from .exceptions import DatasetNotFoundError
from .logging import EvaluationLogger
from .models import (
    BenchmarkDataset,
    BenchmarkResult,
    DatasetType,
    EvaluationSample,
)
from .registry import EvaluatorRegistry
from .statistics import EvaluationMetricsTracker


def builtin_internal_dataset() -> BenchmarkDataset:
    return BenchmarkDataset(
        name="internal-smoke",
        dataset_type=DatasetType.INTERNAL,
        description="Built-in smoke samples covering all evaluator kinds.",
        samples=[
            EvaluationSample.retrieval(
                "ret-1",
                "gold price trend",
                ["d1", "d2"],
                [
                    {"id": "d1", "score": 0.9, "content": "gold prices rising"},
                    {"id": "d3", "score": 0.8, "content": "silver prices falling"},
                    {"id": "d2", "score": 0.7, "content": "gold demand strong"},
                ],
            ),
            EvaluationSample.rag(
                "rag-1",
                "what drives gold prices?",
                ["Gold prices rise when demand increases."],
                "Gold prices rise when demand increases. Silver is cheaper.",
            ),
            EvaluationSample.citation(
                "cit-1",
                "Gold hit a record high in 2026 [1].",
                [{"source_id": "s1", "index": 1, "claim": "Gold hit a record high in 2026."}],
                [{"id": "s1", "content": "Gold hit a record high in 2026 according to market data."}],
            ),
            EvaluationSample.memory(
                "mem-1",
                "user preference",
                ["m1"],
                [{"id": "m1", "importance": 0.9, "content": "user prefers gold"}],
            ),
            EvaluationSample.mcp_tools(
                "mcp-1",
                ["search_knowledge", "memory_save"],
                [
                    {"tool": "search_knowledge", "success": True, "arguments": {"query": "gold"}},
                    {"tool": "memory_save", "success": True, "arguments": {"content": "note"}},
                ],
            ),
        ],
    )


class BenchmarkRegistry:
    def __init__(self) -> None:
        self._datasets: dict[str, BenchmarkDataset] = {}
        self.register(builtin_internal_dataset())

    def register(self, dataset: BenchmarkDataset) -> None:
        self._datasets[dataset.name] = dataset

    def get(self, name: str) -> BenchmarkDataset:
        dataset = self._datasets.get(name)
        if dataset is None:
            raise DatasetNotFoundError(name)
        return dataset

    def contains(self, name: str) -> bool:
        return name in self._datasets

    def list(self) -> list[BenchmarkDataset]:
        return list(self._datasets.values())

    def names(self) -> list[str]:
        return sorted(self._datasets.keys())

    def load_json(
        self, path: str, name: str | None = None, dataset_type: DatasetType = DatasetType.CUSTOM
    ) -> BenchmarkDataset:  # noqa: E501
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        dataset = BenchmarkDataset.from_dict(payload)
        if name:
            dataset.name = name
        dataset.dataset_type = dataset_type
        self.register(dataset)
        return dataset


class BenchmarkRunner:
    def __init__(
        self,
        registry: BenchmarkRegistry | None = None,
        evaluator_registry: EvaluatorRegistry | None = None,
        config: EvaluationConfig | None = None,
        logger: EvaluationLogger | None = None,
        tracker: EvaluationMetricsTracker | None = None,
    ):
        self._registry = registry or BenchmarkRegistry()
        self._evaluator_registry = evaluator_registry or EvaluatorRegistry.default()
        self._config = config or EvaluationConfig()
        self._logger = logger or EvaluationLogger()
        self._tracker = tracker or EvaluationMetricsTracker(self._config)

    @property
    def datasets(self) -> BenchmarkRegistry:
        return self._registry

    async def run(
        self,
        dataset: str | BenchmarkDataset,
        evaluators: list[str] | None = None,
        name: str | None = None,
        apply_gate: bool = True,
    ) -> BenchmarkResult:
        start = time.perf_counter()
        if isinstance(dataset, str):
            dataset = self._registry.get(dataset)
        evaluator_names = evaluators or list(self._config.benchmark_default_evaluators)
        from .gates import QualityGate

        results = []
        error = ""
        for evaluator_name in evaluator_names:
            try:
                evaluator = self._evaluator_registry.create(evaluator_name, config=self._config, logger=self._logger)
                result = await evaluator.evaluate_batch(dataset.samples)
                results.append(result)
                for metric in result.metrics:
                    self._tracker.record(metric.name, metric.value, evaluator=evaluator_name)
                if result.error:
                    error = error or result.error
            except Exception as exc:
                self._logger.log_event("benchmark_evaluator_error", evaluator=evaluator_name, error=str(exc))
                error = error or str(exc)
        gate_result = None
        if apply_gate and self._config.gate_enabled:
            from .models import EvaluationMetric

            all_metrics: list[EvaluationMetric] = []
            for result in results:
                all_metrics.extend(result.metrics)
            gate_result = QualityGate(self._config, self._logger).check(all_metrics)
        benchmark_result = BenchmarkResult(
            name=name or f"{dataset.name}-run",
            dataset_name=dataset.name,
            dataset_type=dataset.dataset_type.value,
            results=results,
            gate=gate_result.to_dict() if gate_result else None,
            duration_ms=round((time.perf_counter() - start) * 1000, 4),
        )
        self._logger.log_event(
            "benchmark_complete",
            dataset=dataset.name,
            evaluators=evaluator_names,
            gate=gate_result.passed if gate_result else None,
            error=error,
        )
        return benchmark_result
