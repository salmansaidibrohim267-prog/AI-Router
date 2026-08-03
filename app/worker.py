"""Distributed worker entry point.

Dequeues tasks from Redis, processes them via the Stage 7 TaskWorker,
and sends results/errors back through the queue and event bus.
"""

import asyncio
import logging
import os
import signal

from app.distributed.distributed_queue import DistributedTaskQueue
from app.distributed.event_bus import DistributedEventBus, EventTypes
from app.distributed.models import TaskState
from app.distributed.redis_client import AsyncRedisClient
from app.distributed.worker_registry import WorkerRegistry

logger = logging.getLogger(__name__)


class WorkerProcess:
    def __init__(self):
        self._redis_client: AsyncRedisClient | None = None
        self._queue: DistributedTaskQueue | None = None
        self._registry: WorkerRegistry | None = None
        self._bus: DistributedEventBus | None = None
        self._running = False
        self._poll_tasks: list[asyncio.Task] = []

    async def start(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        concurrency = int(os.getenv("WORKER_CONCURRENCY", "5"))

        self._redis_client = AsyncRedisClient(url=redis_url)
        await self._redis_client.connect()
        self._queue = DistributedTaskQueue(self._redis_client)
        self._registry = WorkerRegistry(self._redis_client)
        self._bus = DistributedEventBus(self._redis_client)

        await self._registry.register(
            worker_id=f"worker_{os.getpid()}",
            max_concurrent=concurrency,
        )

        await self._bus.publish(
            EventTypes.WORKER_STARTED,
            {
                "worker_id": self._registry._worker_id,
            },
        )

        sem = asyncio.Semaphore(concurrency)

        async def process_one():
            async with sem:
                task = await self._queue.dequeue()
                if task is None:
                    return

                worker_id = self._registry._worker_id
                task.metadata["worker_id"] = worker_id
                task.state = TaskState.RUNNING
                await self._bus.publish(
                    EventTypes.TASK_STARTED,
                    {
                        "task_id": task.task_id,
                        "worker_id": worker_id,
                    },
                )

                try:
                    from app.orchestration.worker_pool import TaskWorker
                    from app.tasks.status import TaskState as TaskStateV7

                    worker = TaskWorker()
                    result = await worker.execute(task.task_type, task.payload)

                    task.state = TaskStateV7.COMPLETED
                    task.metadata["result"] = str(result)
                    await self._queue.ack(task.task_id)
                    await self._bus.publish(
                        EventTypes.TASK_COMPLETED,
                        {
                            "task_id": task.task_id,
                            "worker_id": worker_id,
                        },
                    )
                except Exception as e:
                    task.state = TaskState.FAILED
                    task.metadata["error"] = str(e)
                    await self._queue.nack(task.task_id, error=str(e))
                    await self._bus.publish(
                        EventTypes.TASK_FAILED,
                        {
                            "task_id": task.task_id,
                            "worker_id": worker_id,
                            "error": str(e),
                        },
                    )

        async def poll_loop():
            while self._running:
                try:
                    await process_one()
                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("Worker poll error")
                    await asyncio.sleep(1)

        self._running = True
        self._poll_tasks = [asyncio.create_task(poll_loop()) for _ in range(concurrency)]
        await asyncio.gather(*self._poll_tasks, return_exceptions=True)

    async def stop(self):
        self._running = False
        for t in self._poll_tasks:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._poll_tasks.clear()
        try:
            if self._bus:
                await self._bus.publish(
                    EventTypes.WORKER_STOPPED,
                    {
                        "worker_id": self._registry._worker_id if self._registry else "unknown",
                    },
                )
        except Exception:
            pass
        try:
            if self._registry:
                await self._registry.unregister()
        except Exception:
            pass
        try:
            if self._redis_client:
                await self._redis_client.close()
        except Exception:
            pass


async def main():
    worker = WorkerProcess()
    loop = asyncio.get_running_loop()

    stop = asyncio.Event()

    def signal_handler():
        if not stop.is_set():
            logger.info("Shutdown signal received, stopping worker...")
            stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    worker_task = asyncio.create_task(worker.start())

    await stop.wait()
    logger.info("Worker shutting down...")
    await worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
