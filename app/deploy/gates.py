"""Quality gates and release readiness checks.

Gates are declarative threshold checks (lint, formatting, typing, tests,
coverage, latency, error rate, security scan). ``QualityGateRunner`` runs a
chain and aggregates results; any failed gate blocks the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .config import DeployConfig
from .exceptions import QualityGateError

GateCheck = Callable[[], dict[str, Any]]
"""check() -> {"passed": bool, "value": Any, "detail": str}"""


@dataclass
class QualityGate:
    """A single gate with a threshold."""

    name: str
    kind: str = "threshold"
    threshold: float = 0.0
    operator: str = ">="
    description: str = ""

    def evaluate(self, value: float) -> bool:
        if self.operator == ">=":
            return value >= self.threshold
        if self.operator == "<=":
            return value <= self.threshold
        if self.operator == ">":
            return value > self.threshold
        if self.operator == "<":
            return value < self.threshold
        if self.operator == "==":
            return value == self.threshold
        raise QualityGateError(f"unknown operator {self.operator!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "threshold": self.threshold,
            "operator": self.operator,
            "description": self.description,
        }


@dataclass
class GateResult:
    """Outcome of evaluating one gate."""

    gate: QualityGate
    passed: bool
    value: float
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate.name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.gate.threshold,
            "operator": self.gate.operator,
            "detail": self.detail,
        }


class QualityGateRunner:
    """Runs a chain of quality gates and aggregates the outcome."""

    def __init__(self, config: DeployConfig | None = None) -> None:
        self.config = config if config is not None else DeployConfig()
        self._checks: dict[str, GateCheck] = {}

    def register(self, name: str, check: GateCheck) -> None:
        self._checks[name] = check

    def default_gates(self) -> list[QualityGate]:
        return [
            QualityGate("coverage", "threshold", self.config.min_coverage, ">=", "Test coverage"),
            QualityGate("p95_latency_ms", "threshold", self.config.max_latency_ms, "<=", "p95 latency"),
            QualityGate("error_rate", "threshold", self.config.max_error_rate, "<=", "Error rate %"),
            QualityGate("tests_passed", "threshold", 1, "==", "All tests green"),
        ]

    def run(self, gates: list[QualityGate] | None = None) -> list[GateResult]:
        gates = gates if gates is not None else self.default_gates()
        results: list[GateResult] = []
        for gate in gates:
            check = self._checks.get(gate.name)
            if check is None:
                results.append(GateResult(gate, False, 0.0, "no check registered"))
                continue
            outcome = check()
            value = float(outcome.get("value", 0.0))
            passed = bool(outcome.get("passed", gate.evaluate(value)))
            results.append(GateResult(gate, passed, value, outcome.get("detail", "")))
        return results

    def run_and_raise(self, gates: list[QualityGate] | None = None) -> list[GateResult]:
        results = self.run(gates)
        failed = [r for r in results if not r.passed]
        if failed:
            names = ", ".join(r.gate.name for r in failed)
            raise QualityGateError(f"quality gates failed: {names}")
        return results

    def summary(self, results: list[GateResult]) -> dict[str, Any]:
        return {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [r.to_dict() for r in results],
        }
