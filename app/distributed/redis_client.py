from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# Lua scripts for atomic Redis operations

ATOMIC_DEQUEUE_LUA = """
local queue_key = KEYS[1]
local task_prefix = KEYS[2]
local lease_prefix = KEYS[3]
local now = tonumber(ARGV[1])
local visibility_timeout = tonumber(ARGV[2])
local lease_ttl = tonumber(ARGV[3])
local task_ttl = tonumber(ARGV[4])

local result = redis.call('brpop', queue_key, 1)
if not result then
    return nil
end
local task_id = result[2]
local task_key = task_prefix .. task_id
local task_json = redis.call('get', task_key)
if not task_json then
    return nil
end
local task = cjson.decode(task_json)
if task.state ~= 'queued' then
    redis.call('lpush', queue_key, task_id)
    return nil
end
task.state = 'running'
task.lease_id = task_id .. '_' .. tostring(now)
task.lease_expires_at = now + visibility_timeout
task.updated_at = now
redis.call('setex', task_key, task_ttl, cjson.encode(task))
redis.call('setex', lease_prefix .. task_id, lease_ttl, cjson.encode({
    task_id = task_id,
    lease_id = task.lease_id,
    expires_at = task.lease_expires_at
}))
return cjson.encode(task)
"""

ATOMIC_PROCESS_DELAYED_LUA = """
local delayed_key = KEYS[1]
local task_prefix = KEYS[2]
local queue_prefix = KEYS[3]
local now = tonumber(ARGV[1])
local task_ttl = tonumber(ARGV[2])

local tasks = redis.call('zrangebyscore', delayed_key, 0, now)
local count = 0
for _, task_id in ipairs(tasks) do
    local delayed_flag_key = task_prefix .. task_id .. ':delayed'
    if redis.call('get', delayed_flag_key) then
        redis.call('del', delayed_flag_key)
        redis.call('zrem', delayed_key, task_id)
        local task_key = task_prefix .. task_id
        local task_json = redis.call('get', task_key)
        if task_json then
            local task = cjson.decode(task_json)
            if task.state == 'queued' or task.state == 'retrying' then
                task.state = 'queued'
                task.updated_at = now
                redis.call('setex', task_key, task_ttl, cjson.encode(task))
                redis.call('lpush', queue_prefix .. tostring(task.priority), task_id)
                count = count + 1
            end
        end
    else
        redis.call('zrem', delayed_key, task_id)
    end
end
return tostring(count)
"""

ATOMIC_ACQUIRE_LEASE_LUA = """
local lease_key = KEYS[1]
local worker_id = ARGV[1]
local lease_data = ARGV[2]
local timeout = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local existing = redis.call('get', lease_key)
if not existing then
    redis.call('setex', lease_key, timeout + 10, lease_data)
    return 1
end
local existing_lease = cjson.decode(existing)
if existing_lease.expires_at < now then
    redis.call('del', lease_key)
    redis.call('setex', lease_key, timeout + 10, lease_data)
    return 1
end
return 0
"""

ATOMIC_ACQUIRE_LOCK_LUA = """
local lock_key = KEYS[1]
local owner = ARGV[1]
local ttl = tonumber(ARGV[2])

local acquired = redis.call('setnx', lock_key, owner)
if acquired == 1 then
    redis.call('expire', lock_key, ttl)
    return 1
end
local current_ttl = redis.call('ttl', lock_key)
if current_ttl < 0 then
    redis.call('del', lock_key)
    local retry = redis.call('setnx', lock_key, owner)
    if retry == 1 then
        redis.call('expire', lock_key, ttl)
        return 1
    end
end
return 0
"""

ATOMIC_RELEASE_LOCK_LUA = """
local lock_key = KEYS[1]
local owner = ARGV[1]
local current = redis.call('get', lock_key)
if current and current == owner then
    redis.call('del', lock_key)
    return 1
end
return 0
"""

ATOMIC_RENEW_LOCK_LUA = """
local lock_key = KEYS[1]
local owner = ARGV[1]
local ttl = tonumber(ARGV[2])
local current = redis.call('get', lock_key)
if current and current == owner then
    redis.call('expire', lock_key, ttl)
    return 1
end
return 0
"""


class AsyncRedisClient:
    def __init__(self, url: str = "", max_connections: int = 10, timeout: float = 5.0):
        self._url = url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._max_connections = max_connections
        self._timeout = timeout
        self._pool: Any = None
        self._redis: Any = None
        self._subscriber: Any = None
        self._pubsub: Any = None
        self._closed = False
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._redis is not None:
            return
        async with self._lock:
            if self._redis is not None:
                return
            try:
                import redis.asyncio as aioredis

                self._pool = aioredis.ConnectionPool.from_url(
                    self._url,
                    max_connections=self._max_connections,
                    timeout=self._timeout,
                    socket_keepalive=True,
                    retry_on_timeout=True,
                )
                self._redis = aioredis.Redis(connection_pool=self._pool)
                await self._redis.ping()
                safe_url = self._url.split("@")[-1] if "@" in self._url else self._url
                logger.info(f"Connected to Redis at {safe_url}")
            except ImportError:
                raise ImportError("redis package required. Install: pip install redis") from None
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                raise

    async def ping(self) -> bool:
        if self._redis is None:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            return False

    async def get(self, key: str) -> str | None:
        if self._redis is None:
            return None
        val = await self._redis.get(key)
        if val is not None:
            return val.decode("utf-8") if isinstance(val, bytes) else val
        return None

    async def set(self, key: str, value: str, ttl: int = 0) -> None:
        if self._redis is None:
            return
        if ttl > 0:
            await self._redis.setex(key, ttl, value)
        else:
            await self._redis.set(key, value)

    async def setnx(self, key: str, value: str) -> bool:
        if self._redis is None:
            return False
        result = await self._redis.setnx(key, value)
        return bool(result)

    async def delete(self, key: str) -> None:
        if self._redis is None:
            return
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        if self._redis is None:
            return False
        return bool(await self._redis.exists(key))

    async def lpush(self, key: str, value: str) -> None:
        if self._redis is None:
            return
        await self._redis.lpush(key, value)

    async def rpush(self, key: str, value: str) -> None:
        if self._redis is None:
            return
        await self._redis.rpush(key, value)

    async def rpop(self, key: str) -> str | None:
        if self._redis is None:
            return None
        val = await self._redis.rpop(key)
        if val is not None:
            return val.decode("utf-8") if isinstance(val, bytes) else val
        return None

    async def lpop(self, key: str) -> str | None:
        if self._redis is None:
            return None
        val = await self._redis.lpop(key)
        if val is not None:
            return val.decode("utf-8") if isinstance(val, bytes) else val
        return None

    async def brpop(self, key: str, timeout: int = 0) -> tuple[str, str] | None:
        if self._redis is None:
            return None
        result = await self._redis.brpop(key, timeout=timeout)
        if result:
            k, v = result
            return (k.decode("utf-8") if isinstance(k, bytes) else k, v.decode("utf-8") if isinstance(v, bytes) else v)
        return None

    async def zadd(self, key: str, score: float, member: str) -> None:
        if self._redis is None:
            return
        await self._redis.zadd(key, {member: score})

    async def zrem(self, key: str, member: str) -> None:
        if self._redis is None:
            return
        await self._redis.zrem(key, member)

    async def zrangebyscore(self, key: str, min_score: float, max_score: float) -> list[str]:
        if self._redis is None:
            return []
        results = await self._redis.zrangebyscore(key, min_score, max_score)
        return [r.decode("utf-8") if isinstance(r, bytes) else r for r in results]

    async def zcard(self, key: str) -> int:
        if self._redis is None:
            return 0
        return await self._redis.zcard(key)

    async def zpopmin(self, key: str, count: int = 1) -> list[tuple[str, float]]:
        if self._redis is None:
            return []
        results = await self._redis.zpopmin(key, count=count)
        return [(r[0].decode("utf-8") if isinstance(r[0], bytes) else r[0], r[1]) for r in results]

    async def hset(self, key: str, field: str, value: str) -> None:
        if self._redis is None:
            return
        await self._redis.hset(key, field, value)

    async def hget(self, key: str, field: str) -> str | None:
        if self._redis is None:
            return None
        val = await self._redis.hget(key, field)
        if val is not None:
            return val.decode("utf-8") if isinstance(val, bytes) else val
        return None

    async def hgetall(self, key: str) -> dict[str, str]:
        if self._redis is None:
            return {}
        result = await self._redis.hgetall(key)
        return {
            (k.decode("utf-8") if isinstance(k, bytes) else k): (v.decode("utf-8") if isinstance(v, bytes) else v)
            for k, v in result.items()
        }

    async def hdel(self, key: str, field: str) -> None:
        if self._redis is None:
            return
        await self._redis.hdel(key, field)

    async def publish(self, channel: str, message: str) -> None:
        if self._redis is None:
            return
        await self._redis.publish(channel, message)

    async def subscribe(self, channel: str) -> None:
        if self._redis is None:
            return
        if self._pubsub is None:
            self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(channel)

    async def unsubscribe(self, channel: str) -> None:
        if self._pubsub is None:
            return
        await self._pubsub.unsubscribe(channel)

    async def get_message(self, timeout: float = 1.0) -> dict[str, Any] | None:
        if self._pubsub is None:
            return None
        try:
            msg = await self._pubsub.get_message(timeout=timeout)
            return msg
        except Exception:
            return None

    async def eval_script(self, script: str, keys: list[str] | None = None, args: list[str] | None = None) -> Any:
        if self._redis is None:
            return None
        try:
            return await self._redis.eval(script, len(keys or []), *(keys or []), *(args or []))
        except Exception as e:
            logger.error(f"Lua eval error: {e}")
            return None

    async def atomic_dequeue(
        self,
        queue_key: str,
        task_prefix: str,
        lease_prefix: str,
        now: float,
        visibility_timeout: int,
        lease_ttl: int,
        task_ttl: int,
    ) -> str | None:
        result = await self.eval_script(
            ATOMIC_DEQUEUE_LUA,
            keys=[queue_key, task_prefix, lease_prefix],
            args=[str(now), str(visibility_timeout), str(lease_ttl), str(task_ttl)],
        )
        if result:
            return result.decode("utf-8") if isinstance(result, bytes) else result
        return None

    async def atomic_process_delayed(
        self, delayed_key: str, task_prefix: str, queue_prefix: str, now: float, task_ttl: int
    ) -> int:
        result = await self.eval_script(
            ATOMIC_PROCESS_DELAYED_LUA,
            keys=[delayed_key, task_prefix, queue_prefix],
            args=[str(now), str(task_ttl)],
        )
        if result:
            return int(result.decode("utf-8") if isinstance(result, bytes) else result)
        return 0

    async def acquire_lock(self, lock_key: str, ttl: int = 30, owner: str = "") -> bool:
        if self._redis is None:
            return False
        owner = owner or f"lock_{id(self):x}"
        result = await self.eval_script(
            ATOMIC_ACQUIRE_LOCK_LUA,
            keys=[lock_key],
            args=[owner, str(ttl)],
        )
        return bool(result)

    async def release_lock(self, lock_key: str, owner: str = "") -> None:
        if self._redis is None:
            return
        owner = owner or f"lock_{id(self):x}"
        await self.eval_script(
            ATOMIC_RELEASE_LOCK_LUA,
            keys=[lock_key],
            args=[owner],
        )

    async def renew_lock(self, lock_key: str, ttl: int = 30, owner: str = "") -> bool:
        if self._redis is None:
            return False
        owner = owner or f"lock_{id(self):x}"
        result = await self.eval_script(
            ATOMIC_RENEW_LOCK_LUA,
            keys=[lock_key],
            args=[owner, str(ttl)],
        )
        return bool(result)

    async def keys(self, pattern: str = "*") -> list[str]:
        if self._redis is None:
            return []
        results = await self._redis.keys(pattern)
        return [r.decode("utf-8") if isinstance(r, bytes) else r for r in results]

    async def lindex(self, key: str, index: int) -> str | None:
        if self._redis is None:
            return None
        val = await self._redis.lindex(key, index)
        if val is not None:
            return val.decode("utf-8") if isinstance(val, bytes) else val
        return None

    async def llen(self, key: str) -> int:
        if self._redis is None:
            return 0
        return await self._redis.llen(key)

    async def scan(self, pattern: str = "*", count: int = 100) -> list[str]:
        if self._redis is None:
            return []
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = await self._redis.scan(cursor=cursor, match=pattern, count=count)
            keys.extend(k.decode("utf-8") if isinstance(k, bytes) else k for k in batch)
            if cursor == 0:
                break
        return keys

    async def expire(self, key: str, ttl: int) -> None:
        if self._redis is None:
            return
        await self._redis.expire(key, ttl)

    async def ttl(self, key: str) -> int:
        if self._redis is None:
            return -2
        return await self._redis.ttl(key)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._pubsub:
            await self._pubsub.close()
        if self._pool:
            await self._pool.disconnect()
        self._redis = None
        self._pool = None
        logger.info("Redis client closed")

    async def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        ok = await self.ping()
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "connected": ok,
            "latency_ms": round(elapsed, 2),
            "pool_size": self._max_connections,
            "url": self._url,
        }


async def create_redis_client(
    url: str = "",
    max_connections: int = 10,
    timeout: float = 5.0,
) -> AsyncRedisClient:
    client = AsyncRedisClient(url=url, max_connections=max_connections, timeout=timeout)
    await client.connect()
    return client
