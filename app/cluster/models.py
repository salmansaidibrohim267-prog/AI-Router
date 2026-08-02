"""Data models for the cluster framework."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class NodeRole(str, Enum):
    LEADER = "leader"
    FOLLOWER = "follower"
    STANDBY = "standby"


class NodeState(str, Enum):
    JOINING = "joining"
    JOINED = "joined"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    SUSPECTED = "suspected"
    FAILED = "failed"
    LEAVING = "leaving"
    LEFT = "left"


class JobType(str, Enum):
    RECURRING = "recurring"
    DELAYED = "delayed"
    CRON = "cron"
    SINGLETON = "singleton"
    FAILOVER = "failover"


class JobState(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REASSIGNED = "reassigned"


class DeploymentStrategy(str, Enum):
    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"


class DeploymentState(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    DEPLOYING = "deploying"
    HEALTHY = "healthy"
    COMPLETED = "completed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackupStatus(str, Enum):
    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"


class ReplicationState(str, Enum):
    PENDING = "pending"
    REPLICATED = "replicated"
    FAILED = "failed"


class RebalanceReason(str, Enum):
    NODE_FAILED = "node_failed"
    ORPHANED_JOB = "orphaned_job"
    LEADER_LOST = "leader_lost"
    MANUAL = "manual"
    REBALANCE = "rebalance"


@dataclass
class NodeInfo:
    """Cluster member descriptor."""

    id: str
    name: str
    address: str
    port: int
    role: NodeRole = NodeRole.FOLLOWER
    state: NodeState = NodeState.JOINING
    region: str = "default"
    zone: str = "default"
    labels: dict[str, str] = field(default_factory=dict)
    version: str = "1.0.0"
    capacity: int = 1
    leader_epoch: int = 0
    joined_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "port": self.port,
            "role": self.role.value,
            "state": self.state.value,
            "region": self.region,
            "zone": self.zone,
            "labels": dict(self.labels),
            "version": self.version,
            "capacity": self.capacity,
            "leader_epoch": self.leader_epoch,
            "joined_at": self.joined_at,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NodeInfo":
        labels = dict(data.get("labels", {}) or {})
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            address=data.get("address", ""),
            port=int(data.get("port", 0)),
            role=NodeRole(data.get("role", "follower")),
            state=NodeState(data.get("state", "joining")),
            region=data.get("region", "default"),
            zone=data.get("zone", "default"),
            labels=labels,
            version=data.get("version", "1.0.0"),
            capacity=int(data.get("capacity", 1)),
            leader_epoch=int(data.get("leader_epoch", 0)),
            joined_at=float(data.get("joined_at", time.time())),
            last_seen=float(data.get("last_seen", time.time())),
        )


@dataclass
class Heartbeat:
    """Membership heartbeat payload."""

    node_id: str
    timestamp: float = field(default_factory=time.time)
    state: NodeState = NodeState.HEALTHY
    load: float = 0.0


@dataclass
class HealthReport:
    """Per-node health assessment."""

    node_id: str
    healthy: bool
    last_seen: float
    checks: dict[str, bool]
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "healthy": self.healthy,
            "last_seen": self.last_seen,
            "checks": dict(self.checks),
            "checked_at": self.checked_at,
        }


@dataclass
class JobSpec:
    """Scheduled job descriptor."""

    name: str
    type: JobType = JobType.RECURRING
    id: str = field(default_factory=lambda: generate_id("job"))
    interval: float = 60.0
    delay: float = 0.0
    cron: str = ""
    singleton: bool = False
    failover: bool = False
    owner: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    timeout: float = 30.0
    last_run: float = 0.0
    next_run: float = 0.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "interval": self.interval,
            "delay": self.delay,
            "cron": self.cron,
            "singleton": self.singleton,
            "failover": self.failover,
            "owner": self.owner,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "priority": self.priority,
            "timeout": self.timeout,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "created_at": self.created_at,
        }


@dataclass
class JobRun:
    """Record of a single job execution attempt."""

    id: str = field(default_factory=lambda: generate_id("run"))
    job_id: str = ""
    job_name: str = ""
    node_id: str = ""
    state: JobState = JobState.PENDING
    started_at: float = 0.0
    finished_at: float = 0.0
    result: Any = None
    error: str = ""
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job_name": self.job_name,
            "node_id": self.node_id,
            "state": self.state.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
        }


@dataclass
class DeploymentSpec:
    """Deployment request."""

    name: str
    version: str
    strategy: DeploymentStrategy = DeploymentStrategy.ROLLING
    previous_version: str | None = None
    batch_size: int = 1
    canary_percentage: float = 10.0
    timeout_seconds: float = 120.0
    nodes: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: generate_id("dep"))


@dataclass
class Deployment:
    """Deployment execution state."""

    spec: DeploymentSpec
    state: DeploymentState = DeploymentState.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    progress: float = 0.0
    deployed_nodes: list[str] = field(default_factory=list)
    failed_nodes: list[str] = field(default_factory=list)
    traffic: dict[str, float] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.spec.id,
            "name": self.spec.name,
            "version": self.spec.version,
            "previous_version": self.spec.previous_version,
            "strategy": self.spec.strategy.value,
            "state": self.state.value,
            "progress": self.progress,
            "deployed_nodes": list(self.deployed_nodes),
            "failed_nodes": list(self.failed_nodes),
            "traffic": dict(self.traffic),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class BackupRecord:
    """Backup metadata."""

    id: str = field(default_factory=lambda: generate_id("bkp"))
    name: str = ""
    created_at: float = field(default_factory=time.time)
    size: int = 0
    checksum: str = ""
    entries: int = 0
    status: BackupStatus = BackupStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    restored_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "size": self.size,
            "checksum": self.checksum,
            "entries": self.entries,
            "status": self.status.value,
            "metadata": dict(self.metadata),
            "restored_at": self.restored_at,
        }


@dataclass
class ReplicationRecord:
    """Snapshot replication record."""

    id: str = field(default_factory=lambda: generate_id("rep"))
    snapshot_id: str = ""
    replica_id: str = ""
    state: ReplicationState = ReplicationState.PENDING
    lag_seconds: float = 0.0
    replicated_at: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "replica_id": self.replica_id,
            "state": self.state.value,
            "lag_seconds": self.lag_seconds,
            "replicated_at": self.replicated_at,
            "error": self.error,
        }


@dataclass
class AutoscaleDecision:
    """Result of one autoscaler evaluation."""

    component: str
    metric: str
    current: float
    threshold: float
    desired: int
    previous: int
    reason: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "metric": self.metric,
            "current": self.current,
            "threshold": self.threshold,
            "desired": self.desired,
            "previous": self.previous,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class RebalanceReport:
    """Result of a rebalance() call."""

    reason: RebalanceReason
    reassigned_jobs: int = 0
    orphaned_jobs: int = 0
    failed_nodes: list[str] = field(default_factory=list)
    elected_leader: bool = False
    leader: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason.value,
            "reassigned_jobs": self.reassigned_jobs,
            "orphaned_jobs": self.orphaned_jobs,
            "failed_nodes": list(self.failed_nodes),
            "elected_leader": self.elected_leader,
            "leader": self.leader,
            "timestamp": self.timestamp,
        }
