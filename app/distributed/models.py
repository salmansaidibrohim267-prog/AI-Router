from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class WorkerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    DRAINING = "draining"


@dataclass
class DistributedTask:
    task_id: str = ""
    task_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    state: TaskState = TaskState.QUEUED
    priority: int = 0
    max_retries: int = 3
    retry_count: int = 0
    timeout: int = 300
    session_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    lease_id: str = ""
    lease_expires_at: float = 0.0
    error: str = ""
    idempotency_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "payload": self.payload,
            "state": self.state.value,
            "priority": self.priority,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "timeout": self.timeout,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "lease_id": self.lease_id,
            "lease_expires_at": self.lease_expires_at,
            "error": self.error,
            "idempotency_key": self.idempotency_key,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DistributedTask:
        return DistributedTask(
            task_id=data.get("task_id", ""),
            task_type=data.get("task_type", ""),
            payload=data.get("payload", {}),
            state=TaskState(data.get("state", "queued")),
            priority=data.get("priority", 0),
            max_retries=data.get("max_retries", 3),
            retry_count=data.get("retry_count", 0),
            timeout=data.get("timeout", 300),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
            lease_id=data.get("lease_id", ""),
            lease_expires_at=data.get("lease_expires_at", 0.0),
            error=data.get("error", ""),
            idempotency_key=data.get("idempotency_key", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class LeaseInfo:
    task_id: str
    worker_id: str
    lease_id: str = ""
    acquired_at: float = 0.0
    expires_at: float = 0.0
    timeout: float = 60.0

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "worker_id": self.worker_id,
            "lease_id": self.lease_id,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "timeout": self.timeout,
        }


@dataclass
class WorkerInfo:
    worker_id: str
    hostname: str = ""
    pid: int = 0
    version: str = ""
    status: WorkerStatus = WorkerStatus.ONLINE
    started_at: float = 0.0
    last_heartbeat: float = 0.0
    current_tasks: int = 0
    max_concurrent: int = 5
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "hostname": self.hostname,
            "pid": self.pid,
            "version": self.version,
            "status": self.status.value,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "current_tasks": self.current_tasks,
            "max_concurrent": self.max_concurrent,
            "tags": self.tags,
        }


@dataclass
class EventMessage:
    event_id: str = ""
    event_type: str = ""
    timestamp: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id or uuid.uuid4().hex[:12],
            "event_type": self.event_type,
            "timestamp": self.timestamp or time.time(),
            "payload": self.payload,
            "metadata": self.metadata,
        }


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    multiplier: float = 2.0
    jitter: float = 0.1

    def get_delay(self, attempt: int) -> float:
        import random

        delay = min(self.base_delay * (self.multiplier**attempt), self.max_delay)
        jitter_amount = delay * self.jitter
        return delay + random.uniform(-jitter_amount, jitter_amount)


@dataclass
class DLQEntry:
    task_id: str
    original_task: dict[str, Any]
    error: str = ""
    retry_count: int = 0
    worker_id: str = ""
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "original_task": self.original_task,
            "error": self.error,
            "retry_count": self.retry_count,
            "worker_id": self.worker_id,
            "timestamp": self.timestamp or time.time(),
            "metadata": self.metadata,
        }
