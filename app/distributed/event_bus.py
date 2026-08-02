from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from typing import Any, Callable

from app.distributed.models import EventMessage
from app.distributed.redis_client import AsyncRedisClient

logger = logging.getLogger(__name__)

EVENT_CHANNEL = "dist_events"
EventHandler = Callable[[EventMessage], Any]


class EventTypes:
    TASK_CREATED = "task.created"
    TASK_QUEUED = "task.queued"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    WORKER_STARTED = "worker.started"
    WORKER_STOPPED = "worker.stopped"
    WORKER_OFFLINE = "worker.offline"
    SCHEDULER_LEADER_CHANGED = "scheduler.leader_changed"


class DistributedEventBus:
    def __init__(self, redis: AsyncRedisClient, channel: str = EVENT_CHANNEL):
        self._redis = redis
        self._channel = channel
        self._local_handlers: dict[str, list[EventHandler]] = {}
        self._running = False
        self._listener_task: asyncio.Task | None = None

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._local_handlers:
            self._local_handlers[event_type] = []
        self._local_handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type in self._local_handlers:
            self._local_handlers[event_type] = [
                h for h in self._local_handlers[event_type] if h is not handler
            ]

    async def publish(self, event_type: str, payload: dict[str, Any] = None, metadata: dict[str, Any] = None) -> None:
        event = EventMessage(
            event_id=uuid.uuid4().hex[:12],
            event_type=event_type,
            timestamp=time.time(),
            payload=payload or {},
            metadata=metadata or {},
        )
        msg = json.dumps(event.to_dict())
        await self._redis.publish(self._channel, msg)
        await self._dispatch_local(event)

    async def start_listener(self) -> None:
        if self._running:
            return
        self._running = True
        await self._redis.subscribe(self._channel)
        self._listener_task = asyncio.create_task(self._listen_loop())

    async def stop_listener(self) -> None:
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        await self._redis.unsubscribe(self._channel)

    async def _listen_loop(self) -> None:
        while self._running:
            try:
                msg = await self._redis.get_message(timeout=1.0)
                if msg and msg.get("type") == "message":
                    data = msg.get("data", b"{}")
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    event_data = json.loads(data)
                    event = EventMessage(**event_data)
                    await self._dispatch_local(event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Event listener error: {e}")

    async def _dispatch_local(self, event: EventMessage) -> None:
        handlers = self._local_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error for {event.event_type}: {e}")

    def get_subscriber_count(self, event_type: str = "") -> int:
        if event_type:
            return len(self._local_handlers.get(event_type, []))
        return sum(len(h) for h in self._local_handlers.values())
