from __future__ import annotations

import time
import uuid
from typing import Any

from app.memory.store import MemoryStore, SQLiteStore
from app.tasks.status import TaskState


class TaskStorage:
    def __init__(self, store: MemoryStore | None = None):
        self._store = store or SQLiteStore()

    def create(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        max_retries: int = 3,
        timeout: int = 300,
        session_id: str = "",
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex[:16]
        now = time.time()
        task = {
            "task_id": task_id,
            "type": task_type,
            "payload": payload,
            "state": TaskState.QUEUED.value,
            "priority": priority,
            "max_retries": max_retries,
            "retry_count": 0,
            "timeout": timeout,
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "started_at": 0,
            "completed_at": 0,
            "error": "",
            "progress": 0.0,
            "result": None,
            "timeline": [],
            "graph": None,
        }
        self._store.set(f"task:{task_id}", task)
        self._store.set(f"task_queue:{task_id}", {
            "type": task_type,
            "priority": priority,
            "state": TaskState.QUEUED.value,
            "created_at": now,
        })
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        return self._store.get(f"task:{task_id}")

    def update(self, task_id: str, updates: dict[str, Any]) -> None:
        task = self._store.get(f"task:{task_id}")
        if task:
            task.update(updates)
            task["updated_at"] = time.time()
            self._store.set(f"task:{task_id}", task)

    def delete(self, task_id: str) -> None:
        self._store.delete(f"task:{task_id}")
        self._store.delete(f"task_queue:{task_id}")

    def list_tasks(
        self,
        state: str = "",
        task_type: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        all_tasks = []
        for key in self._store.keys("task:*"):
            task = self._store.get(key)
            if task and "task_id" in task:
                all_tasks.append(task)
        if state:
            all_tasks = [t for t in all_tasks if t.get("state") == state]
        if task_type:
            all_tasks = [t for t in all_tasks if t.get("type") == task_type]
        all_tasks.sort(key=lambda t: (-t.get("priority", 0), t.get("created_at", 0)))
        return all_tasks[offset:offset + limit]

    def dequeue(self) -> dict[str, Any] | None:
        queue_keys = self._store.keys("task_queue:*")
        candidates = []
        for key in queue_keys:
            entry = self._store.get(key)
            if entry and entry.get("state") == TaskState.QUEUED.value:
                entry["key"] = key
                candidates.append(entry)
        if not candidates:
            return None
        candidates.sort(key=lambda e: (-e.get("priority", 0), e.get("created_at", 0)))
        chosen = candidates[0]
        task_id = chosen["key"].split(":", 1)[1]
        task = self._store.get(f"task:{task_id}")
        if task:
            task["state"] = TaskState.RUNNING.value
            task["started_at"] = time.time()
            self.update(task_id, {"state": TaskState.RUNNING.value, "started_at": task["started_at"]})
            self._store.set(f"task_queue:{task_id}", {
                "type": task.get("type", ""),
                "priority": task.get("priority", 0),
                "state": TaskState.RUNNING.value,
                "created_at": task.get("created_at", 0),
            })
        return task

    def get_queue_depth(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key in self._store.keys("task:*"):
            task = self._store.get(key)
            if task:
                s = task.get("state", "unknown")
                counts[s] = counts.get(s, 0) + 1
        return counts

    def add_timeline_event(self, task_id: str, event: dict[str, Any]) -> None:
        task = self._store.get(f"task:{task_id}")
        if task:
            timeline = task.get("timeline", [])
            timeline.append(event)
            self.update(task_id, {"timeline": timeline})

    def set_graph(self, task_id: str, graph: dict[str, Any]) -> None:
        self.update(task_id, {"graph": graph})

    def clear(self) -> None:
        for key in self._store.keys("task:*"):
            self._store.delete(key)
        for key in self._store.keys("task_queue:*"):
            self._store.delete(key)
