from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time

from app.distributed.models import WorkerInfo, WorkerStatus
from app.distributed.redis_client import AsyncRedisClient

logger = logging.getLogger(__name__)

WORKER_PREFIX = "dist_worker:"
WORKER_HEARTBEAT_PREFIX = "dist_heartbeat:"
HEARTBEAT_TTL = 15


class WorkerRegistry:
    def __init__(self, redis: AsyncRedisClient, heartbeat_interval: int = 5):
        self._redis = redis
        self._heartbeat_interval = heartbeat_interval
        self._worker_id = ""
        self._hostname = socket.gethostname()
        self._pid = os.getpid()
        self._running = False

    async def register(
        self,
        worker_id: str,
        max_concurrent: int = 5,
        tags: dict[str, str] | None = None,
    ) -> None:
        self._worker_id = worker_id
        now = time.time()
        info = WorkerInfo(
            worker_id=worker_id,
            hostname=self._hostname,
            pid=self._pid,
            version=self._get_version(),
            status=WorkerStatus.ONLINE,
            started_at=now,
            last_heartbeat=now,
            max_concurrent=max_concurrent,
            tags=tags or {},
        )
        await self._redis.set(
            f"{WORKER_PREFIX}{worker_id}",
            json.dumps(info.to_dict()),
            ttl=86400,
        )
        logger.info(f"Worker registered: {worker_id} ({self._hostname}:{self._pid})")

    async def unregister(self) -> None:
        if not self._worker_id:
            return
        worker = await self.get_worker(self._worker_id)
        if worker:
            worker.status = WorkerStatus.OFFLINE
            await self._redis.set(
                f"{WORKER_PREFIX}{self._worker_id}",
                json.dumps(worker.to_dict()),
                ttl=86400,
            )
        await self._redis.delete(f"{WORKER_HEARTBEAT_PREFIX}{self._worker_id}")
        logger.info(f"Worker unregistered: {self._worker_id}")

    async def heartbeat(self) -> None:
        if not self._worker_id:
            return
        now = time.time()
        await self._redis.set(
            f"{WORKER_HEARTBEAT_PREFIX}{self._worker_id}",
            json.dumps({"last_heartbeat": now, "worker_id": self._worker_id}),
            ttl=HEARTBEAT_TTL,
        )
        worker = await self.get_worker(self._worker_id)
        if worker:
            worker.last_heartbeat = now
            await self._redis.set(
                f"{WORKER_PREFIX}{self._worker_id}",
                json.dumps(worker.to_dict()),
                ttl=86400,
            )

    async def start_heartbeat_loop(self) -> None:
        self._running = True
        while self._running:
            try:
                await self.heartbeat()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(self._heartbeat_interval)

    async def stop_heartbeat(self) -> None:
        self._running = False

    async def get_worker(self, worker_id: str) -> WorkerInfo | None:
        data = await self._redis.get(f"{WORKER_PREFIX}{worker_id}")
        if not data:
            return None
        return WorkerInfo(**json.loads(data))

    async def list_workers(self) -> list[WorkerInfo]:
        keys = await self._redis.keys(f"{WORKER_PREFIX}*")
        workers = []
        for key in keys:
            data = await self._redis.get(key)
            if data:
                worker = WorkerInfo(**json.loads(data))
                if worker.status != WorkerStatus.DRAINING:
                    worker.status = await self._check_status(worker.worker_id)
                workers.append(worker)
        return workers

    async def get_online_count(self) -> int:
        workers = await self.list_workers()
        return sum(1 for w in workers if w.status == WorkerStatus.ONLINE)

    async def set_draining(self, worker_id: str) -> None:
        worker = await self.get_worker(worker_id)
        if worker:
            worker.status = WorkerStatus.DRAINING
            await self._redis.set(
                f"{WORKER_PREFIX}{worker_id}",
                json.dumps(worker.to_dict()),
                ttl=86400,
            )

    async def _check_status(self, worker_id: str) -> WorkerStatus:
        heartbeat = await self._redis.get(f"{WORKER_HEARTBEAT_PREFIX}{worker_id}")
        if not heartbeat:
            return WorkerStatus.OFFLINE
        data = json.loads(heartbeat)
        elapsed = time.time() - data.get("last_heartbeat", 0)
        if elapsed > HEARTBEAT_TTL * 2:
            return WorkerStatus.OFFLINE
        return WorkerStatus.ONLINE

    def _get_version(self) -> str:
        try:
            from app import __version__

            return __version__
        except (ImportError, AttributeError):
            return "0.0.0"
