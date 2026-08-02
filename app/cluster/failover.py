"""Automatic failover and task reassignment.

Subscribes to the health monitor (Observer pattern); whenever a member is
marked failed, its jobs and tasks are reassigned to surviving nodes and
failover events are recorded.
"""

from __future__ import annotations

import time
from typing import Any

from .config import ClusterConfig
from .logging import ClusterLogger
from .metrics import ClusterMetricsTracker
from .models import JobState, NodeInfo, NodeState, RebalanceReason
from .repository import JobStore, NodeStore
from .health import HealthMonitor

FailoverRecord = dict[str, Any]


class FailoverManager:
    """Detects node failures and reassigns their work."""

    def __init__(
        self,
        config: ClusterConfig | None = None,
        store: NodeStore | None = None,
        jobs: JobStore | None = None,
        health: HealthMonitor | None = None,
        logger: ClusterLogger | None = None,
        metrics: ClusterMetricsTracker | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.store = store if store is not None else NodeStore()
        self.jobs = jobs if jobs is not None else JobStore()
        self.health = health
        self.logger = logger or ClusterLogger(self.config)
        self.metrics = metrics or ClusterMetricsTracker(self.config)
        self._history: list[FailoverRecord] = []
        self._unsubscribe: Any = None

    async def start(self) -> None:
        if self._unsubscribe is not None:
            return
        if self.health is not None:
            self._unsubscribe = self.health.subscribe(self._on_health_change)

    async def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def _on_health_change(self, node_id: str, previous: NodeState, new_state: NodeState) -> None:
        if new_state != NodeState.FAILED:
            return
        await self.reassign(node_id, reason=RebalanceReason.NODE_FAILED)

    async def reassign(self, node_id: str, reason: RebalanceReason = RebalanceReason.NODE_FAILED) -> int:
        """Reassign all jobs owned by ``node_id``; returns count reassigned."""
        node = self.store.get(node_id)
        if node is None:
            return 0
        reassigned = 0
        for job in self.jobs.by_owner(node_id):
            if not job.failover:
                continue
            self.jobs.update(job.id, owner=None)
            reassigned += 1
        record: FailoverRecord = {
            "node_id": node_id,
            "reason": reason.value,
            "jobs_reassigned": reassigned,
            "timestamp": time.time(),
        }
        self._history.append(record)
        self.metrics.record("failovers", component="failover")
        self.metrics.record("jobs_reassigned", component="failover", amount=reassigned)
        self.logger.log_event("failover", **record)
        return reassigned

    def history(self) -> list[FailoverRecord]:
        return list(self._history)

    def reassign_orphans(self) -> int:
        """Claim-based helper: count orphaned failover jobs awaiting pickup."""
        return len(self.jobs.orphaned())

    def status(self) -> dict[str, Any]:
        return {
            "failovers": len(self._history),
            "orphaned_jobs": len(self.jobs.orphaned()),
            "last_failover": self._history[-1] if self._history else None,
        }
