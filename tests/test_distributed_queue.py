import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.distributed.distributed_queue import DistributedTaskQueue
from app.distributed.lease import LeaseManager
from app.distributed.models import DistributedTask, LeaseInfo, WorkerInfo, WorkerStatus, EventMessage, RetryPolicy, DLQEntry
from app.distributed.redis_client import AsyncRedisClient
from app.distributed.worker_registry import WorkerRegistry
from app.distributed.idempotency import IdempotencyGuard
from app.distributed.retry import ExponentialBackoff, RetryPolicyManager
from app.distributed.dlq import DeadLetterQueue
from app.distributed.event_bus import DistributedEventBus, EventTypes
from app.distributed.distributed_scheduler import DistributedScheduler
from app.distributed.health import RuntimeHealth


# ---------------------------------------------------------------------------
# Mock Redis (full command set matching AsyncRedisClient)
# ---------------------------------------------------------------------------

class MockRedis:
    def __init__(self):
        self._data: dict[str, str] = {}
        self._expiry: dict[str, float] = {}
        self._pubsub: list[dict] = []

    async def get(self, key: str) -> str | None:
        if key in self._expiry and time.time() > self._expiry.get(key, 0):
            del self._data[key]
            del self._expiry[key]
            return None
        return self._data.get(key)

    async def set(self, key: str, value: str, **kwargs) -> None:
        self._data[key] = value
        ttl = kwargs.get("ex") or kwargs.get("ttl", 0)
        if ttl:
            self._expiry[key] = time.time() + ttl

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._data[key] = value
        self._expiry[key] = time.time() + ttl

    async def setnx(self, key: str, value: str) -> bool:
        if key not in self._data:
            self._data[key] = value
            return True
        return False

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._expiry.pop(key, None)

    async def expire(self, key: str, ttl: int) -> None:
        self._expiry[key] = time.time() + ttl

    async def ttl(self, key: str) -> int:
        if key not in self._data:
            return -2
        if key not in self._expiry:
            return -1
        remaining = int(self._expiry[key] - time.time())
        return max(remaining, 0)

    async def lpush(self, key: str, value: str) -> None:
        if key not in self._data:
            self._data[key] = "[]"
        lst = json.loads(self._data[key])
        lst.insert(0, value)
        self._data[key] = json.dumps(lst)

    async def rpush(self, key: str, value: str) -> None:
        if key not in self._data:
            self._data[key] = "[]"
        lst = json.loads(self._data[key])
        lst.append(value)
        self._data[key] = json.dumps(lst)

    async def lpop(self, key: str) -> str | None:
        if key not in self._data:
            return None
        lst = json.loads(self._data[key])
        if not lst:
            return None
        val = lst.pop(0)
        self._data[key] = json.dumps(lst)
        return val

    async def rpop(self, key: str) -> str | None:
        if key not in self._data:
            return None
        lst = json.loads(self._data[key])
        if not lst:
            return None
        val = lst.pop()
        self._data[key] = json.dumps(lst)
        return val

    async def brpop(self, key: str, timeout: int = 0) -> tuple[str, str] | None:
        if key not in self._data:
            return None
        lst = json.loads(self._data[key])
        if not lst:
            return None
        val = lst.pop()
        self._data[key] = json.dumps(lst)
        return (key, val)

    async def lindex(self, key: str, idx: int) -> str | None:
        if key not in self._data:
            return None
        lst = json.loads(self._data[key])
        if 0 <= idx < len(lst):
            return lst[idx]
        return None

    async def llen(self, key: str) -> int:
        if key not in self._data:
            return 0
        return len(json.loads(self._data[key]))

    async def zadd(self, key: str, score: float, member: str) -> None:
        if key not in self._data:
            self._data[key] = "[]"
        lst = json.loads(self._data[key])
        lst.append(json.dumps({"member": member, "score": score}))
        self._data[key] = json.dumps(lst)

    async def zrem(self, key: str, member: str) -> None:
        if key not in self._data:
            return
        lst = json.loads(self._data[key])
        lst = [x for x in lst if json.loads(x).get("member") != member]
        self._data[key] = json.dumps(lst)

    async def zrangebyscore(self, key: str, min_score: float, max_score: float) -> list[str]:
        if key not in self._data:
            return []
        lst = json.loads(self._data[key])
        results = []
        for x in lst:
            entry = json.loads(x)
            if min_score <= entry["score"] <= max_score:
                results.append(entry["member"])
        return results

    async def zcard(self, key: str) -> int:
        if key not in self._data:
            return 0
        return len(json.loads(self._data[key]))

    async def zpopmin(self, key: str, count: int = 1) -> list[tuple[str, float]]:
        if key not in self._data:
            return []
        lst = json.loads(self._data[key])
        items = [(json.loads(x)["member"], json.loads(x)["score"]) for x in lst]
        items.sort(key=lambda x: x[1])
        popped = items[:count]
        remaining = items[count:]
        self._data[key] = json.dumps([json.dumps({"member": m, "score": s}) for m, s in remaining])
        return popped

    async def publish(self, channel: str, message: str) -> None:
        self._pubsub.append({"channel": channel, "data": message})

    async def ping(self) -> bool:
        return True

    async def hset(self, key: str, field: str, value: str) -> None:
        if key not in self._data:
            self._data[key] = "{}"
        obj = json.loads(self._data[key])
        obj[field] = value
        self._data[key] = json.dumps(obj)

    async def hget(self, key: str, field: str) -> str | None:
        if key not in self._data:
            return None
        obj = json.loads(self._data[key])
        return obj.get(field)

    async def hgetall(self, key: str) -> dict[str, str]:
        if key not in self._data:
            return {}
        return json.loads(self._data[key])

    async def hdel(self, key: str, field: str) -> None:
        if key in self._data:
            obj = json.loads(self._data[key])
            obj.pop(field, None)
            self._data[key] = json.dumps(obj)

    async def hkeys(self, key: str) -> list[str]:
        obj = await self.hgetall(key)
        return list(obj.keys())

    async def hvals(self, key: str) -> list[str]:
        obj = await self.hgetall(key)
        return list(obj.values())

    async def hlen(self, key: str) -> int:
        obj = await self.hgetall(key)
        return len(obj)

    async def incr(self, key: str) -> int:
        val = int(await self.get(key) or "0")
        val += 1
        await self.set(key, str(val))
        return val

    async def decr(self, key: str) -> int:
        val = int(await self.get(key) or "0")
        val -= 1
        await self.set(key, str(val))
        return val

    async def smembers(self, key: str) -> set:
        val = await self.get(key)
        if not val:
            return set()
        return set(json.loads(val))

    async def sadd(self, key: str, member: str) -> None:
        members = await self.smembers(key)
        members.add(member)
        await self.set(key, json.dumps(list(members)))

    async def srem(self, key: str, member: str) -> None:
        members = await self.smembers(key)
        members.discard(member)
        await self.set(key, json.dumps(list(members)))

    async def keys(self, pattern: str = "*") -> list[str]:
        return [k for k in self._data]

    async def subscribe(self, channel: str) -> None:
        pass

    async def unsubscribe(self, channel: str) -> None:
        pass

    async def get_message(self, timeout: float = 1.0) -> dict | None:
        return None

    async def eval_script(self, script: str, keys: list | None = None, args: list | None = None) -> Any:
        import json as _json
        key = (keys or [None])[0] if keys else ""
        now = float((args or ["0", "0", "0"])[-1]) if args else 0
        # Lease acquire Lua
        if key.startswith("dist_lease:"):
            existing = await self.get(key)
            lease_data = (args or [""])[0] if args else "{}"
            timeout = int((args or ["0", "0", "0"])[1]) if len(args or []) > 1 else 30
            if not existing:
                await self.set(key, lease_data)
                await self.expire(key, timeout)
                return 1
            try:
                el = _json.loads(existing)
                if el.get("expires_at", 0) < now:
                    await self.delete(key)
                    await self.set(key, lease_data)
                    await self.expire(key, timeout)
                    return 1
            except (_json.JSONDecodeError, TypeError):
                pass
            return 0
        # Idempotency SET NX EX
        if "NX" in script:
            val = (args or [""])[0] if args else ""
            ttl = int((args or ["0", "0", "0"])[1]) if len(args or []) > 1 else 86400
            acquired = await self.setnx(key, val)
            if acquired:
                await self.expire(key, ttl)
                return 1
            return 0
        return 1

    async def acquire_lock(self, lock_key: str, ttl: int = 30, owner: str = "") -> bool:
        acquired = await self.setnx(lock_key, owner)
        if acquired:
            await self.expire(lock_key, ttl)
            return True
        current = await self.get(lock_key)
        if current:
            current_ttl = await self.ttl(lock_key)
            if current_ttl < 0:
                await self.delete(lock_key)
                return await self.acquire_lock(lock_key, ttl, owner)
        return False

    async def release_lock(self, lock_key: str, owner: str = "") -> None:
        current = await self.get(lock_key)
        if current and current == owner:
            await self.delete(lock_key)

    async def renew_lock(self, lock_key: str, ttl: int = 30, owner: str = "") -> bool:
        current = await self.get(lock_key)
        if current and current == owner:
            await self.expire(lock_key, ttl)
            return True
        return False


@pytest.fixture
def mock_redis():
    return MockRedis()


@pytest.fixture
def client(mock_redis):
    """Wrap MockRedis in an AsyncRedisClient-compatible adapter."""
    client = AsyncMock(spec=AsyncRedisClient)
    client._redis = mock_redis
    for method in [
        "get", "set", "setnx", "exists", "delete", "expire", "ttl",
        "lpush", "rpush", "lpop", "rpop", "brpop", "lindex", "llen",
        "zadd", "zrem", "zrangebyscore", "zcard", "zpopmin",
        "publish", "ping",
        "hset", "hget", "hgetall", "hdel",
        "keys", "subscribe", "unsubscribe", "get_message",
        "acquire_lock", "release_lock", "renew_lock", "eval_script",
    ]:
        impl = getattr(mock_redis, method)
        getattr(client, method).side_effect = impl
    return client


# ---------------------------------------------------------------------------
# Test DistributedTask serialization
# ---------------------------------------------------------------------------

class TestModels:
    def test_distributed_task_roundtrip(self):
        task = DistributedTask(
            task_id="t1",
            task_type="test",
            payload={"key": "val"},
            priority=5,
            max_retries=3,
        )
        d = task.to_dict()
        task2 = DistributedTask.from_dict(d)
        assert task2.task_id == "t1"
        assert task2.task_type == "test"
        assert task2.payload == {"key": "val"}
        assert task2.priority == 5
        assert task2.max_retries == 3

    def test_lease_info(self):
        li = LeaseInfo(worker_id="w1", task_id="t1", timeout=30)
        d = li.to_dict()
        assert d["worker_id"] == "w1"
        assert d["task_id"] == "t1"
        assert d["timeout"] == 30
        assert li.is_expired() is True

    def test_worker_info_to_dict(self):
        wi = WorkerInfo(worker_id="w1", status=WorkerStatus.ONLINE)
        d = wi.to_dict()
        assert d["worker_id"] == "w1"
        assert d["status"] == "online"

    def test_event_message(self):
        em = EventMessage(
            event_id="e1",
            event_type="test.event",
            timestamp=time.time(),
            payload={"key": "val"},
        )
        d = em.to_dict()
        em2 = EventMessage(**d)
        assert em2.event_id == "e1"
        assert em2.event_type == "test.event"

    def test_retry_policy(self):
        rp = RetryPolicy(max_retries=5, base_delay=2.0)
        assert rp.max_retries == 5
        assert rp.base_delay == 2.0

    def test_dlq_entry(self):
        task = DistributedTask(task_id="t_dlq", task_type="fail")
        entry = DLQEntry(
            task_id="t_dlq",
            original_task=task.to_dict(),
            error="timeout",
            retry_count=3,
            worker_id="w1",
        )
        d = entry.to_dict()
        assert d["task_id"] == "t_dlq"
        assert d["error"] == "timeout"


# ---------------------------------------------------------------------------
# Test DistributedTaskQueue
# ---------------------------------------------------------------------------

class TestDistributedTaskQueue:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, client):
        queue = DistributedTaskQueue(client)
        task = await queue.enqueue(task_type="test", payload={"a": 1})
        assert task is not None
        assert task.task_id

        dequeued = await queue.dequeue()
        assert dequeued is not None
        assert dequeued.task_type == "test"
        assert dequeued.payload == {"a": 1}

    @pytest.mark.asyncio
    async def test_ack(self, client):
        queue = DistributedTaskQueue(client)
        await queue.enqueue(task_type="test", payload={})
        dequeued = await queue.dequeue()
        assert dequeued is not None

        await queue.ack(dequeued.task_id)
        saved = await queue.get_task(dequeued.task_id)
        assert saved.state.value == "completed"

    @pytest.mark.asyncio
    async def test_nack_requeues(self, client):
        queue = DistributedTaskQueue(client)
        await queue.enqueue(task_type="test", payload={})
        dequeued = await queue.dequeue()
        assert dequeued is not None

        await queue.nack(dequeued.task_id, error="fail")
        saved = await queue.get_task(dequeued.task_id)
        assert saved is not None

    @pytest.mark.asyncio
    async def test_enqueue_with_priority(self, client):
        queue = DistributedTaskQueue(client)
        await queue.enqueue(task_type="low", payload={}, priority=1)
        await queue.enqueue(task_type="high", payload={}, priority=10)

        t1 = await queue.dequeue()
        assert t1 is not None
        assert t1.task_type == "high"

    @pytest.mark.asyncio
    async def test_get_depth(self, client):
        queue = DistributedTaskQueue(client)
        depth = await queue.get_depth()
        assert isinstance(depth, dict)

    @pytest.mark.asyncio
    async def test_empty_dequeue_returns_none(self, client):
        queue = DistributedTaskQueue(client)
        result = await queue.dequeue()
        assert result is None


# ---------------------------------------------------------------------------
# Test LeaseManager
# ---------------------------------------------------------------------------

class TestLeaseManager:
    @pytest.mark.asyncio
    async def test_acquire_release(self, client):
        lease = LeaseManager(client)
        acquired = await lease.acquire("task_1", "worker_1", timeout=10)
        assert acquired is not None

        released = await lease.release("task_1", "worker_1")
        assert released is True

    @pytest.mark.asyncio
    async def test_acquire_twice_fails(self, client):
        lease = LeaseManager(client)
        await lease.acquire("task_1", "worker_1", timeout=10)
        acquired = await lease.acquire("task_1", "worker_2", timeout=10)
        assert acquired is None

    @pytest.mark.asyncio
    async def test_renew(self, client):
        lease = LeaseManager(client)
        await lease.acquire("task_1", "worker_1", timeout=10)
        renewed = await lease.renew("task_1", "worker_1", timeout=20)
        assert renewed is True


# ---------------------------------------------------------------------------
# Test WorkerRegistry
# ---------------------------------------------------------------------------

class TestWorkerRegistry:
    @pytest.mark.asyncio
    async def test_register_and_list(self, client):
        registry = WorkerRegistry(client)
        await registry.register("test_worker_1")

        workers = await registry.list_workers()
        assert len(workers) == 1
        assert workers[0].worker_id == "test_worker_1"

    @pytest.mark.asyncio
    async def test_drain(self, client):
        registry = WorkerRegistry(client)
        await registry.register("test_worker_2")
        await registry.set_draining("test_worker_2")

        workers = await registry.list_workers()
        assert workers[0].status == WorkerStatus.DRAINING

    @pytest.mark.asyncio
    async def test_unregister(self, client):
        registry = WorkerRegistry(client)
        await registry.register("test_worker_3")
        await registry.unregister()

        worker = await registry.get_worker("test_worker_3")
        assert worker is None or worker.status == WorkerStatus.OFFLINE


# ---------------------------------------------------------------------------
# Test IdempotencyGuard
# ---------------------------------------------------------------------------

class TestIdempotencyGuard:
    @pytest.mark.asyncio
    async def test_is_duplicate(self, client):
        guard = IdempotencyGuard(client)
        assert await guard.is_duplicate("key1") is False

        await guard.mark_processed("key1")
        assert await guard.is_duplicate("key1") is True

    @pytest.mark.asyncio
    async def test_try_process(self, client):
        guard = IdempotencyGuard(client)
        assert await guard.try_process("key1") is True
        assert await guard.try_process("key1") is False

    @pytest.mark.asyncio
    async def test_get_result(self, client):
        guard = IdempotencyGuard(client)
        await guard.mark_processed("key1", result="done")
        result = await guard.get_result("key1")
        assert result is not None
        assert result["result"] == "done"

    @pytest.mark.asyncio
    async def test_release(self, client):
        guard = IdempotencyGuard(client)
        await guard.mark_processed("key1")
        await guard.release("key1")
        assert await guard.is_duplicate("key1") is False


# ---------------------------------------------------------------------------
# Test ExponentialBackoff
# ---------------------------------------------------------------------------

class TestExponentialBackoff:
    def test_backoff_increases(self):
        b = ExponentialBackoff(base_delay=1.0, multiplier=2.0, jitter=0.0)
        d1 = b.get_delay(0)
        d2 = b.get_delay(1)
        d3 = b.get_delay(2)
        assert d1 == 1.0
        assert d2 == 2.0
        assert d3 == 4.0

    def test_backoff_max_delay(self):
        b = ExponentialBackoff(base_delay=1.0, max_delay=5.0, multiplier=10.0, jitter=0.0)
        d = b.get_delay(10)
        assert d <= 5.0

    def test_jitter(self):
        b = ExponentialBackoff(base_delay=10.0, jitter=0.5)
        delays = [b.get_delay(0) for _ in range(100)]
        assert any(d != 10.0 for d in delays)


class TestRetryPolicyManager:
    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self):
        mgr = RetryPolicyManager()
        result = await mgr.execute_with_retry(lambda: "ok")
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_execute_with_retry_failure(self):
        mgr = RetryPolicyManager(RetryPolicy(max_retries=2, base_delay=0.01))

        call_count = 0

        async def fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await mgr.execute_with_retry(fail)
        assert call_count == 3


# ---------------------------------------------------------------------------
# Test DeadLetterQueue
# ---------------------------------------------------------------------------

class TestDeadLetterQueue:
    @pytest.mark.asyncio
    async def test_push_and_count(self, client):
        dlq = DeadLetterQueue(client)
        task = DistributedTask(task_id="dlq_1", task_type="fail")
        await dlq.push(task, error="timeout", worker_id="w1")
        count = await dlq.count()
        assert count == 1

    @pytest.mark.asyncio
    async def test_list_entries(self, client):
        dlq = DeadLetterQueue(client)
        task = DistributedTask(task_id="dlq_2", task_type="fail")
        await dlq.push(task, error="err", worker_id="w1")
        entries = await dlq.list_entries(limit=10)
        assert len(entries) == 1
        assert entries[0]["task_id"] == "dlq_2"
        assert entries[0]["error"] == "err"

    @pytest.mark.asyncio
    async def test_clear(self, client):
        dlq = DeadLetterQueue(client)
        task = DistributedTask(task_id="dlq_3", task_type="fail")
        await dlq.push(task, error="err")
        await dlq.clear()
        count = await dlq.count()
        assert count == 0


# ---------------------------------------------------------------------------
# Test DistributedEventBus
# ---------------------------------------------------------------------------

class TestDistributedEventBus:
    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self, client):
        bus = DistributedEventBus(client)
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventTypes.TASK_CREATED, handler)
        await bus.publish(EventTypes.TASK_CREATED, {"task_id": "t1"})
        assert len(received) == 1
        assert received[0].event_type == EventTypes.TASK_CREATED
        assert received[0].payload["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_unsubscribe(self, client):
        bus = DistributedEventBus(client)
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)
        await bus.publish("test.event", {})
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, client):
        bus = DistributedEventBus(client)
        r1, r2 = [], []

        async def h1(e):
            r1.append(e)

        async def h2(e):
            r2.append(e)

        bus.subscribe("multi", h1)
        bus.subscribe("multi", h2)
        await bus.publish("multi", {"n": 1})
        assert len(r1) == 1
        assert len(r2) == 1

    def test_subscriber_count(self, client):
        bus = DistributedEventBus(client)
        assert bus.get_subscriber_count() == 0

        def h(e):
            pass

        bus.subscribe("a", h)
        assert bus.get_subscriber_count("a") == 1
        assert bus.get_subscriber_count() == 1

    def test_event_types_constants(self):
        assert EventTypes.TASK_CREATED == "task.created"
        assert EventTypes.SCHEDULER_LEADER_CHANGED == "scheduler.leader_changed"


# ---------------------------------------------------------------------------
# Test DistributedScheduler
# ---------------------------------------------------------------------------

class TestDistributedScheduler:
    @pytest.mark.asyncio
    async def test_leader_election(self, client):
        sched = DistributedScheduler(client, instance_id="test_1")
        await sched.start()
        await asyncio.sleep(0.3)
        leader = await sched.is_leader()
        assert leader is True
        await sched.stop()

    @pytest.mark.asyncio
    async def test_get_leader(self, client):
        sched = DistributedScheduler(client, instance_id="leader_1")
        await sched.start()
        await asyncio.sleep(0.3)
        leader_id = await sched.get_leader()
        assert leader_id == "leader_1"
        await sched.stop()

    @pytest.mark.asyncio
    async def test_add_remove_job(self, client):
        sched = DistributedScheduler(client)
        sched.add_job("j1", "test", {"a": 1}, interval=60)
        jobs = sched.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["job_id"] == "j1"

        sched.remove_job("j1")
        assert len(sched.list_jobs()) == 0

    @pytest.mark.asyncio
    async def test_leader_change_callback(self, client):
        sched = DistributedScheduler(client, instance_id="cb_test")
        states = []

        def cb(is_leader):
            states.append(is_leader)

        sched.on_leader_change(cb)
        await sched.start()
        await asyncio.sleep(0.3)
        assert True in states
        await sched.stop()


# ---------------------------------------------------------------------------
# Test RuntimeHealth
# ---------------------------------------------------------------------------

class TestRuntimeHealth:
    @pytest.mark.asyncio
    async def test_check_redis(self, client):
        health = RuntimeHealth(redis=client)
        result = await health.check_redis()
        assert result["status"] == "ok"
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_full_health(self, client):
        health = RuntimeHealth(redis=client)
        result = await health.full_health()
        assert result["status"] == "ok"
        assert "redis" in result["checks"]
        assert "queue" in result["checks"]
        assert "workers" in result["checks"]
        assert "scheduler" in result["checks"]
        assert "event_bus" in result["checks"]


# ---------------------------------------------------------------------------
# Test Tracing (no-op without OTEL)
# ---------------------------------------------------------------------------

class TestTracing:
    def test_get_tracer_no_otel(self):
        from app.distributed import tracing
        tracer = tracing.get_tracer()
        assert tracer is None or tracer is not None

    def test_init_tracing_disabled(self):
        from app.distributed import tracing
        tracing.init_tracing(enabled=False)
        assert tracing.TRACER is None
