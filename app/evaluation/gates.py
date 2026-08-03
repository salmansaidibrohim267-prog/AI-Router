from __future__ import annotations

from .config import EvaluationConfig
from .logging import EvaluationLogger
from .models import EvaluationMetric, GateCheck, GateResult


class QualityGate:
    def __init__(
        self,
        config: EvaluationConfig | None = None,
        logger: EvaluationLogger | None = None,
    ):
        self._config = config or EvaluationConfig()
        self._logger = logger or EvaluationLogger()

    @property
    def config(self) -> EvaluationConfig:
        return self._config

    def check(self, metrics: list[EvaluationMetric]) -> GateResult:
        checks: list[GateCheck] = []
        for metric in metrics:
            threshold_min, threshold_max = self._thresholds(metric.name)
            if threshold_min is None and threshold_max is None:
                continue
            passed = (threshold_min is None or metric.value >= threshold_min) and (
                threshold_max is None or metric.value <= threshold_max
            )
            checks.append(
                GateCheck(
                    metric=metric.name,
                    value=metric.value,
                    threshold_min=threshold_min,
                    threshold_max=threshold_max,
                    passed=passed,
                )
            )
        result = GateResult(passed=all(c.passed for c in checks), checks=checks)
        self._logger.log_event(
            "gate_check",
            passed=result.passed,
            checked=len(checks),
            failed=[c.metric for c in checks if not c.passed],
        )
        return result

    def _thresholds(self, metric: str) -> tuple[float | None, float | None]:
        threshold = self._config.thresholds.get(metric, {})
        return threshold.get("min"), threshold.get("max")
