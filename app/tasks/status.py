from __future__ import annotations

from enum import Enum


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskStatus:
    def __init__(
        self,
        state: TaskState = TaskState.QUEUED,
        progress: float = 0.0,
        error: str = "",
        retry_count: int = 0,
    ):
        self.state = state
        self.progress = progress
        self.error = error
        self.retry_count = retry_count

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "progress": self.progress,
            "error": self.error,
            "retry_count": self.retry_count,
        }
