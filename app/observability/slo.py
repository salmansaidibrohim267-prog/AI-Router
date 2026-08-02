"""SLO / SLI tracking with error budgets and burn rates.

``SloDefinition`` couples an indicator (success ratio) with a target over a
window. ``SliCollector`` aggregates request outcomes (good/bad) per SLO key
and computes the error budget remaining and burn rate for alerting.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .config import ObservabilityConfig
from .exceptions import SloError


@dataclass
class SloDefinition:
    """A service-level objective definition."""

    name: str
    target: float = 99.9
    window_seconds: int = 2592000
    description: str = ""

    def __post_init__(self) -> None:
        if not 0.0 < self.target <= 100.0:
            raise SloError(f"SLO target must be in (0, 100], got {self.target}")
        if self.window_seconds <= 0:
            raise SloError("SLO window must be positive")
        if not self.name:
            raise SloError("SLO name must not be empty")

    @property
    def error_budget_pct(self) -> float:
        """Percentage of events allowed to fail within the window."""
        return round(100.0 - self.target, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "window_seconds": self.window_seconds,
            "description": self.description,
            "error_budget_pct": self.error_budget_pct,
        }


@dataclass
class SliSnapshot:
    """Current SLI state for a single SLO."""

    slo: SloDefinition
    good: int = 0
    bad: int = 0
    window_start: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)

    @property
    def total(self) -> int:
        return self.good + self.bad

    @property
    def success_ratio(self) -> float:
        if self.total == 0:
            return 100.0
        return round(self.good / self.total * 100.0, 4)

    @property
    def error_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.bad / self.total * 100.0, 4)

    def error_budget_remaining(self) -> float:
        """Remaining budget as a percentage of the total allowed failures."""
        allowed = self.slo.error_budget_pct / 100.0 * self.total
        if allowed <= 0:
            return 100.0 if self.bad == 0 else 0.0
        return round(max(0.0, 1.0 - self.bad / allowed) * 100.0, 2)

    def burn_rate(self) -> float:
        """Actual failure rate relative to the allowed failure rate."""
        allowed = self.slo.error_budget_pct / 100.0
        if allowed <= 0:
            return 0.0
        actual = self.bad / self.total if self.total else 0.0
        return round(actual / allowed, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "slo": self.slo.to_dict(),
            "good": self.good,
            "bad": self.bad,
            "total": self.total,
            "success_ratio": self.success_ratio,
            "error_rate": self.error_rate,
            "error_budget_remaining_pct": self.error_budget_remaining(),
            "burn_rate": self.burn_rate(),
            "window_start": self.window_start,
            "last_updated": self.last_updated,
        }


class SliCollector:
    """Aggregates good/bad outcomes per SLO with rolling windows."""

    def __init__(self, config: ObservabilityConfig | None = None) -> None:
        self.config = config if config is not None else ObservabilityConfig()
        self._definitions: dict[str, SloDefinition] = {}
        self._snapshots: dict[str, SliSnapshot] = {}
        self._history: dict[str, list[tuple[float, int]]] = {}
        self._lock = threading.RLock()

    def define(self, slo: SloDefinition) -> None:
        if not slo.name:
            raise SloError("SLO name must not be empty")
        self._definitions[slo.name] = slo
        if slo.name not in self._snapshots:
            self._snapshots[slo.name] = SliSnapshot(slo)

    def define_many(self, slos: list[SloDefinition]) -> None:
        for slo in slos:
            self.define(slo)

    def record_good(self, name: str, amount: int = 1) -> None:
        self._record(name, good=amount)

    def record_bad(self, name: str, amount: int = 1) -> None:
        self._record(name, bad=amount)

    def record_outcome(self, name: str, good: bool, amount: int = 1) -> None:
        if good:
            self.record_good(name, amount)
        else:
            self.record_bad(name, amount)

    def _record(self, name: str, good: int = 0, bad: int = 0) -> None:
        with self._lock:
            if name not in self._definitions:
                slo = SloDefinition(name, self.config.default_slo, self.config.window_seconds)
                self._definitions[name] = slo
                self._snapshots[name] = SliSnapshot(slo)
            snapshot = self._snapshots[name]
            self._roll_window(snapshot)
            snapshot.good += good
            snapshot.bad += bad
            snapshot.last_updated = time.time()
            history = self._history.setdefault(name, [])
            history.append((time.time(), good - bad))
            if len(history) > 5000:
                self._history[name] = history[-5000:]

    def _roll_window(self, snapshot: SliSnapshot) -> None:
        now = time.time()
        if now - snapshot.window_start >= snapshot.slo.window_seconds:
            snapshot.good = 0
            snapshot.bad = 0
            snapshot.window_start = now

    def snapshot(self, name: str) -> SliSnapshot:
        with self._lock:
            if name not in self._snapshots:
                raise SloError(f"unknown SLO {name!r}")
            self._roll_window(self._snapshots[name])
            return self._snapshots[name]

    def snapshots(self) -> list[SliSnapshot]:
        with self._lock:
            return [self.snapshot(name) for name in self._definitions]

    def error_budget_remaining(self, name: str) -> float:
        return self.snapshot(name).error_budget_remaining()

    def burn_rate(self, name: str) -> float:
        return self.snapshot(name).burn_rate()

    def definitions(self) -> list[SloDefinition]:
        with self._lock:
            return list(self._definitions.values())

    def status(self) -> dict[str, Any]:
        return {
            "slo_count": len(self._definitions),
            "snapshots": [s.to_dict() for s in self.snapshots()],
        }
