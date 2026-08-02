"""Cluster exception hierarchy."""


class ClusterError(Exception):
    """Base class for all cluster framework errors."""


class ClusterNotStartedError(ClusterError):
    """Operation requires the cluster manager to be running (joined)."""


class NodeAlreadyJoinedError(ClusterError):
    """The node attempted to join while already joined."""


class DiscoveryError(ClusterError):
    """Node discovery backend failure."""


class ElectionError(ClusterError):
    """Leader election failure."""


class LeadershipError(ClusterError):
    """Leadership-specific operation failure."""


class SchedulerError(ClusterError):
    """Distributed scheduler failure."""


class JobNotFoundError(SchedulerError):
    """Referenced job does not exist."""


class JobExecutionError(SchedulerError):
    """A job execution raised."""


class HealthError(ClusterError):
    """Health monitoring failure."""


class FailoverError(ClusterError):
    """Automatic failover failure."""


class AutoscaleError(ClusterError):
    """Autoscaling failure."""


class DeploymentError(ClusterError):
    """Deployment orchestration failure."""


class BackupError(ClusterError):
    """Backup failure."""


class RestoreError(ClusterError):
    """Restore failure."""


class ReplicationError(ClusterError):
    """Replication failure."""


class DRFailoverError(ClusterError):
    """Disaster-recovery failover failure."""
