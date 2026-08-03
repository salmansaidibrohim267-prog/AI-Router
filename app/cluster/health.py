"""Node health monitoring and heartbeat (Observer pattern).

The monitor sends local heartbeats and assesses membership freshness.
Observers are notified whenever a node transitions between healthy and
failed/suspected.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .config import ClusterConfig
from .logging import ClusterLogger
from .metrics import ClusterMetricsTracker
from .models import HealthReport, Heartbeat, NodeInfo, NodeState
from .repository import NodeStore

HealthObserver = Callable[[str, NodeState, NodeState], Awaitable[None]]
"""observer(node_id, previous_state, new_state)"""


class HealthMonitor:
    """Tracks heartbeats, marks nodes dead/suspected, notifies observers."""

    def __init__(
        self,
        config: ClusterConfig | None = None,
        store: NodeStore | None = None,
        logger: ClusterLogger | None = None,
        metrics: ClusterMetricsTracker | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.store = store if store is not None else NodeStore()
        self.logger = logger or ClusterLogger(self.config)
        self.metrics = metrics or ClusterMetricsTracker(self.config)
        self._observers: list[HealthObserver] = []
        self._loop_task: asyncio.Task | None = None
        self._running = False
        self._custom_checks: dict[str, Callable[[NodeInfo], bool]] = {}

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._loop(), name="cluster-health")

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
                self.send_heartbeat(self.config.node_id)
                await self.evaluate()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - monitor must survive
                self.logger.log_event("health_eval_error", error=str(exc))
            await asyncio.sleep(self.config.heartbeat_interval)

    # -- observers -------------------------------------------------------------

    def subscribe(self, observer: HealthObserver) -> Callable[[], None]:
        self._observers.append(observer)

        def unsubscribe() -> None:
            if observer in self._observers:
                self._observers.remove(observer)

        return unsubscribe

    def unsubscribe(self, observer: HealthObserver) -> bool:
        if observer in self._observers:
            self._observers.remove(observer)
            return True
        return False

    def register_check(self, name: str, check: Callable[[NodeInfo], bool]) -> None:
        self._custom_checks[name] = check

    # -- heartbeats --------------------------------------------------------------

    def send_heartbeat(self, node_id: str, load: float = 0.0) -> Heartbeat:
        self.store.touch(node_id, load=load)
        return Heartbeat(node_id=node_id, load=load)

    def receive_heartbeat(self, heartbeat: Heartbeat) -> None:
        self.store.record_heartbeat(heartbeat)

    def last_seen(self, node_id: str) -> float:
        node = self.store.get(node_id)
        return node.last_seen if node is not None else 0.0

    def is_stale(self, node_id: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return now - self.last_seen(node_id) > self.config.heartbeat_timeout

    # -- assessment --------------------------------------------------------------

    def check(self, node: NodeInfo, now: float | None = None) -> HealthReport:
        now = now if now is not None else time.time()
        checks: dict[str, bool] = {
            "registered": True,
            "heartbeat_fresh": now - self.last_seen(node.id) <= self.config.heartbeat_timeout,
        }
        for name, fn in self._custom_checks.items():
            try:
                checks[name] = bool(fn(node))
            except Exception:  # noqa: BLE001 - a failing check means unhealthy
                checks[name] = False
        healthy = all(checks.values())
        return HealthReport(
            node_id=node.id,
            healthy=healthy,
            last_seen=self.last_seen(node.id),
            checks=checks,
            checked_at=now,
        )

    async def evaluate(self, now: float | None = None) -> list[tuple[str, NodeState, NodeState]]:
        """Re-assess all members and fire state-change notifications."""
        now = now if now is not None else time.time()
        transitions: list[tuple[str, NodeState, NodeState]] = []
        for node in self.store.all():
            if node.state in (NodeState.LEFT, NodeState.LEAVING, NodeState.FAILED):
                continue
            previous = node.state
            if now - self.last_seen(node.id) > self.config.heartbeat_timeout:
                new_state = NodeState.FAILED if previous == NodeState.HEALTHY else NodeState.SUSPECTED
            else:
                new_state = NodeState.HEALTHY
            if new_state != previous:
                self.store.mark(node.id, new_state)
                transitions.append((node.id, previous, new_state))
                self.logger.log_event("health_change", node=node.id, previous=previous.value, state=new_state.value)
                if new_state == NodeState.FAILED:
                    self.metrics.record("node_failures", component="health")
                if new_state == NodeState.HEALTHY:
                    self.metrics.record("node_recoveries", component="health")
        for node_id, previous, new_state in transitions:
            for observer in list(self._observers):
                try:
                    result = observer(node_id, previous, new_state)
                    if asyncio.iscoroutine(result):
                        await result
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - observers are isolated
                    self.logger.log_event("health_observer_error", node=node_id, error=str(exc))
        return transitions

    def reports(self, now: float | None = None) -> list[HealthReport]:
        return [self.check(node, now) for node in self.store.all()]

    def healthy_nodes(self) -> list[NodeInfo]:
        return [n for n in self.store.all() if self.check(n).healthy and n.state != NodeState.FAILED]

    def dead_nodes(self) -> list[NodeInfo]:
        return [n for n in self.store.all() if n.state == NodeState.FAILED]

    def status(self) -> dict[str, Any]:
        reports = self.reports()
        return {
            "healthy": sum(1 for r in reports if r.healthy),
            "unhealthy": sum(1 for r in reports if not r.healthy),
            "total": len(reports),
            "reports": [r.to_dict() for r in reports],
        }
