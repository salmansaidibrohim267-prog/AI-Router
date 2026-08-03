from __future__ import annotations

import json
import logging
import time
import uuid

from app.distributed.models import LeaseInfo
from app.distributed.redis_client import AsyncRedisClient

logger = logging.getLogger(__name__)

LEASE_PREFIX = "dist_lease:"


class LeaseManager:
    def __init__(self, redis: AsyncRedisClient, default_timeout: float = 60.0):
        self._redis = redis
        self._default_timeout = default_timeout

    async def acquire(self, task_id: str, worker_id: str, timeout: float = 0) -> LeaseInfo | None:
        if timeout <= 0:
            timeout = self._default_timeout
        lease_id = uuid.uuid4().hex[:12]
        now = time.time()
        lease = LeaseInfo(
            task_id=task_id,
            worker_id=worker_id,
            lease_id=lease_id,
            acquired_at=now,
            expires_at=now + timeout,
            timeout=timeout,
        )
        lease_key = f"{LEASE_PREFIX}{task_id}"
        lease_json = json.dumps(lease.to_dict())
        acquired = await self._redis.eval_script(
            """local lease_key = KEYS[1]; local lease_data = ARGV[1]; local timeout = tonumber(ARGV[2]); local now = tonumber(ARGV[3]); local existing = redis.call('get', lease_key); if not existing then redis.call('setex', lease_key, timeout + 10, lease_data); return 1; end; local el = cjson.decode(existing); if el.expires_at < now then redis.call('del', lease_key); redis.call('setex', lease_key, timeout + 10, lease_data); return 1; end; return 0;""",  # noqa: E501
            keys=[lease_key],
            args=[lease_json, str(int(timeout) + 10), str(now)],
        )
        if acquired:
            logger.debug(f"Lease acquired: task={task_id} worker={worker_id} lease={lease_id}")
            return lease
        return None

    async def release(self, task_id: str, worker_id: str = "") -> bool:
        lease_key = f"{LEASE_PREFIX}{task_id}"
        existing = await self._redis.get(lease_key)
        if not existing:
            return False
        lease_data = json.loads(existing)
        if worker_id and lease_data.get("worker_id") != worker_id:
            return False
        await self._redis.delete(lease_key)
        logger.debug(f"Lease released: task={task_id}")
        return True

    async def renew(self, task_id: str, worker_id: str, timeout: float = 0) -> bool:
        if timeout <= 0:
            timeout = self._default_timeout
        lease_key = f"{LEASE_PREFIX}{task_id}"
        existing = await self._redis.get(lease_key)
        if not existing:
            return False
        lease_data = json.loads(existing)
        if lease_data.get("worker_id") != worker_id:
            return False
        lease_data["expires_at"] = time.time() + timeout
        await self._redis.set(lease_key, json.dumps(lease_data), ttl=int(timeout) + 10)
        logger.debug(f"Lease renewed: task={task_id} worker={worker_id}")
        return True

    async def is_expired(self, task_id: str) -> bool:
        lease_key = f"{LEASE_PREFIX}{task_id}"
        existing = await self._redis.get(lease_key)
        if not existing:
            return True
        lease_data = json.loads(existing)
        return lease_data.get("expires_at", 0) < time.time()

    async def get_lease(self, task_id: str) -> LeaseInfo | None:
        lease_key = f"{LEASE_PREFIX}{task_id}"
        existing = await self._redis.get(lease_key)
        if not existing:
            return None
        data = json.loads(existing)
        return LeaseInfo(**data)

    async def get_active_leases(self) -> list[LeaseInfo]:
        keys = await self._redis.keys(f"{LEASE_PREFIX}*")
        leases = []
        now = time.time()
        for key in keys:
            data = await self._redis.get(key)
            if data:
                lease_data = json.loads(data)
                if lease_data.get("expires_at", 0) > now:
                    leases.append(LeaseInfo(**lease_data))
        return leases

    async def release_expired(self) -> int:
        now = time.time()
        keys = await self._redis.keys(f"{LEASE_PREFIX}*")
        count = 0
        for key in keys:
            data = await self._redis.get(key)
            if data:
                lease_data = json.loads(data)
                if lease_data.get("expires_at", 0) < now:
                    await self._redis.delete(key)
                    count += 1
        return count
