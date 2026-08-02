from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from app.distributed.models import DistributedTask, TaskState
from app.distributed.redis_client import AsyncRedisClient

logger = logging.getLogger(__name__)

TASK_PREFIX = "dist_task:"
QUEUE_PREFIX = "dist_queue:"
DELAYED_PREFIX = "dist_delayed:"
LEASE_PREFIX = "dist_lease:"
TASK_TTL = 86400


class DistributedTaskQueue:
    def __init__(self, redis: AsyncRedisClient, visibility_timeout: int = 60):
        self._redis = redis
        self._visibility_timeout = visibility_timeout

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        max_retries: int = 3,
        timeout: int = 300,
        idempotency_key: str = "",
        delay: int = 0,
        session_id: str = "",
    ) -> DistributedTask:
        task_id = uuid.uuid4().hex[:16]
        now = time.time()
        task = DistributedTask(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
            priority=priority,
            max_retries=max_retries,
            timeout=timeout,
            idempotency_key=idempotency_key,
            session_id=session_id,
            created_at=now,
            updated_at=now,
        )
        task_data = json.dumps(task.to_dict())
        await self._redis.set(f"{TASK_PREFIX}{task_id}", task_data, ttl=TASK_TTL)

        if delay > 0:
            exec_at = now + delay
            await self._redis.zadd(DELAYED_PREFIX, exec_at, task_id)
            await self._redis.set(f"{TASK_PREFIX}{task_id}:delayed", "1", ttl=delay + 60)
        else:
            queue_key = f"{QUEUE_PREFIX}{priority}"
            await self._redis.lpush(queue_key, task_id)

        return task

    async def dequeue(self) -> DistributedTask | None:
        for priority in range(10, -1, -1):
            queue_key = f"{QUEUE_PREFIX}{priority}"
            result = await self._redis.brpop(queue_key, timeout=1)
            if result:
                _, task_id = result
                task = await self._get_task(task_id)
                if task and task.state == TaskState.QUEUED:
                    lease_id = uuid.uuid4().hex[:12]
                    task.state = TaskState.RUNNING
                    task.lease_id = lease_id
                    task.lease_expires_at = time.time() + self._visibility_timeout
                    task.updated_at = time.time()
                    await self._save_task(task)
                    lease_data = json.dumps({
                        "task_id": task_id,
                        "lease_id": lease_id,
                        "expires_at": task.lease_expires_at,
                    })
                    await self._redis.set(
                        f"{LEASE_PREFIX}{task_id}",
                        lease_data,
                        ttl=self._visibility_timeout + 10,
                    )
                    return task
                if task:
                    await self._requeue(task_id, task.priority)
        return None

    async def ack(self, task_id: str) -> None:
        task = await self._get_task(task_id)
        if task:
            task.state = TaskState.COMPLETED
            task.updated_at = time.time()
            await self._save_task(task)
        await self._redis.delete(f"{LEASE_PREFIX}{task_id}")

    async def nack(self, task_id: str, error: str = "", requeue: bool = True) -> None:
        task = await self._get_task(task_id)
        if not task:
            return
        task.retry_count += 1
        task.error = error
        task.updated_at = time.time()
        task.lease_id = ""
        task.lease_expires_at = 0.0

        if requeue and task.retry_count < task.max_retries:
            task.state = TaskState.RETRYING
            await self._save_task(task)
            delay = min(2 ** task.retry_count, 60)
            exec_at = time.time() + delay
            await self._redis.zadd(DELAYED_PREFIX, exec_at, task_id)
            logger.info(f"Task {task_id} retry {task.retry_count}/{task.max_retries} in {delay}s")
        else:
            task.state = TaskState.FAILED
            await self._save_task(task)

        await self._redis.delete(f"{LEASE_PREFIX}{task_id}")

    async def get_task(self, task_id: str) -> DistributedTask | None:
        return await self._get_task(task_id)

    async def get_depth(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for priority in range(10, -1, -1):
            key = f"{QUEUE_PREFIX}{priority}"
            length = await self._redis.llen(key)
            counts[f"priority_{priority}"] = length
        delayed_count = await self._redis.zcard(DELAYED_PREFIX)
        lease_keys = await self._redis.scan(f"{LEASE_PREFIX}*")
        counts["delayed"] = delayed_count
        counts["running"] = len(lease_keys)
        return counts

    async def requeue_expired(self) -> int:
        now = time.time()
        lease_keys = await self._redis.scan(f"{LEASE_PREFIX}*")
        count = 0
        for key in lease_keys:
            task_id = key.replace(LEASE_PREFIX, "")
            lease_data = await self._redis.get(key)
            if not lease_data:
                continue
            try:
                lease = json.loads(lease_data)
            except json.JSONDecodeError:
                await self._redis.delete(key)
                continue
            if lease.get("expires_at", 0) < now:
                task = await self._get_task(task_id)
                if task and task.state == TaskState.RUNNING:
                    task.state = TaskState.QUEUED
                    task.lease_id = ""
                    task.lease_expires_at = 0.0
                    task.updated_at = now
                    await self._save_task(task)
                    await self._requeue(task_id, task.priority)
                    await self._redis.delete(key)
                    count += 1
        return count

    async def process_delayed(self) -> int:
        return await self._redis.atomic_process_delayed(
            DELAYED_PREFIX,
            TASK_PREFIX,
            QUEUE_PREFIX,
            time.time(),
            TASK_TTL,
        )

    async def move_to_dlq(self, task_id: str, error: str = "") -> None:
        task = await self._get_task(task_id)
        if not task:
            return
        dlq_entry = {
            "task_id": task_id,
            "original_task": task.to_dict(),
            "error": error or task.error,
            "retry_count": task.retry_count,
            "timestamp": time.time(),
        }
        await self._redis.lpush("dist_dlq", json.dumps(dlq_entry))
        await self._redis.delete(f"{TASK_PREFIX}{task_id}")
        await self._redis.delete(f"{LEASE_PREFIX}{task_id}")

    async def list_dlq(self, limit: int = 50) -> list[dict[str, Any]]:
        entries = []
        for _ in range(limit):
            entry = await self._redis.lpop("dist_dlq")
            if entry:
                try:
                    entries.append(json.loads(entry))
                except json.JSONDecodeError:
                    continue
            else:
                break
        for entry in reversed(entries):
            await self._redis.lpush("dist_dlq", json.dumps(entry))
        return entries

    async def _get_task(self, task_id: str) -> DistributedTask | None:
        data = await self._redis.get(f"{TASK_PREFIX}{task_id}")
        if not data:
            return None
        return DistributedTask.from_dict(json.loads(data))

    async def _save_task(self, task: DistributedTask) -> None:
        await self._redis.set(f"{TASK_PREFIX}{task.task_id}", json.dumps(task.to_dict()), ttl=TASK_TTL)

    async def _requeue(self, task_id: str, priority: int) -> None:
        queue_key = f"{QUEUE_PREFIX}{priority}"
        await self._redis.lpush(queue_key, task_id)
