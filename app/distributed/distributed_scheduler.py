from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable

from app.distributed.redis_client import AsyncRedisClient

logger = logging.getLogger(__name__)

SCHEDULER_LOCK_KEY = "dist_scheduler:lock"
SCHEDULER_LEADER_KEY = "dist_scheduler:leader"
SCHEDULER_LOCK_TTL = 10
HEARTBEAT_INTERVAL = 3


class DistributedScheduler:
    def __init__(
        self,
        redis: AsyncRedisClient,
        instance_id: str = "",
        lock_ttl: int = SCHEDULER_LOCK_TTL,
    ):
        self._redis = redis
        self._instance_id = instance_id or f"scheduler_{uuid.uuid4().hex[:8]}"
        self._lock_ttl = lock_ttl
        self._running = False
        self._is_leader = False
        self._jobs: dict[str, dict[str, Any]] = {}
        self._on_leader_change: Callable[[bool], Any] | None = None

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
        }

    def remove_job(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [{"job_id": jid, **job} for jid, job in self._jobs.items()]

    def on_leader_change(self, callback: Callable[[bool], Any]) -> None:
        self._on_leader_change = callback

    async def start(self) -> None:
        self._running = True
        self._leader_task = asyncio.create_task(self._leader_election_loop())
        self._job_task = asyncio.create_task(self._job_execution_loop())
        logger.info(f"Scheduler instance {self._instance_id} started")

    async def stop(self) -> None:
        self._running = False
        if self._is_leader:
            await self._release_leadership()
        if hasattr(self, "_leader_task"):
            self._leader_task.cancel()
            try:
                await self._leader_task
            except asyncio.CancelledError:
                pass
        if hasattr(self, "_job_task"):
            self._job_task.cancel()
            try:
                await self._job_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Scheduler instance {self._instance_id} stopped")

    async def is_leader(self) -> bool:
        return self._is_leader

    async def get_leader(self) -> str:
        leader = await self._redis.get(SCHEDULER_LEADER_KEY)
        return leader or ""

    async def _leader_election_loop(self) -> None:
        while self._running:
            try:
                acquired = await self._redis.acquire_lock(
                    SCHEDULER_LOCK_KEY,
                    ttl=self._lock_ttl,
                    owner=self._instance_id,
                )
                if acquired and not self._is_leader:
                    self._is_leader = True
                    await self._redis.set(
                        SCHEDULER_LEADER_KEY,
                        self._instance_id,
                        ttl=self._lock_ttl,
                    )
                    logger.info(f"Leader elected: {self._instance_id}")
                    if self._on_leader_change:
                        result = self._on_leader_change(True)
                        if asyncio.iscoroutine(result):
                            await result
                elif not acquired and self._is_leader:
                    self._is_leader = False
                    logger.info(f"Lost leadership: {self._instance_id}")
                    if self._on_leader_change:
                        result = self._on_leader_change(False)
                        if asyncio.iscoroutine(result):
                            await result
                elif not acquired:
                    leader = await self._redis.get(SCHEDULER_LEADER_KEY)
                    if not leader:
                        await self._redis.set(
                            SCHEDULER_LEADER_KEY,
                            "unknown",
                            ttl=self._lock_ttl,
                        )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Leader election error: {e}")
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _job_execution_loop(self) -> None:
        while self._running:
            try:
                if self._is_leader:
                    now = time.time()
                    for job_id, job in list(self._jobs.items()):
                        if job["max_runs"] > 0 and job["run_count"] >= job["max_runs"]:
                            continue
                        if now - job["last_run"] >= job["interval"]:
                            try:
                                from app.memory.store import SQLiteStore
                                from app.tasks.queue import TaskQueue
                                from app.tasks.storage import TaskStorage

                                store = SQLiteStore()
                                storage = TaskStorage(store)
                                queue = TaskQueue(storage)
                                queue.create_task(
                                    task_type=job["task_type"],
                                    payload=job["payload"],
                                )
                                job["run_count"] += 1
                                job["last_run"] = now
                                logger.debug(f"Job {job_id} triggered")
                            except Exception as e:
                                logger.error(f"Job {job_id} execution error: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Job execution loop error: {e}")
            await asyncio.sleep(1)

    async def _release_leadership(self) -> None:
        await self._redis.release_lock(
            SCHEDULER_LOCK_KEY,
            owner=self._instance_id,
        )
        self._is_leader = False
