from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.distributed.models import DLQEntry, DistributedTask, TaskState
from app.distributed.redis_client import AsyncRedisClient

logger = logging.getLogger(__name__)

DLQ_LIST_KEY = "dist_dlq"


class DeadLetterQueue:
    def __init__(self, redis: AsyncRedisClient, max_entries: int = 1000):
        self._redis = redis
        self._max_entries = max_entries

    async def push(self, task: DistributedTask, error: str = "", worker_id: str = "") -> None:
        entry = DLQEntry(
            task_id=task.task_id,
            original_task=task.to_dict(),
            error=error or task.error,
            retry_count=task.retry_count,
            worker_id=worker_id,
            timestamp=time.time(),
        )
        entry_json = json.dumps(entry.to_dict())
        await self._redis.lpush(DLQ_LIST_KEY, entry_json)
        length = await self._redis.llen(DLQ_LIST_KEY)
        if length > self._max_entries:
            await self._redis.rpop(DLQ_LIST_KEY)
        logger.info(f"Task {task.task_id} moved to DLQ (retries={task.retry_count}, error={error})")

    async def list_entries(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        entries = []
        for i in range(limit):
            entry_raw = await self._redis.lindex(DLQ_LIST_KEY, offset + i)
            if entry_raw:
                try:
                    entries.append(json.loads(entry_raw))
                except json.JSONDecodeError:
                    continue
            else:
                break
        return entries

    async def pop_entry(self) -> dict[str, Any] | None:
        entry = await self._redis.rpop(DLQ_LIST_KEY)
        if entry:
            try:
                return json.loads(entry)
            except json.JSONDecodeError:
                pass
        return None

    async def requeue_entry(self, entry: dict[str, Any], queue: Any) -> None:
        task_data = entry.get("original_task", {})
        if task_data:
            task = DistributedTask.from_dict(task_data)
            task.retry_count = 0
            task.state = TaskState.QUEUED
            await queue.enqueue(
                task_type=task.task_type,
                payload=task.payload,
                priority=task.priority,
                max_retries=task.max_retries,
                timeout=task.timeout,
                idempotency_key=task.idempotency_key,
            )
            logger.info(f"Task {task.task_id} requeued from DLQ")

    async def clear(self) -> None:
        await self._redis.delete(DLQ_LIST_KEY)
        logger.info("DLQ cleared")

    async def count(self) -> int:
        return await self._redis.llen(DLQ_LIST_KEY)
