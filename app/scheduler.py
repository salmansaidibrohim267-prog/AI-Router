"""Distributed scheduler entry point.

Runs leader election and periodically enqueues scheduled jobs.
"""

import asyncio
import logging
import os
import signal

from app.distributed.distributed_scheduler import DistributedScheduler
from app.distributed.redis_client import AsyncRedisClient

logger = logging.getLogger(__name__)


class SchedulerProcess:
    def __init__(self):
        self._redis_client: AsyncRedisClient | None = None
        self._scheduler: DistributedScheduler | None = None
        self._running = False

    async def start(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis_client = AsyncRedisClient(url=redis_url)
        await self._redis_client.connect()
        self._scheduler = DistributedScheduler(self._redis_client)

        await self._scheduler.start()
        self._running = True

        while self._running:
            await asyncio.sleep(60)

    async def stop(self):
        self._running = False
        if self._scheduler:
            await self._scheduler.stop()
        if self._redis_client:
            await self._redis_client.close()


async def main():
    scheduler = SchedulerProcess()
    loop = asyncio.get_running_loop()

    stop = asyncio.Event()

    def signal_handler():
        if not stop.is_set():
            logger.info("Shutdown signal received, stopping scheduler...")
            stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    scheduler_task = asyncio.create_task(scheduler.start())

    await stop.wait()
    logger.info("Scheduler shutting down...")
    await scheduler.stop()
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
