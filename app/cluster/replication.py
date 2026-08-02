"""Backup, restore, replication and disaster recovery.

- :class:`BackupManager` — create/list/restore/prune backups from an
  injectable state provider (Repository pattern via :class:`BackupStore`).
- :class:`ReplicationManager` — fans a snapshot out to replicas through an
  injectable transport, tracking lag and state per replica.
- :class:`DisasterRecovery` — promotes standby nodes and fails over whole
  regions.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Awaitable, Callable

from .config import ClusterConfig
from .exceptions import BackupError, DRFailoverError, RestoreError
from .logging import ClusterLogger
from .metrics import ClusterMetricsTracker
from .models import (
    BackupRecord,
    BackupStatus,
    NodeInfo,
    NodeRole,
    NodeState,
    ReplicationRecord,
    ReplicationState,
    generate_id,
)
from .repository import BackupStore, NodeStore, SnapshotStore

StateProvider = Callable[[], dict[str, Any]]
RestoreTarget = Callable[[dict[str, Any]], None]
ReplicaTransport = Callable[["ReplicationManager", str, dict[str, Any]], Awaitable[None]]
"""transport(manager, replica_id, snapshot)"""


class BackupManager:
    """Creates and restores full-state backups."""

    def __init__(
        self,
        config: ClusterConfig | None = None,
        store: BackupStore | None = None,
        logger: ClusterLogger | None = None,
        metrics: ClusterMetricsTracker | None = None,
        state_provider: StateProvider | None = None,
        restore_target: RestoreTarget | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.store = store if store is not None else BackupStore()
        self.logger = logger or ClusterLogger(self.config)
        self.metrics = metrics or ClusterMetricsTracker(self.config)
        self.state_provider = state_provider or (lambda: {})
        self.restore_target = restore_target or (lambda data: None)

    def create_backup(self, name: str = "", metadata: dict[str, Any] | None = None) -> BackupRecord:
        """Snapshot provider state into a new backup record."""
        data = self.state_provider()
        if not isinstance(data, dict):
            raise BackupError("state provider must return a dict")
        checksum = _checksum(data)
        record = BackupRecord(
            name=name or f"backup-{generate_id('')[:8]}",
            size=len(json.dumps(data, default=str)),
            checksum=checksum,
            entries=len(data),
            status=BackupStatus.OK,
            metadata=dict(metadata or {}),
            data=data,
        )
        self.store.save(record)
        if self.config.backup_prune_max > 0:
            self.prune(self.config.backup_prune_max)
        self.logger.log_event(
            "backup_created", id=record.id, name=record.name, entries=record.entries, size=record.size
        )
        self.metrics.record("backups_created", component="replication")
        return record

    def list_backups(self) -> list[BackupRecord]:
        return self.store.list()

    def get(self, backup_id: str) -> BackupRecord:
        try:
            return self.store.require(backup_id)
        except KeyError as exc:
            raise BackupError(str(exc)) from exc

    def restore(self, backup_id: str, verify: bool = True) -> BackupRecord:
        """Restore a backup into the injectable restore target."""
        record = self.get(backup_id)
        if record.status != BackupStatus.OK:
            raise RestoreError(f"backup {backup_id!r} is not restorable (status {record.status.value})")
        if verify:
            actual = _checksum(record.data)
            if actual != record.checksum:
                raise RestoreError(f"backup {backup_id!r} checksum mismatch")
        try:
            self.restore_target(dict(record.data))
        except Exception as exc:  # noqa: BLE001 - surface as restore error
            raise RestoreError(f"restore of {backup_id!r} failed: {exc}") from exc
        record.restored_at = time.time()
        self.logger.log_event("backup_restored", id=record.id, name=record.name)
        self.metrics.record("backups_restored", component="replication")
        return record

    def delete(self, backup_id: str) -> bool:
        removed = self.store.remove(backup_id)
        if removed:
            self.logger.log_event("backup_deleted", id=backup_id)
        return removed

    def prune(self, max_keep: int) -> int:
        """Keep the newest ``max_keep`` backups; returns number deleted."""
        records = self.store.list()
        removed = 0
        for record in records[max_keep:]:
            if self.store.remove(record.id):
                removed += 1
        if removed:
            self.logger.log_event("backups_pruned", removed=removed, max_keep=max_keep)
        return removed

    def status(self) -> dict[str, Any]:
        backups = self.list_backups()
        return {
            "count": len(backups),
            "total_size": sum(b.size for b in backups),
            "latest": backups[0].to_dict() if backups else None,
            "backups": [b.to_dict() for b in backups],
        }


class ReplicationManager:
    """Replicates snapshots to standby replicas with lag tracking."""

    def __init__(
        self,
        config: ClusterConfig | None = None,
        store: SnapshotStore | None = None,
        logger: ClusterLogger | None = None,
        metrics: ClusterMetricsTracker | None = None,
        transport: ReplicaTransport | None = None,
        replicas: list[str] | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.store = store if store is not None else SnapshotStore()
        self.logger = logger or ClusterLogger(self.config)
        self.metrics = metrics or ClusterMetricsTracker(self.config)
        self.transport = transport or self._default_transport
        self.replicas = list(replicas or [])
        self._last_replication = 0.0

    async def _default_transport(self, manager: "ReplicationManager", replica_id: str, snapshot: dict[str, Any]) -> None:
        # In-memory default: nothing to ship; real deployments inject transport.
        return None

    def add_replica(self, replica_id: str) -> None:
        if replica_id not in self.replicas:
            self.replicas.append(replica_id)

    def remove_replica(self, replica_id: str) -> bool:
        if replica_id in self.replicas:
            self.replicas.remove(replica_id)
            return True
        return False

    async def replicate(self, snapshot: dict[str, Any], snapshot_id: str = "") -> list[ReplicationRecord]:
        """Send a snapshot to all configured replicas; returns records."""
        snapshot_id = snapshot_id or f"snapshot-{generate_id('')[:8]}"
        self.store.save_snapshot(snapshot_id, snapshot)
        records: list[ReplicationRecord] = []
        started = time.time()
        for replica in self.replicas:
            record = ReplicationRecord(snapshot_id=snapshot_id, replica_id=replica)
            self.store.save_record(record)
            try:
                await self.transport(self, replica, snapshot)
            except Exception as exc:  # noqa: BLE001 - per-replica isolation
                self.store.update_record(record.id, state=ReplicationState.FAILED, error=str(exc))
                self.logger.log_event(
                    "replication_failed", snapshot=snapshot_id, replica=replica, error=str(exc)
                )
                records.append(record)
                continue
            self.store.update_record(
                record.id,
                state=ReplicationState.REPLICATED,
                lag_seconds=time.time() - started,
                replicated_at=time.time(),
            )
            self.logger.log_event("replication_ok", snapshot=snapshot_id, replica=replica)
            records.append(record)
        self._last_replication = time.time()
        self.metrics.record("replications", component="replication", amount=len(self.replicas))
        return records

    def lag(self) -> float:
        return self.store.latest_lag()

    def records(self, snapshot_id: str | None = None) -> list[ReplicationRecord]:
        return self.store.records(snapshot_id)

    def snapshots(self) -> list[str]:
        return self.store.list_snapshots()

    def status(self) -> dict[str, Any]:
        records = self.records()
        return {
            "replicas": list(self.replicas),
            "replicated": sum(1 for r in records if r.state == ReplicationState.REPLICATED),
            "failed": sum(1 for r in records if r.state == ReplicationState.FAILED),
            "latest_lag": self.lag(),
            "snapshots": self.snapshots(),
            "last_replication": self._last_replication,
        }


class DisasterRecovery:
    """Region failover and standby promotion."""

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

    def promote_standby(self, node_id: str) -> NodeInfo:
        """Promote a standby node to leader-capable active node."""
        node = self.store.get(node_id)
        if node is None:
            raise DRFailoverError(f"unknown node {node_id!r}")
        if node.state == NodeState.FAILED:
            raise DRFailoverError(f"cannot promote failed node {node_id!r}")
        if node.role != NodeRole.STANDBY and node.role != NodeRole.FOLLOWER:
            raise DRFailoverError(f"node {node_id!r} is already {node.role.value}")
        if node.role == NodeRole.STANDBY:
            self.store.update(node_id, role=NodeRole.FOLLOWER, state=NodeState.HEALTHY)
            node = self.store.require(node_id)
        self.logger.log_event("standby_promoted", node=node_id)
        self.metrics.record("standby_promotions", component="dr")
        return node

    def demote(self, node_id: str) -> NodeInfo:
        """Mark a node as standby (no leader candidacy)."""
        node = self.store.get(node_id)
        if node is None:
            raise DRFailoverError(f"unknown node {node_id!r}")
        self.store.update(node_id, role=NodeRole.STANDBY)
        return self.store.require(node_id)

    async def failover_region(self, region: str, standby_region: str = "") -> int:
        """Demote every node in ``region`` and promote standbys elsewhere."""
        nodes = [n for n in self.store.all() if n.region == region]
        if not nodes:
            raise DRFailoverError(f"no nodes found in region {region!r}")
        standby_region = standby_region or region
        candidates = [
            n
            for n in self.store.all()
            if n.region == standby_region and n.state != NodeState.FAILED
        ]
        if not candidates:
            raise DRFailoverError(f"no candidates available in region {standby_region!r}")
        for node in nodes:
            if node.id != self.config.node_id:
                self.store.update(node.id, state=NodeState.FAILED)
            else:
                self.store.update(node.id, role=NodeRole.STANDBY)
        for candidate in candidates:
            self.promote_standby(candidate.id)
        promoted = len(nodes)
        self.logger.log_event("region_failover", region=region, standby_region=standby_region, promoted=promoted)
        self.metrics.record("region_failovers", component="dr")
        return promoted

    def dr_status(self) -> dict[str, Any]:
        nodes = self.store.all()
        return {
            "nodes": [n.to_dict() for n in nodes],
            "standbys": sum(1 for n in nodes if n.role == NodeRole.STANDBY),
            "failed": sum(1 for n in nodes if n.state == NodeState.FAILED),
            "regions": sorted({n.region for n in nodes}),
        }


def _checksum(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
