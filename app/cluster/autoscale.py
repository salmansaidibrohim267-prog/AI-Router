"""Autoscaling based on CPU, memory, queue length, request rate and token
throughput (Strategy pattern via pluggable collectors).

Collectors sample a metric; the Autoscaler combines the samples, computes a
desired replica count within ``[min_replicas, max_replicas]``, applies
cooldown and hysteresis, and notifies observers of scale decisions.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .config import ClusterConfig
from .exceptions import AutoscaleError
from .logging import ClusterLogger
from .metrics import ClusterMetricsTracker
from .models import AutoscaleDecision

ScaleObserver = Callable[[AutoscaleDecision], Awaitable[None]]


class MetricCollector:
    """Base collector: samples a metric, keeps a rolling window."""

    name = "base"
    default_threshold = 100.0

    def __init__(self, source: Callable[[], float] | None = None, window: int = 60) -> None:
        self._source = source or (lambda: 0.0)
        self._window: list[float] = []
        self._max_window = window

    def record(self, value: float) -> None:
        self._window.append(float(value))
        if len(self._window) > self._max_window:
            del self._window[: len(self._window) - self._max_window]

    def sample(self) -> float:
        value = self._source()
        self.record(value)
        if not self._window:
            return 0.0
        return sum(self._window) / len(self._window)

    def last(self) -> float:
        if not self._window:
            return 0.0
        return self._window[-1]

    def reset(self) -> None:
        self._window.clear()


class CpuCollector(MetricCollector):
    name = "cpu"
    default_threshold = 70.0


class MemoryCollector(MetricCollector):
    name = "memory"
    default_threshold = 70.0


class QueueLengthCollector(MetricCollector):
    name = "queue_length"
    default_threshold = 100.0


class RequestRateCollector(MetricCollector):
    name = "request_rate"
    default_threshold = 1000.0


class TokenThroughputCollector(MetricCollector):
    name = "token_throughput"
    default_threshold = 100000.0


_COLLECTOR_TYPES: dict[str, type[MetricCollector]] = {
    "cpu": CpuCollector,
    "memory": MemoryCollector,
    "queue_length": QueueLengthCollector,
    "request_rate": RequestRateCollector,
    "token_throughput": TokenThroughputCollector,
}


class Autoscaler:
    """Evaluates cluster load and recommends replica counts."""

    def __init__(
        self,
        config: ClusterConfig | None = None,
        logger: ClusterLogger | None = None,
        metrics: ClusterMetricsTracker | None = None,
        collectors: dict[str, MetricCollector] | None = None,
        apply_scale: Callable[[str, int], Any] | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.logger = logger or ClusterLogger(self.config)
        self.metrics = metrics or ClusterMetricsTracker(self.config)
        self.collectors = collectors or {
            name: kind() for name, kind in _COLLECTOR_TYPES.items()
        }
        self._apply_scale = apply_scale
        self._observers: list[ScaleObserver] = []
        self._decisions: list[AutoscaleDecision] = []
        self._loop_task: asyncio.Task | None = None
        self._running = False
        self._component = "cluster"
        self._last_eval = 0.0
        self._replicas = self.config.min_replicas

    def set_component(self, component: str) -> None:
        self._component = component

    def set_replicas(self, replicas: int) -> None:
        self._replicas = max(1, int(replicas))

    @property
    def replicas(self) -> int:
        return self._replicas

    # -- lifecycle -------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._loop(), name="cluster-autoscale")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.evaluate()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - autoscaler must survive
                self.logger.log_event("autoscale_error", error=str(exc))
            await asyncio.sleep(self.config.autoscale_interval)

    # -- observers -----------------------------------------------------------------

    def subscribe(self, observer: ScaleObserver) -> Callable[[], None]:
        self._observers.append(observer)

        def unsubscribe() -> None:
            if observer in self._observers:
                self._observers.remove(observer)

        return unsubscribe

    # -- evaluation ------------------------------------------------------------------

    def record(self, metric: str, value: float) -> None:
        collector = self.collectors.get(metric)
        if collector is None:
            raise AutoscaleError(f"unknown autoscale metric {metric!r}")
        collector.record(value)

    def _threshold_for(self, collector: MetricCollector) -> float:
        return {
            "cpu": self.config.cpu_threshold,
            "memory": self.config.memory_threshold,
            "queue_length": self.config.queue_threshold,
            "request_rate": self.config.request_rate_threshold,
            "token_throughput": self.config.token_throughput_threshold,
        }.get(collector.name, collector.default_threshold)

    async def evaluate(self, now: float | None = None) -> AutoscaleDecision | None:
        """One autoscaling evaluation; returns the decision if any."""
        if not self.config.autoscale_enabled:
            return None
        now = now if now is not None else time.time()
        if now - self._last_eval < self.config.autoscale_cooldown:
            return None
        self._last_eval = now
        decision: AutoscaleDecision | None = None
        for name, collector in self.collectors.items():
            current = collector.sample()
            threshold = self._threshold_for(collector)
            scale_up = current >= threshold
            scale_down = current < threshold * self.config.scale_down_factor
            if not (scale_up or scale_down):
                continue
            ratio = current / threshold if threshold else 1.0
            if scale_up:
                desired = min(
                    self.config.max_replicas,
                    max(self._replicas, int(self._replicas * ratio * self.config.autoscale_factor) + 1),
                )
                reason = f"{name} at {current:.1f} exceeds threshold {threshold:.1f}"
            else:
                desired = max(
                    self.config.min_replicas,
                    int(self._replicas * ratio),
                )
                reason = f"{name} at {current:.1f} below scale-down threshold {threshold * self.config.scale_down_factor:.1f}"
            if desired == self._replicas:
                continue
            decision = AutoscaleDecision(
                component=self._component,
                metric=name,
                current=current,
                threshold=threshold,
                desired=desired,
                previous=self._replicas,
                reason=reason,
            )
            self._replicas = desired
            self._decisions.append(decision)
            self.logger.log_event("autoscale", **decision.to_dict())
            self.metrics.record("scale_decisions", component="autoscale")
            if self._apply_scale is not None:
                self._apply_scale(self._component, desired)
            for observer in list(self._observers):
                try:
                    result = observer(decision)
                    if asyncio.iscoroutine(result):
                        await result
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - observers are isolated
                    pass
        return decision

    # -- reporting ----------------------------------------------------------------------

    def decisions(self, limit: int = 50) -> list[AutoscaleDecision]:
        return list(reversed(self._decisions[-limit:]))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.config.autoscale_enabled,
            "replicas": self._replicas,
            "min_replicas": self.config.min_replicas,
            "max_replicas": self.config.max_replicas,
            "cooldown": self.config.autoscale_cooldown,
            "metrics": {name: collector.last() for name, collector in self.collectors.items()},
            "decisions": [d.to_dict() for d in self.decisions()],
        }
