"""Repository pattern: in-memory stores for cluster state.

Every store is a Repository: it owns its data and exposes a narrow,
mutation-safe API. Implementations are in-memory by default so the whole
framework runs without external infrastructure; a ``shared`` store can be
swapped in for real multi-node operation (e.g. backed by Redis/etcd).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from .models import (
    BackupRecord,
    Heartbeat,
    JobRun,
    JobSpec,
    NodeInfo,
    NodeState,
    ReplicationRecord,
)


class _Locked:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> "_Locked":
        self._lock.acquire()
        return self

    def __exit__(self, *_: Any) -> None:
        self._lock.release()


class NodeStore:
    """Repository of cluster members (nodes)."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeInfo] = {}
        self._history: list[NodeInfo] = []
        self._heartbeats: dict[str, Heartbeat] = {}
        self._lock = _Locked()

    def register(self, node: NodeInfo) -> None:
        with self._lock:
            self._nodes[node.id] = node

    def get(self, node_id: str) -> NodeInfo | None:
        with self._lock:
            return self._nodes.get(node_id)

    def require(self, node_id: str) -> NodeInfo:
        node = self.get(node_id)
        if node is None:
            raise KeyError(f"unknown node {node_id!r}")
        return node

    def update(self, node_id: str, **changes: Any) -> NodeInfo:
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                raise KeyError(f"unknown node {node_id!r}")
            for key, value in changes.items():
                if not hasattr(node, key):
                    raise AttributeError(f"NodeInfo has no field {key!r}")
                setattr(node, key, value)
            return node

    def remove(self, node_id: str) -> None:
        with self._lock:
            node = self._nodes.pop(node_id, None)
            if node is not None:
                self._history.append(node)

    def all(self) -> list[NodeInfo]:
        with self._lock:
            return sorted(self._nodes.values(), key=lambda n: n.id)

    def by_state(self, state: NodeState) -> list[NodeInfo]:
        return [n for n in self.all() if n.state == state]

    def alive(self) -> list[NodeInfo]:
        return [
            n
            for n in self.all()
            if n.state not in (NodeState.FAILED, NodeState.LEFT, NodeState.LEAVING)
        ]

    def history(self) -> list[NodeInfo]:
        with self._lock:
            return list(self._history)

    def mark(self, node_id: str, state: NodeState) -> None:
        self.update(node_id, state=state)

    def touch(self, node_id: str, load: float = 0.0) -> None:
        with self._lock:
            node = self._nodes.get(node_id)
            if node is not None:
                node.last_seen = time.time()
                node.state = NodeState.HEALTHY
            self._heartbeats[node_id] = Heartbeat(node_id=node_id, load=load)

    def record_heartbeat(self, heartbeat: Heartbeat) -> None:
        with self._lock:
            node = self._nodes.get(heartbeat.node_id)
            if node is not None:
                node.last_seen = heartbeat.timestamp
                node.state = heartbeat.state
            self._heartbeats[heartbeat.node_id] = heartbeat

    def last_heartbeat(self, node_id: str) -> Heartbeat | None:
        with self._lock:
            return self._heartbeats.get(node_id)

    def leader(self) -> NodeInfo | None:
        leaders = [n for n in self.all() if n.role.value == "leader"]
        if not leaders:
            return None
        return max(leaders, key=lambda n: n.leader_epoch)

    def set_leader(self, node_id: str, epoch: int | None = None) -> None:
        with self._lock:
            for node in self._nodes.values():
                node.role = type(node.role)("follower")
                node.leader_epoch = 0
            node = self._nodes.get(node_id)
            if node is not None:
                node.role = type(node.role)("leader")
                node.leader_epoch = epoch if epoch is not None else node.leader_epoch + 1

    def next_epoch(self) -> int:
        with self._lock:
            return max((n.leader_epoch for n in self._nodes.values()), default=0) + 1

    def snapshot(self) -> list[dict[str, Any]]:
        return [n.to_dict() for n in self.all()]

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)


class JobStore:
    """Repository of scheduled jobs and their execution history."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobSpec] = {}
        self._runs: dict[str, JobRun] = {}
        self._lock = _Locked()

    def add(self, job: JobSpec) -> JobSpec:
        with self._lock:
            self._jobs[job.id] = job
            return job

    def get(self, job_id: str) -> JobSpec | None:
        with self._lock:
            return self._jobs.get(job_id)

    def require(self, job_id: str) -> JobSpec:
        job = self.get(job_id)
        if job is None:
            raise KeyError(f"unknown job {job_id!r}")
        return job

    def remove(self, job_id: str) -> bool:
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def all(self) -> list[JobSpec]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: (j.priority, j.created_at))

    def due(self, now: float | None = None) -> list[JobSpec]:
        now = now if now is not None else time.time()
        return [j for j in self.all() if j.next_run > 0 and j.next_run <= now]

    def by_owner(self, node_id: str) -> list[JobSpec]:
        return [j for j in self.all() if j.owner == node_id]

    def orphaned(self) -> list[JobSpec]:
        return [j for j in self.all() if j.failover and j.owner is None]

    def claim(self, job_id: str, node_id: str) -> bool:
        """Claim an unowned failover job (returns False if already owned)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or (job.owner is not None and job.owner != node_id):
                return False
            job.owner = node_id
            return True

    def update(self, job_id: str, **changes: Any) -> JobSpec:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"unknown job {job_id!r}")
            for key, value in changes.items():
                if not hasattr(job, key):
                    raise AttributeError(f"JobSpec has no field {key!r}")
                setattr(job, key, value)
            return job

    def add_run(self, run: JobRun) -> JobRun:
        with self._lock:
            self._runs[run.id] = run
            return run

    def get_run(self, run_id: str) -> JobRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def runs(self, job_id: str | None = None, limit: int = 100) -> list[JobRun]:
        with self._lock:
            values = (
                [r for r in self._runs.values() if r.job_id == job_id]
                if job_id is not None
                else list(self._runs.values())
            )
            values.sort(key=lambda r: r.started_at, reverse=True)
            return values[:limit]

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)


class LeaseStore:
    """Repository backing lease-based leader election.

    A store is distributed by swapping in a remote implementation; the
    in-memory one simulates a single shared namespace with TTLs.
    """

    def __init__(self) -> None:
        self._leases: dict[str, tuple[str, float]] = {}
        self._lock = _Locked()

    def acquire(self, name: str, holder: str, ttl: float) -> bool:
        now = time.time()
        with self._lock:
            existing = self._leases.get(name)
            if existing is not None and existing[0] != holder and existing[1] > now:
                return False
            self._leases[name] = (holder, now + ttl)
            return True

    def renew(self, name: str, holder: str, ttl: float) -> bool:
        now = time.time()
        with self._lock:
            existing = self._leases.get(name)
            if existing is None or existing[0] != holder:
                return False
            if existing[1] <= now:
                return False
            self._leases[name] = (holder, now + ttl)
            return True

    def release(self, name: str, holder: str) -> bool:
        with self._lock:
            existing = self._leases.get(name)
            if existing is None or existing[0] != holder:
                return False
            del self._leases[name]
            return True

    def get(self, name: str) -> tuple[str, float] | None:
        now = time.time()
        with self._lock:
            existing = self._leases.get(name)
            if existing is None:
                return None
            holder, expires = existing
            if expires <= now:
                del self._leases[name]
                return None
            return (holder, expires)

    def snapshot(self) -> dict[str, tuple[str, float]]:
        with self._lock:
            return dict(self._leases)


class BackupStore:
    """Repository of backup records."""

    def __init__(self) -> None:
        self._backups: dict[str, BackupRecord] = {}
        self._lock = _Locked()

    def save(self, record: BackupRecord) -> BackupRecord:
        with self._lock:
            self._backups[record.id] = record
            return record

    def get(self, backup_id: str) -> BackupRecord | None:
        with self._lock:
            return self._backups.get(backup_id)

    def require(self, backup_id: str) -> BackupRecord:
        record = self.get(backup_id)
        if record is None:
            raise KeyError(f"unknown backup {backup_id!r}")
        return record

    def list(self) -> list[BackupRecord]:
        with self._lock:
            return sorted(self._backups.values(), key=lambda b: b.created_at, reverse=True)

    def remove(self, backup_id: str) -> bool:
        with self._lock:
            return self._backups.pop(backup_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            return len(self._backups)


class SnapshotStore:
    """Repository of replication records."""

    def __init__(self) -> None:
        self._records: dict[str, ReplicationRecord] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._lock = _Locked()

    def save_record(self, record: ReplicationRecord) -> ReplicationRecord:
        with self._lock:
            self._records[record.id] = record
            return record

    def save_snapshot(self, snapshot_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._snapshots[snapshot_id] = data

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._snapshots.get(snapshot_id)
            return dict(data) if data is not None else None

    def list_snapshots(self) -> list[str]:
        with self._lock:
            return sorted(self._snapshots.keys())

    def records(self, snapshot_id: str | None = None) -> list[ReplicationRecord]:
        with self._lock:
            values = (
                [r for r in self._records.values() if r.snapshot_id == snapshot_id]
                if snapshot_id is not None
                else list(self._records.values())
            )
            return sorted(values, key=lambda r: r.replicated_at, reverse=True)

    def update_record(self, record_id: str, **changes: Any) -> ReplicationRecord:
        with self._lock:
            record = self._records.get(record_id)
            if record is None:
                raise KeyError(f"unknown replication record {record_id!r}")
            for key, value in changes.items():
                setattr(record, key, value)
            return record

    def latest_lag(self) -> float:
        with self._lock:
            replicated = [r for r in self._records.values() if r.state.value == "replicated"]
            if not replicated:
                return float("inf")
            return min(r.lag_seconds for r in replicated)
