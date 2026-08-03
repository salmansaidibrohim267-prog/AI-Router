"""Cluster & High Availability configuration.

Settings mirror the rest of the platform: constructor defaults plus
``from_env()`` reading ``CL_*`` environment variables.
"""

from __future__ import annotations

import os
import socket
import uuid
from typing import Any


def _default_node_id() -> str:
    host = socket.gethostname()
    suffix = uuid.uuid4().hex[:8]
    return f"node-{host}-{suffix}"


class ClusterConfig:
    """Runtime configuration for the cluster framework."""

    def __init__(self, **kwargs: Any) -> None:
        # Identity
        self.node_id: str = kwargs.pop("node_id", None) or _default_node_id()
        self.node_name: str = kwargs.pop("node_name", "") or self.node_id
        self.node_address: str = kwargs.pop("node_address", "127.0.0.1")
        self.node_port: int = int(kwargs.pop("node_port", 8000))
        self.region: str = kwargs.pop("region", "default")
        self.zone: str = kwargs.pop("zone", "default")
        self.labels: dict[str, str] = dict(kwargs.pop("labels", {}) or {})
        self.version: str = kwargs.pop("version", "1.0.0")

        # Discovery
        self.discovery_type: str = kwargs.pop("discovery_type", "static")
        self.discovery_config: dict[str, Any] = dict(kwargs.pop("discovery_config", {}) or {})

        # Leader election
        self.election_strategy: str = kwargs.pop("election_strategy", "lease")
        self.election_retry_interval: float = float(kwargs.pop("election_retry_interval", 1.0))
        self.lease_ttl: float = float(kwargs.pop("lease_ttl", 10.0))
        self.lease_renew_interval: float = float(kwargs.pop("lease_renew_interval", 2.0))

        # Health / heartbeat
        self.heartbeat_interval: float = float(kwargs.pop("heartbeat_interval", 1.0))
        self.heartbeat_timeout: float = float(kwargs.pop("heartbeat_timeout", 5.0))

        # Scheduler
        self.scheduler_interval: float = float(kwargs.pop("scheduler_interval", 0.5))
        self.scheduler_max_concurrent: int = int(kwargs.pop("scheduler_max_concurrent", 10))
        self.job_timeout: float = float(kwargs.pop("job_timeout", 30.0))

        # Autoscaling
        self.autoscale_enabled: bool = bool(kwargs.pop("autoscale_enabled", True))
        self.autoscale_interval: float = float(kwargs.pop("autoscale_interval", 2.0))
        self.autoscale_cooldown: float = float(kwargs.pop("autoscale_cooldown", 30.0))
        self.min_replicas: int = int(kwargs.pop("min_replicas", 1))
        self.max_replicas: int = int(kwargs.pop("max_replicas", 16))
        self.autoscale_factor: float = float(kwargs.pop("autoscale_factor", 1.0))
        self.scale_down_factor: float = float(kwargs.pop("scale_down_factor", 0.8))
        self.cpu_threshold: float = float(kwargs.pop("cpu_threshold", 70.0))
        self.memory_threshold: float = float(kwargs.pop("memory_threshold", 70.0))
        self.queue_threshold: float = float(kwargs.pop("queue_threshold", 100.0))
        self.request_rate_threshold: float = float(kwargs.pop("request_rate_threshold", 1000.0))
        self.token_throughput_threshold: float = float(kwargs.pop("token_throughput_threshold", 100000.0))

        # Deployments
        self.deployment_strategy: str = kwargs.pop("deployment_strategy", "rolling")
        self.deployment_batch_size: int = int(kwargs.pop("deployment_batch_size", 1))
        self.canary_percentage: float = float(kwargs.pop("canary_percentage", 10.0))
        self.deployment_timeout: float = float(kwargs.pop("deployment_timeout", 120.0))

        # Replication / DR
        self.replication_enabled: bool = bool(kwargs.pop("replication_enabled", True))
        self.replica_count: int = int(kwargs.pop("replica_count", 1))
        self.backup_dir: str = kwargs.pop("backup_dir", "/tmp/cluster-backups")
        self.backup_prune_max: int = int(kwargs.pop("backup_prune_max", 20))

        # Observability
        self.log_events: bool = bool(kwargs.pop("log_events", True))
        self.track_metrics: bool = bool(kwargs.pop("track_metrics", True))

        if kwargs:
            unknown = ", ".join(sorted(kwargs))
            raise TypeError(f"Unknown cluster config option(s): {unknown}")

    @classmethod
    def from_env(cls, **overrides: Any) -> "ClusterConfig":
        """Build config from ``CL_*`` environment variables."""
        params: dict[str, Any] = {}
        mappings = {
            "CL_NODE_ID": "node_id",
            "CL_NODE_NAME": "node_name",
            "CL_NODE_ADDRESS": "node_address",
            "CL_NODE_PORT": "node_port",
            "CL_REGION": "region",
            "CL_ZONE": "zone",
            "CL_VERSION": "version",
            "CL_DISCOVERY_TYPE": "discovery_type",
            "CL_DISCOVERY_PEERS": "discovery_peers",
            "CL_ELECTION_STRATEGY": "election_strategy",
            "CL_ELECTION_RETRY_INTERVAL": "election_retry_interval",
            "CL_LEASE_TTL": "lease_ttl",
            "CL_LEASE_RENEW_INTERVAL": "lease_renew_interval",
            "CL_HEARTBEAT_INTERVAL": "heartbeat_interval",
            "CL_HEARTBEAT_TIMEOUT": "heartbeat_timeout",
            "CL_SCHEDULER_INTERVAL": "scheduler_interval",
            "CL_SCHEDULER_MAX_CONCURRENT": "scheduler_max_concurrent",
            "CL_JOB_TIMEOUT": "job_timeout",
            "CL_AUTOSCALE_ENABLED": "autoscale_enabled",
            "CL_AUTOSCALE_INTERVAL": "autoscale_interval",
            "CL_AUTOSCALE_COOLDOWN": "autoscale_cooldown",
            "CL_MIN_REPLICAS": "min_replicas",
            "CL_MAX_REPLICAS": "max_replicas",
            "CL_CPU_THRESHOLD": "cpu_threshold",
            "CL_MEMORY_THRESHOLD": "memory_threshold",
            "CL_QUEUE_THRESHOLD": "queue_threshold",
            "CL_REQUEST_RATE_THRESHOLD": "request_rate_threshold",
            "CL_TOKEN_THROUGHPUT_THRESHOLD": "token_throughput_threshold",
            "CL_DEPLOYMENT_STRATEGY": "deployment_strategy",
            "CL_DEPLOYMENT_BATCH_SIZE": "deployment_batch_size",
            "CL_CANARY_PERCENTAGE": "canary_percentage",
            "CL_DEPLOYMENT_TIMEOUT": "deployment_timeout",
            "CL_REPLICATION_ENABLED": "replication_enabled",
            "CL_REPLICA_COUNT": "replica_count",
            "CL_BACKUP_DIR": "backup_dir",
            "CL_LOG_EVENTS": "log_events",
            "CL_TRACK_METRICS": "track_metrics",
        }
        for env, key in mappings.items():
            raw = os.environ.get(env)
            if raw is None:
                continue
            if key == "discovery_peers":
                params["discovery_config"] = {"peers": [p.strip() for p in raw.split(",") if p.strip()]}
            elif key in (
                "CL_NODE_PORT",
                "CL_SCHEDULER_MAX_CONCURRENT",
                "CL_MIN_REPLICAS",
                "CL_MAX_REPLICAS",
                "CL_REPLICA_COUNT",
                "CL_DEPLOYMENT_BATCH_SIZE",
                "CL_BACKUP_PRUNE_MAX",
            ) or key in (
                "min_replicas",
                "max_replicas",
                "replica_count",
                "deployment_batch_size",
                "backup_prune_max",
                "node_port",
                "scheduler_max_concurrent",
            ):  # noqa: E501
                params[key] = int(raw)
            elif key in ("autoscale_enabled", "replication_enabled", "log_events", "track_metrics"):
                params[key] = raw.strip().lower() in ("1", "true", "yes", "on")
            elif key in (
                "election_retry_interval",
                "lease_ttl",
                "lease_renew_interval",
                "heartbeat_interval",
                "heartbeat_timeout",
                "scheduler_interval",
                "job_timeout",
                "autoscale_interval",
                "autoscale_cooldown",
                "autoscale_factor",
                "scale_down_factor",
                "cpu_threshold",
                "memory_threshold",
                "queue_threshold",
                "request_rate_threshold",
                "token_throughput_threshold",
                "canary_percentage",
                "deployment_timeout",
            ):  # noqa: E501
                params[key] = float(raw)
            else:
                params[key] = raw
        params.update(overrides)
        return cls(**params)

    def as_dict(self) -> dict[str, Any]:
        """Plain serialisable representation (for status()/logging)."""
        result: dict[str, Any] = {}
        for name, value in vars(self).items():
            if name == "labels":
                result[name] = dict(value)
            elif isinstance(value, (str, int, float, bool)) or value is None:
                result[name] = value
            else:
                result[name] = str(value)
        result["discovery_config"] = dict(self.discovery_config)
        return result
