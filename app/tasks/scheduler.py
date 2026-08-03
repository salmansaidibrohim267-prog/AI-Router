from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from app.tasks.queue import TaskQueue

logger = logging.getLogger(__name__)

ScheduleHandler = Callable[[], dict[str, Any] | None]


class TaskScheduler:
    def __init__(self, queue: TaskQueue):
        self._queue = queue
        self._jobs: dict[str, dict[str, Any]] = {}
        self._running = False

    def add_job(
        self,
        job_id: str,
        task_type: str,
        payload: dict[str, Any],
        interval: float,
        max_runs: int = 0,
    ) -> None:
        self._jobs[job_id] = {
            "task_type": task_type,
            "payload": payload,
            "interval": interval,
            "max_runs": max_runs,
            "run_count": 0,
            "last_run": 0,
            "enabled": True,
        }

    def remove_job(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            {
                "job_id": jid,
                **job,
            }
            for jid, job in self._jobs.items()
        ]

    async def start(self) -> None:
        self._running = True
        logger.info(f"Scheduler started with {len(self._jobs)} jobs")
        while self._running:
            now = time.time()
            for _, job in list(self._jobs.items()):
                if not job["enabled"]:
                    continue
                if job["max_runs"] > 0 and job["run_count"] >= job["max_runs"]:
                    continue
                if now - job["last_run"] >= job["interval"]:
                    self._queue.create_task(
                        task_type=job["task_type"],
                        payload=job["payload"],
                    )
                    job["run_count"] += 1
                    job["last_run"] = now
            await asyncio.sleep(1)

    async def stop(self) -> None:
        self._running = False
        logger.info("Scheduler stopped")
