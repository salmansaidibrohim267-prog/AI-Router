from __future__ import annotations

import json
import time
from typing import Any

from app.distributed.distributed_queue import DistributedTaskQueue
from app.distributed.distributed_scheduler import DistributedScheduler
from app.distributed.event_bus import DistributedEventBus
from app.distributed.lease import LeaseManager
from app.distributed.models import WorkerInfo, WorkerStatus
from app.distributed.redis_client import AsyncRedisClient
from app.distributed.worker_registry import WorkerRegistry


class RuntimeHealth:
    def __init__(
        self,
        redis: AsyncRedisClient,
        queue: DistributedTaskQueue | None = None,
        worker_registry: WorkerRegistry | None = None,
        scheduler: DistributedScheduler | None = None,
        event_bus: DistributedEventBus | None = None,
        lease_manager: LeaseManager | None = None,
    ):
        self._redis = redis
        self._queue = queue
        self._worker_registry = worker_registry
        self._scheduler = scheduler
        self._event_bus = event_bus
        self._lease_manager = lease_manager

    async def check_redis(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = await self._redis.ping()
        elapsed = (time.perf_counter() - start) * 1000
        return {"status": "ok" if ok else "error", "latency_ms": round(elapsed, 2)}

    async def check_queue(self) -> dict[str, Any]:
        if not self._queue:
            return {"status": "not_configured"}
        try:
            depth = await self._queue.get_depth()
            return {"status": "ok", "depth": depth}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def check_workers(self) -> dict[str, Any]:
        if not self._worker_registry:
            return {"status": "not_configured"}
        try:
            workers = await self._worker_registry.list_workers()
            online = sum(1 for w in workers if w.status == WorkerStatus.ONLINE)
            return {"status": "ok", "total": len(workers), "online": online}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def check_scheduler(self) -> dict[str, Any]:
        if not self._scheduler:
            return {"status": "not_configured"}
        try:
            leader = await self._scheduler.get_leader()
            is_leader = await self._scheduler.is_leader()
            return {"status": "ok", "leader": leader, "is_this_instance_leader": is_leader}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def check_event_bus(self) -> dict[str, Any]:
        if not self._event_bus:
            return {"status": "not_configured"}
        return {"status": "ok", "subscribers": self._event_bus.get_subscriber_count()}

    async def full_health(self) -> dict[str, Any]:
        redis_check = await self.check_redis()
        return {
            "status": "ok" if redis_check["status"] == "ok" else "degraded",
            "timestamp": time.time(),
            "checks": {
                "redis": redis_check,
                "queue": await self.check_queue(),
                "workers": await self.check_workers(),
                "scheduler": await self.check_scheduler(),
                "event_bus": await self.check_event_bus(),
            },
        }

    async def get_workers_list(self) -> list[dict[str, Any]]:
        if not self._worker_registry:
            return []
        workers = await self._worker_registry.list_workers()
        return [w.to_dict() for w in workers]
