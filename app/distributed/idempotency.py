from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.distributed.redis_client import AsyncRedisClient

logger = logging.getLogger(__name__)

IDEMPOTENCY_PREFIX = "dist_idempotency:"
IDEMPOTENCY_TTL = 86400


class IdempotencyGuard:
    def __init__(self, redis: AsyncRedisClient, ttl: int = IDEMPOTENCY_TTL):
        self._redis = redis
        self._ttl = ttl

    async def is_duplicate(self, idempotency_key: str) -> bool:
        if not idempotency_key:
            return False
        return await self._redis.exists(f"{IDEMPOTENCY_PREFIX}{idempotency_key}")

    async def mark_processed(self, idempotency_key: str, result: str = "") -> None:
        if not idempotency_key:
            return
        data = json.dumps({"processed_at": time.time(), "result": result})
        await self._redis.set(
            f"{IDEMPOTENCY_PREFIX}{idempotency_key}",
            data,
            ttl=self._ttl,
        )

    async def get_result(self, idempotency_key: str) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        data = await self._redis.get(f"{IDEMPOTENCY_PREFIX}{idempotency_key}")
        if data:
            return json.loads(data)
        return None

    async def try_process(self, idempotency_key: str) -> bool:
        if not idempotency_key:
            return True
        key = f"{IDEMPOTENCY_PREFIX}{idempotency_key}"
        acquired = await self._redis.eval_script(
            """local key = KEYS[1]; local value = ARGV[1]; local ttl = tonumber(ARGV[2]); local acquired = redis.call('set', key, value, 'NX', 'EX', ttl); return acquired and 1 or 0;""",  # noqa: E501
            keys=[key],
            args=[str(time.time()), str(self._ttl)],
        )
        return bool(acquired)

    async def release(self, idempotency_key: str) -> None:
        if idempotency_key:
            await self._redis.delete(f"{IDEMPOTENCY_PREFIX}{idempotency_key}")
