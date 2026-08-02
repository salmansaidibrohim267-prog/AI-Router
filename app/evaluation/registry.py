from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from .config import EvaluationConfig
from .exceptions import EvaluatorNotFoundError
from .logging import EvaluationLogger
from .models import EvaluationMetric, EvaluationResult, EvaluationSample, MetricScore
from .statistics import distribution


class BaseEvaluator(ABC):
    kind: str = "base"

    def __init__(
        self,
        config: EvaluationConfig | None = None,
        name: str | None = None,
        logger: EvaluationLogger | None = None,
        judge: Any | None = None,
    ):
        self.name = name or self.kind
        self._config = config or EvaluationConfig()
        self._logger = logger or EvaluationLogger()
        self._judge = judge

    @property
    def config(self) -> EvaluationConfig:
        return self._config

    @property
    def judge(self) -> Any | None:
        return self._judge

    def threshold_for(self, metric: str) -> tuple[float | None, float | None]:
        threshold = self._config.thresholds.get(metric, {})
        return threshold.get("min"), threshold.get("max")

    @abstractmethod
    def evaluate_scores(self, sample: EvaluationSample) -> list[MetricScore]:
        raise NotImplementedError

    async def evaluate_batch(self, samples: list[EvaluationSample]) -> EvaluationResult:
        start = time.perf_counter()
        scores_by_sample: list[list[MetricScore]] = []
        try:
            for sample in samples:
                scores_by_sample.append(self.evaluate_scores(sample))
            return self._finalize(samples, scores_by_sample, start)
        except Exception as exc:
            self._logger.log_event("evaluator_failed", evaluator=self.name, error=str(exc))
            return EvaluationResult(
                evaluator=self.name,
                samples=samples,
                error=str(exc),
                duration_ms=round((time.perf_counter() - start) * 1000, 4),
            )

    def _finalize(
        self,
        samples: list[EvaluationSample],
        scores_by_sample: list[list[MetricScore]],
        start: float,
    ) -> EvaluationResult:
        grouped: dict[str, list[float]] = {}
        for scores in scores_by_sample:
            for score in scores:
                grouped.setdefault(score.metric, []).append(score.value)
        metrics: list[EvaluationMetric] = []
        for name, values in grouped.items():
            threshold_min, threshold_max = self.threshold_for(name)
            value = statistics_mean(values)
            passed: bool | None = None
            if threshold_min is not None or threshold_max is not None:
                passed = (threshold_min is None or value >= threshold_min) and (
                    threshold_max is None or value <= threshold_max
                )
            metrics.append(
                EvaluationMetric(
                    name=name,
                    value=value,
                    samples=len(values),
                    distribution=distribution(values),
                    threshold_min=threshold_min,
                    threshold_max=threshold_max,
                    passed=passed,
                )
            )
        metrics.sort(key=lambda m: m.name)
        self._logger.log_event(
            "evaluator_complete",
            evaluator=self.name,
            samples=len(samples),
            metrics=len(metrics),
        )
        return EvaluationResult(
            evaluator=self.name,
            samples=samples,
            metrics=metrics,
            duration_ms=round((time.perf_counter() - start) * 1000, 4),
        )


def statistics_mean(values: list[float]) -> float:
    import statistics

    return round(statistics.fmean(values), 4)


class CompositeEvaluator(BaseEvaluator):
    kind = "composite"

    def __init__(
        self,
        config: EvaluationConfig | None = None,
        name: str = "composite",
        evaluators: list[BaseEvaluator] | None = None,
        logger: EvaluationLogger | None = None,
        judge: Any | None = None,
    ):
        super().__init__(config=config, name=name, logger=logger, judge=judge)
        self._evaluators = evaluators or []

    @property
    def evaluators(self) -> list[BaseEvaluator]:
        return self._evaluators

    def evaluate_scores(self, sample: EvaluationSample) -> list[MetricScore]:
        raise NotImplementedError

    async def evaluate_batch(self, samples: list[EvaluationSample]) -> EvaluationResult:
        start = time.perf_counter()
        metrics: list[EvaluationMetric] = []
        error = ""
        for evaluator in self._evaluators:
            result = await evaluator.evaluate_batch(samples)
            metrics.extend(result.metrics)
            if result.error:
                error = error or result.error
        return EvaluationResult(
            evaluator=self.name,
            samples=samples,
            metrics=metrics,
            error=error,
            duration_ms=round((time.perf_counter() - start) * 1000, 4),
        )


class EvaluatorRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, type[BaseEvaluator]] = {}

    def register(self, name: str, evaluator_cls: type[BaseEvaluator]) -> None:
        self._registry[name] = evaluator_cls

    def create(self, name: str, **kwargs: Any) -> BaseEvaluator:
        evaluator_cls = self._registry.get(name)
        if evaluator_cls is None:
            raise EvaluatorNotFoundError(name)
        return evaluator_cls(**kwargs)

    def contains(self, name: str) -> bool:
        return name in self._registry

    def names(self) -> list[str]:
        return sorted(self._registry.keys())

    @staticmethod
    def default() -> EvaluatorRegistry:
        from .evaluators.citation import CitationEvaluator
        from .evaluators.mcp_tools import MCPToolUsageEvaluator
        from .evaluators.memory import MemoryEvaluator
        from .evaluators.rag import RAGEvaluator
        from .evaluators.retrieval import RetrievalEvaluator

        registry = EvaluatorRegistry()
        registry.register("retrieval", RetrievalEvaluator)
        registry.register("rag", RAGEvaluator)
        registry.register("citation", CitationEvaluator)
        registry.register("memory", MemoryEvaluator)
        registry.register("mcp_tools", MCPToolUsageEvaluator)
        return registry
