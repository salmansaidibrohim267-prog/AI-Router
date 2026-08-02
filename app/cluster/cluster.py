"""ClusterManager — the cluster coordinator facade (Coordinator pattern).

Wires discovery, leader election, the distributed scheduler, health
monitoring, failover, autoscaling, deployments and replication/DR together,
and exposes the required public surface: ``join``, ``leave``, ``discover``,
``rebalance``, ``status``, ``shutdown``.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .autoscale import Autoscaler
from .config import ClusterConfig
from .deployments import DeploymentManager
from .discovery import DiscoveryBackend, create_discovery
from .election import Elector, LeaseElection, create_elector
from .exceptions import (
    ClusterError,
    ClusterNotStartedError,
    NodeAlreadyJoinedError,
)
from .failover import FailoverManager
from .health import HealthMonitor
from .logging import ClusterLogger
from .metrics import ClusterMetricsTracker
from .models import NodeInfo, NodeRole, NodeState, RebalanceReason, RebalanceReport
from .replication import BackupManager, DisasterRecovery, ReplicationManager
from .repository import BackupStore, JobStore, LeaseStore, NodeStore, SnapshotStore
from .scheduler import DistributedScheduler


class ClusterManager:
    """High-level cluster coordinator."""

    def __init__(
        self,
        config: ClusterConfig | None = None,
        store: NodeStore | None = None,
        logger: ClusterLogger | None = None,
        metrics: ClusterMetricsTracker | None = None,
        discovery: DiscoveryBackend | None = None,
        elector: Elector | None = None,
        scheduler: DistributedScheduler | None = None,
        health: HealthMonitor | None = None,
        failover: FailoverManager | None = None,
        autoscaler: Autoscaler | None = None,
        deployments: DeploymentManager | None = None,
        backup: BackupManager | None = None,
        replication: ReplicationManager | None = None,
        dr: DisasterRecovery | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.logger = logger or ClusterLogger(self.config)
        self.metrics = metrics or ClusterMetricsTracker(self.config)
        self.store = store if store is not None else NodeStore()
        self.discovery = discovery
        self.elector = elector
        self.scheduler = scheduler
        self.health = health
        self.failover = failover
        self.autoscaler = autoscaler
        self.deployments = deployments
        self.backup = backup
        self.replication = replication
        self.dr = dr
        self.node = NodeInfo(
            id=self.config.node_id,
            name=self.config.node_name,
            address=self.config.node_address,
            port=self.config.node_port,
            role=NodeRole.FOLLOWER,
            state=NodeState.JOINING,
            region=self.config.region,
            zone=self.config.zone,
            labels=dict(self.config.labels),
            version=self.config.version,
        )
        self.running = False
        self.started_at = 0.0
        self._election_observer: Any = None
        self._leader_failover_task: asyncio.Task | None = None

    # -- lifecycle -------------------------------------------------------------------

    async def join(self) -> None:
        """Join the cluster: register, start election, monitoring and loops."""
        if self.running:
            raise NodeAlreadyJoinedError("node already joined")
        self.store.register(self.node)
        if self.discovery is not None:
            await self.discovery.start()
            await self.discovery.register(self.node)
        self.store.mark(self.node.id, NodeState.JOINED)
        self.node.state = NodeState.JOINED
        self.logger.log_event(
            "node_joined",
            node=self.node.id,
            address=self.node.address,
            port=self.node.port,
            region=self.node.region,
        )
        self.metrics.record("node_joins", component="cluster")

        if self.elector is not None:
            self._election_observer = self.elector.on_change(self._on_leader_change)
            await self.elector.start()
        if self.health is not None:
            await self.health.start()
        if self.failover is not None:
            await self.failover.start()
        if self.scheduler is not None:
            self.scheduler.set_node_id(self.node.id)
            if self.elector is not None:
                self.scheduler.set_leader_check(lambda: self.elector.is_leader)
            await self.scheduler.start()
        if self.autoscaler is not None:
            self.autoscaler.set_component(self.node.id)
            await self.autoscaler.start()
        if self.deployments is not None:
            await self.deployments.start()
        self.running = True
        self.started_at = time.time()
        self._leader_failover_task = asyncio.create_task(
            self._watch_leader_failover(), name="cluster-leader-watch"
        )
        self.logger.log_event("cluster_joined", node=self.node.id)

    async def leave(self) -> None:
        """Gracefully leave the cluster."""
        if not self.running:
            raise ClusterNotStartedError("cluster not started")
        self.logger.log_event("node_leaving", node=self.node.id)
        if self.elector is not None:
            await self.elector.stop()
            if self.elector.is_leader:
                await self.elector.step_down()
        for component in (self.scheduler, self.health, self.failover, self.autoscaler, self.deployments):
            if component is not None:
                await component.stop()
        if self.discovery is not None:
            try:
                await self.discovery.deregister(self.node.id)
            except ClusterError:
                pass
        self.store.mark(self.node.id, NodeState.LEFT)
        self.running = False
        self.logger.log_event("node_left", node=self.node.id)
        self.metrics.record("node_leaves", component="cluster")

    async def shutdown(self) -> None:
        """Teardown everything (idempotent)."""
        if self.running:
            await self.leave()
        if self._leader_failover_task is not None:
            self._leader_failover_task.cancel()
            try:
                await self._leader_failover_task
            except asyncio.CancelledError:
                pass
            self._leader_failover_task = None
        if self.discovery is not None:
            await self.discovery.close()
        self.logger.log_event("cluster_shutdown", node=self.node.id)

    # -- core operations ---------------------------------------------------------------

    async def discover(self) -> list[NodeInfo]:
        """Query the discovery backend and refresh membership."""
        if self.discovery is None:
            return []
        nodes = await self.discovery.discover()
        for node in nodes:
            if self.store.get(node.id) is None:
                self.store.register(node)
        self.logger.log_event("discovery_refresh", node=self.node.id, found=len(nodes))
        return nodes

    async def rebalance(self, reason: RebalanceReason = RebalanceReason.REBALANCE) -> RebalanceReport:
        """Reassign work: fail over dead nodes, re-claim orphans, re-elect."""
        report = RebalanceReport(reason=reason)
        if not self.running:
            raise ClusterNotStartedError("cluster not started")

        dead = [n for n in self.store.by_state(NodeState.FAILED)]
        report.failed_nodes = [n.id for n in dead]
        for node in dead:
            if self.failover is not None:
                report.reassigned_jobs += await self.failover.reassign(
                    node.id, reason=RebalanceReason.NODE_FAILED
                )

        if self.scheduler is not None:
            for job in self.scheduler.store.orphaned():
                self.scheduler.store.claim(job.id, self.node.id)
            report.orphaned_jobs = len(self.scheduler.store.orphaned())

        leader = self.store.leader() if self.elector is None else None
        if self.elector is not None:
            current = self.elector.current_leader
            leader_node = self.store.get(current) if current else None
            if leader_node is None or leader_node.state == NodeState.FAILED:
                if isinstance(self.elector, LeaseElection) and current:
                    self.elector.store.release("cluster-leader", current)
                if self.elector.is_leader:
                    await self.elector.step_down()
                elected = await self.elector.elect()
                report.elected_leader = bool(elected)
            report.leader = self.elector.current_leader or ""
        elif leader is not None:
            report.leader = leader.id
        report.timestamp = time.time()
        self.logger.log_event("rebalance", node=self.node.id, **report.to_dict())
        self.metrics.record("rebalances", component="cluster")
        return report

    async def _on_leader_change(self, leader: str | None, epoch: int) -> None:
        self.logger.log_event(
            "leader_observed", node=self.node.id, leader=leader, epoch=epoch, is_leader=(leader == self.node.id)
        )
        if leader == self.node.id:
            self.store.set_leader(self.node.id, epoch)
            self.node.role = NodeRole.LEADER
            self.logger.log_event("node_elected_leader", node=self.node.id, epoch=epoch)
            self.metrics.record("leader_elections", component="cluster")
            if self.failover is not None:
                for dead in self.store.by_state(NodeState.FAILED):
                    await self.failover.reassign(dead.id, reason=RebalanceReason.LEADER_LOST)

    async def _watch_leader_failover(self) -> None:
        """Periodically verify leadership; re-elect if the leader vanished."""
        while True:
            await asyncio.sleep(self.config.election_retry_interval)
            if not self.running:
                return
            if self.elector is None:
                continue
            current = self.elector.current_leader
            if not current:
                continue
            leader_node = self.store.get(current)
            if leader_node is None or leader_node.state == NodeState.FAILED:
                await self.rebalance(reason=RebalanceReason.LEADER_LOST)

    # -- reporting -----------------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        """Full cluster observability snapshot."""
        report: dict[str, Any] = {
            "cluster": {
                "node_id": self.node.id,
                "name": self.node.name,
                "state": self.node.state.value,
                "role": self.node.role.value,
                "version": self.config.version,
                "running": self.running,
                "started_at": self.started_at,
            },
            "membership": {
                "total": len(self.store),
                "healthy": len([n for n in self.store.all() if n.state == NodeState.HEALTHY]),
                "failed": len(self.store.by_state(NodeState.FAILED)),
                "nodes": [n.to_dict() for n in self.store.all()],
            },
        }
        if self.elector is not None:
            report["leadership"] = {
                "leader": self.elector.current_leader,
                "is_leader": self.elector.is_leader,
                "epoch": self.elector.epoch,
                "strategy": self.elector.name,
            }
        if self.scheduler is not None:
            report["scheduler"] = self.scheduler.status()
        if self.health is not None:
            report["health"] = self.health.status()
        if self.autoscaler is not None:
            report["autoscale"] = self.autoscaler.status()
        if self.deployments is not None:
            report["deployments"] = self.deployments.status()
        if self.backup is not None:
            report["backups"] = self.backup.status()
        if self.replication is not None:
            report["replication"] = self.replication.status()
        if self.dr is not None:
            report["dr"] = self.dr.dr_status()
        report["observability"] = {
            "events": len(self.logger.events),
            "metrics": self.metrics.summary(),
        }
        return report


def create_cluster_manager(config: ClusterConfig | None = None, **overrides: Any) -> ClusterManager:
    """DI factory: wires the full cluster stack with injectable collaborators.

    ``overrides`` may provide: store, logger, metrics, discovery, elector,
    scheduler, health, failover, autoscaler, deployments, backup,
    replication, dr, plus pass-through kwargs for ``create_discovery``
    (transport/registry) and ``create_elector`` (kv/transport/store).
    """
    config = config or ClusterConfig()
    node_id = overrides.pop("node_id", None)
    if node_id is not None:
        config = ClusterConfig(**{**config.as_dict(), "node_id": node_id})
    logger = overrides.pop("logger", None) or ClusterLogger(config)
    metrics = overrides.pop("metrics", None) or ClusterMetricsTracker(config)
    store = overrides.pop("store", None)
    if store is None:
        store = NodeStore()
    discovery = overrides.pop("discovery", None)
    elector = overrides.pop("elector", None)
    scheduler = overrides.pop("scheduler", None)
    health = overrides.pop("health", None)
    failover = overrides.pop("failover", None)
    autoscaler = overrides.pop("autoscaler", None)
    deployments = overrides.pop("deployments", None)
    backup = overrides.pop("backup", None)
    replication = overrides.pop("replication", None)
    dr = overrides.pop("dr", None)

    if discovery is None:
        discovery = create_discovery(config, transport=overrides.pop("discovery_transport", None))
    job_store = overrides.pop("job_store", None)
    if job_store is None:
        job_store = JobStore()
    lease_store = overrides.pop("lease_store", None)
    if lease_store is None:
        lease_store = LeaseStore()
    backup_store = overrides.pop("backup_store", None)
    if backup_store is None:
        backup_store = BackupStore()
    snapshot_store = overrides.pop("snapshot_store", None)
    if snapshot_store is None:
        snapshot_store = SnapshotStore()
    if elector is None:
        election_options = dict(overrides.pop("election_options", {}))
        if "store" not in election_options:
            election_options["store"] = lease_store
        if "nodes" not in election_options:
            election_options["nodes"] = store
        elector = create_elector(
            config,
            NodeInfo(
                id=config.node_id,
                name=config.node_name,
                address=config.node_address,
                port=config.node_port,
                region=config.region,
                zone=config.zone,
                labels=config.labels,
                version=config.version,
            ),
            logger,
            **election_options,
        )

    if scheduler is None:
        scheduler = DistributedScheduler(config, job_store, logger, metrics)
    if health is None:
        health = HealthMonitor(config, store, logger, metrics)
    if failover is None:
        failover = FailoverManager(config, store, job_store, health, logger, metrics)
    if autoscaler is None:
        autoscaler = Autoscaler(config, logger, metrics)
    if deployments is None:
        deployments = DeploymentManager(config, store, logger, metrics)
    if backup is None:
        backup = BackupManager(config, backup_store, logger, metrics)
    if replication is None:
        replication = ReplicationManager(config, snapshot_store, logger, metrics)
    if dr is None:
        dr = DisasterRecovery(config, store, logger, metrics)

    if overrides:
        raise TypeError(f"unexpected cluster manager overrides: {sorted(overrides)}")

    return ClusterManager(
        config=config,
        store=store,
        logger=logger,
        metrics=metrics,
        discovery=discovery,
        elector=elector,
        scheduler=scheduler,
        health=health,
        failover=failover,
        autoscaler=autoscaler,
        deployments=deployments,
        backup=backup,
        replication=replication,
        dr=dr,
    )
