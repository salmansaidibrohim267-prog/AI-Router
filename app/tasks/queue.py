from __future__ import annotations

from typing import Any

from app.tasks.storage import TaskStorage
from app.tasks.status import TaskState


class TaskQueue:
    def __init__(self, storage: TaskStorage | None = None):
        self._storage = storage or TaskStorage()

    def create_task(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        max_retries: int = 3,
        timeout: int = 300,
        session_id: str = "",
    ) -> dict[str, Any]:
        return self._storage.create(
            task_type=task_type,
            payload=payload,
            priority=priority,
            max_retries=max_retries,
            timeout=timeout,
            session_id=session_id,
        )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._storage.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        task = self._storage.get(task_id)
        if task and task.get("state") in (TaskState.QUEUED.value, TaskState.RUNNING.value):
            self._storage.update(task_id, {"state": TaskState.CANCELLED.value})
            return True
        return False

    def delete_task(self, task_id: str) -> None:
        self._storage.delete(task_id)

    def list_tasks(
        self,
        state: str = "",
        task_type: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._storage.list_tasks(
            state=state, task_type=task_type, limit=limit, offset=offset
        )

    def dequeue(self) -> dict[str, Any] | None:
        return self._storage.dequeue()

    def get_depth(self) -> dict[str, int]:
        return self._storage.get_queue_depth()

    def add_timeline_event(self, task_id: str, event: dict[str, Any]) -> None:
        self._storage.add_timeline_event(task_id, event)

    def set_graph(self, task_id: str, graph: dict[str, Any]) -> None:
        self._storage.set_graph(task_id, graph)

    def fail_task(self, task_id: str, error: str) -> None:
        task = self._storage.get(task_id)
        if task:
            retry_count = task.get("retry_count", 0)
            max_retries = task.get("max_retries", 3)
            if retry_count < max_retries:
                self._storage.update(task_id, {
                    "state": TaskState.RETRYING.value,
                    "retry_count": retry_count + 1,
                    "error": error,
                })
            else:
                self._storage.update(task_id, {
                    "state": TaskState.FAILED.value,
                    "completed_at": __import__("time").time(),
                    "error": error,
                })

    def complete_task(self, task_id: str, result: Any = None) -> None:
        self._storage.update(task_id, {
            "state": TaskState.COMPLETED.value,
            "completed_at": __import__("time").time(),
            "result": result,
            "progress": 1.0,
        })
