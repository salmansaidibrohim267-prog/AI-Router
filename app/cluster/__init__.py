"""Cluster & High Availability framework.

Coordinator (``ClusterManager``), pluggable leader election and discovery
strategies, a distributed scheduler, health monitoring with automatic
failover, autoscaling, zero-downtime deployments, and backup/replication/
disaster recovery — all async-first with structured logging, metrics and
dependency injection via ``create_cluster_manager``.
"""

from __future__ import annotations

from .autoscale import (
    Autoscaler,
    CpuCollector,
    MemoryCollector,
    MetricCollector,
    QueueLengthCollector,
    RequestRateCollector,
    TokenThroughputCollector,
)
from .cluster import ClusterManager, create_cluster_manager
from .config import ClusterConfig
from .deployments import DeploymentManager
from .discovery import (
    ConsulDiscovery,
    DiscoveryBackend,
    DiscoveryRegistry,
    DNSDiscovery,
    EtcdDiscovery,
    KubernetesDiscovery,
    StaticDiscovery,
    create_discovery,
)
from .election import (
    ElectionRegistry,
    Elector,
    KubernetesLeaseElection,
    LeaseElection,
    RedisElection,
    create_elector,
)
from .exceptions import ClusterError
from .failover import FailoverManager
from .health import HealthMonitor
from .logging import ClusterLogger
from .metrics import ClusterMetricsTracker
from .models import (
    AutoscaleDecision,
    BackupRecord,
    BackupStatus,
    Deployment,
    DeploymentSpec,
    DeploymentState,
    DeploymentStrategy,
    HealthReport,
    Heartbeat,
    JobRun,
    JobSpec,
    JobState,
    JobType,
    NodeInfo,
    NodeRole,
    NodeState,
    RebalanceReason,
    RebalanceReport,
    ReplicationRecord,
    ReplicationState,
)
from .replication import BackupManager, DisasterRecovery, ReplicationManager
from .repository import BackupStore, JobStore, LeaseStore, NodeStore, SnapshotStore
from .scheduler import CronExpression, DistributedScheduler

__all__ = [
    "Autoscaler",
    "AutoscaleDecision",
    "BackupManager",
    "BackupRecord",
    "BackupStatus",
    "BackupStore",
    "ClusterConfig",
    "ClusterError",
    "ClusterLogger",
    "ClusterManager",
    "ClusterMetricsTracker",
    "ConsulDiscovery",
    "CpuCollector",
    "CronExpression",
    "DNSDiscovery",
    "Deployment",
    "DeploymentManager",
    "DeploymentSpec",
    "DeploymentState",
    "DeploymentStrategy",
    "DisasterRecovery",
    "DiscoveryBackend",
    "DiscoveryRegistry",
    "DistributedScheduler",
    "Elector",
    "ElectionRegistry",
    "EtcdDiscovery",
    "FailoverManager",
    "HealthMonitor",
    "HealthReport",
    "Heartbeat",
    "JobRun",
    "JobSpec",
    "JobState",
    "JobStore",
    "JobType",
    "KubernetesDiscovery",
    "KubernetesLeaseElection",
    "LeaseElection",
    "LeaseStore",
    "MemoryCollector",
    "MetricCollector",
    "NodeInfo",
    "NodeRole",
    "NodeState",
    "NodeStore",
    "QueueLengthCollector",
    "RebalanceReason",
    "RebalanceReport",
    "RedisElection",
    "ReplicationManager",
    "ReplicationRecord",
    "ReplicationState",
    "RequestRateCollector",
    "SnapshotStore",
    "StaticDiscovery",
    "TokenThroughputCollector",
    "create_cluster_manager",
    "create_discovery",
    "create_elector",
]
