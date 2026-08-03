from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.orchestration.models import OrchestrationRequest
from app.orchestration.orchestrator import Orchestrator
from app.tasks.queue import TaskQueue

logger = logging.getLogger(__name__)


class TaskWorker:
    def __init__(
        self,
        queue: TaskQueue,
        orchestrator: Orchestrator,
        worker_id: str = "",
        poll_interval: float = 1.0,
        max_concurrent: int = 5,
    ):
        self._queue = queue
        self._orchestrator = orchestrator
        self._worker_id = worker_id or f"worker_{id(self):x}"
        self._poll_interval = poll_interval
        self._max_concurrent = max_concurrent
        self._running = False
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_tasks: set[str] = set()

    async def start(self) -> None:
        self._running = True
        logger.info(f"Worker {self._worker_id} started (max_concurrent={self._max_concurrent})")
        while self._running:
            try:
                task = self._queue.dequeue()
                if task:
                    asyncio.create_task(self._process_task(task))
                else:
                    await asyncio.sleep(self._poll_interval)
            except Exception as e:
                logger.error(f"Worker {self._worker_id} error: {e}")
                await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        self._running = False
        logger.info(f"Worker {self._worker_id} stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def active_count(self) -> int:
        return len(self._active_tasks)

    async def _process_task(self, task: dict[str, Any]) -> None:
        task_id = task.get("task_id", "")
        self._active_tasks.add(task_id)

        async with self._semaphore:
            try:
                await self._execute_task(task)
            except Exception as e:
                logger.exception(f"Task {task_id} failed: {e}")
                self._queue.fail_task(task_id, str(e))
            finally:
                self._active_tasks.discard(task_id)

    async def _execute_task(self, task: dict[str, Any]) -> None:
        task_id = task.get("task_id", "")
        payload = task.get("payload", {})
        task_type = task.get("type", "")

        self._queue.add_timeline_event(
            task_id,
            {
                "event": "task_started",
                "timestamp": time.time(),
                "worker": self._worker_id,
            },
        )

        try:
            async with asyncio.timeout(task.get("timeout", 300)):
                if task_type in ("orchestrate", "chat"):
                    req = OrchestrationRequest(**payload)
                    result = await self._orchestrator.orchestrate(req)
                    self._queue.complete_task(task_id, result.model_dump())
                else:
                    self._queue.fail_task(task_id, f"Unknown task type: {task_type}")
                    return
        except asyncio.TimeoutError:
            self._queue.fail_task(task_id, "Task timed out")
            return

        self._queue.add_timeline_event(
            task_id,
            {
                "event": "task_completed",
                "timestamp": time.time(),
                "worker": self._worker_id,
            },
        )

    def get_status(self) -> dict[str, Any]:
        return {
            "worker_id": self._worker_id,
            "running": self._running,
            "active_tasks": self.active_count,
            "max_concurrent": self._max_concurrent,
            "poll_interval": self._poll_interval,
        }
