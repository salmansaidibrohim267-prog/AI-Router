"""Distributed scheduler.

Job types:

- ``recurring`` — run every ``interval`` seconds.
- ``delayed``   — run once after ``delay`` seconds.
- ``cron``      — run on a cron schedule (minute hour dom month dow).
- ``singleton`` — run only on the leader node.
- ``failover``  — claimable by any node; orphans are re-claimed after a
  node failure.

The scheduler is async-first: one loop task ticks every
``config.scheduler_interval`` seconds, claiming due jobs and executing
handlers as tasks with per-job timeouts.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Callable

from .config import ClusterConfig
from .exceptions import JobNotFoundError, SchedulerError
from .logging import ClusterLogger
from .metrics import ClusterMetricsTracker
from .models import JobRun, JobSpec, JobState, JobType
from .repository import JobStore


class CronExpression:
    """Minimal cron parser: ``m h dom mon dow``.

    Supports ``*``, ``*/n``, ``a-b`` ranges, ``a,b,c`` lists and plain
    numbers. Names (``jan``/``mon``) are not supported.
    """

    _BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))

    def __init__(self, expression: str) -> None:
        self.expression = expression
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError(f"cron expression must have 5 fields, got {len(parts)}: {expression!r}")
        self._sets: list[set[int]] = []
        for bounds, raw in zip(self._BOUNDS, parts, strict=False):
            self._sets.append(self._parse_field(bounds, raw))

    def _parse_field(self, bounds: tuple[int, int], raw: str) -> set[int]:
        low, high = bounds
        values: set[int] = set()
        if raw == "*":
            return set(range(low, high + 1))
        for piece in raw.split(","):
            if "/" in piece:
                base, _, step_raw = piece.partition("/")
                step = int(step_raw)
                if step <= 0:
                    raise ValueError(f"cron step must be positive: {piece!r}")
                if base == "*":
                    values.update(range(low, high + 1, step))
                elif "-" in base:
                    start, _, end = base.partition("-")
                    values.update(range(int(start), int(end) + 1, step))
                else:
                    values.update(range(int(base), high + 1, step))
            elif "-" in piece:
                start, _, end = piece.partition("-")
                values.update(range(int(start), int(end) + 1))
            elif piece.isdigit():
                value = int(piece)
                if value < low or value > high:
                    raise ValueError(f"cron value {value} out of range {low}-{high}")
                values.add(value)
            else:
                raise ValueError(f"invalid cron token {piece!r}")
        if not values:
            raise ValueError(f"empty cron set in {self.expression!r}")
        return values

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self._sets[0]
            and dt.hour in self._sets[1]
            and self._day_matches(dt)
            and dt.month in self._sets[3]
        )

    def next_after(self, dt: datetime | None = None) -> datetime:
        """Next datetime strictly after ``dt`` matching the schedule."""
        dt = dt or datetime.now()
        candidate = dt.replace(second=0, microsecond=0)
        if dt.second or dt.microsecond:
            candidate += timedelta(minutes=1)
        for _ in range(366 * 24 * 60):
            if candidate.month not in self._sets[3] or not self._day_matches(candidate):
                candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if candidate.hour in self._sets[1]:
                for _minute in range(60):
                    minute = candidate.minute
                    if minute in self._sets[0]:
                        return candidate
                    if minute == 59:
                        break
                    candidate = candidate.replace(minute=minute + 1)
            candidate = candidate.replace(minute=0) + timedelta(hours=1)
        raise ValueError(f"no future cron match for {self.expression!r}")

    def _day_matches(self, dt: datetime) -> bool:
        dom_matches = dt.day in self._sets[2]
        dow_matches = dt.weekday() in self._sets[4]
        dom_restricted = self._sets[2] != set(range(1, 32))
        dow_restricted = self._sets[4] != set(range(0, 7))
        if dom_restricted and dow_restricted:
            # Standard cron: either field matching satisfies the day.
            return dom_matches or dow_matches
        return dom_matches and dow_matches


Handler = Callable[[dict[str, Any]], Any]
"""Job handler: async or sync, receives the job payload."""


class DistributedScheduler:
    """Claims and executes due jobs across the cluster."""

    def __init__(
        self,
        config: ClusterConfig | None = None,
        store: JobStore | None = None,
        logger: ClusterLogger | None = None,
        metrics: ClusterMetricsTracker | None = None,
        handlers: dict[str, Handler] | None = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.store = store if store is not None else JobStore()
        self.logger = logger or ClusterLogger(self.config)
        self.metrics = metrics or ClusterMetricsTracker(self.config)
        self.handlers = dict(handlers or {})
        self._tasks: set[asyncio.Task] = set()
        self._loop_task: asyncio.Task | None = None
        self._running = False
        self._paused = False
        self._node_id = "local"
        self._leader_check: Callable[[], bool] = lambda: True
        self._semaphore = asyncio.Semaphore(self.config.scheduler_max_concurrent)
        self.last_tick = 0.0
        self.executed = 0

    def register_handler(self, name: str, handler: Handler) -> None:
        self.handlers[name] = handler

    def unregister_handler(self, name: str) -> bool:
        return self.handlers.pop(name, None) is not None

    def set_node_id(self, node_id: str) -> None:
        self._node_id = node_id

    def set_leader_check(self, check: Callable[[], bool]) -> None:
        self._leader_check = check

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._loop(), name="cluster-scheduler")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def _loop(self) -> None:
        while self._running:
            if not self._paused:
                try:
                    await self.tick()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - scheduler must survive
                    self.logger.log_event("scheduler_tick_error", error=str(exc))
            await asyncio.sleep(self.config.scheduler_interval)

    # -- job management ------------------------------------------------------

    def add_job(self, spec: JobSpec) -> JobSpec:
        if spec.type == JobType.CRON and not spec.cron:
            raise SchedulerError("cron jobs require a cron expression")
        now = time.time()
        if spec.type == JobType.DELAYED:
            spec.next_run = now + spec.delay
        elif spec.type == JobType.CRON:
            spec.next_run = CronExpression(spec.cron).next_after(datetime.now()).timestamp()
        else:
            spec.next_run = now + spec.interval
        self.store.add(spec)
        self.logger.log_event("job_added", job=spec.id, name=spec.name, type=spec.type.value, next_run=spec.next_run)
        self.metrics.record("jobs_added", component="scheduler")
        return spec

    def schedule(
        self,
        name: str,
        handler: Handler,
        *,
        interval: float = 60.0,
        delay: float = 0.0,
        cron: str = "",
        singleton: bool = False,
        failover: bool = False,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        priority: int = 0,
        timeout: float | None = None,
        job_type: JobType | None = None,
    ) -> JobSpec:
        """Convenience registration: handler + spec in one call."""
        if job_type is None:
            if cron:
                job_type = JobType.CRON
            elif delay:
                job_type = JobType.DELAYED
            elif singleton:
                job_type = JobType.SINGLETON
            elif failover:
                job_type = JobType.FAILOVER
            else:
                job_type = JobType.RECURRING
        self.register_handler(name, handler)
        spec = JobSpec(
            name=name,
            type=job_type,
            interval=interval,
            delay=delay,
            cron=cron,
            singleton=singleton,
            failover=failover,
            payload=dict(payload or {}),
            metadata=dict(metadata or {}),
            priority=priority,
            timeout=timeout if timeout is not None else self.config.job_timeout,
        )
        return self.add_job(spec)

    def remove_job(self, job_id: str) -> bool:
        removed = self.store.remove(job_id)
        if removed:
            self.logger.log_event("job_removed", job=job_id)
            self.metrics.record("jobs_removed", component="scheduler")
        return removed

    def get_job(self, job_id: str) -> JobSpec:
        job = self.store.get(job_id)
        if job is None:
            raise JobNotFoundError(f"job {job_id!r} not found")
        return job

    def jobs(self) -> list[JobSpec]:
        return self.store.all()

    def runs(self, job_id: str | None = None, limit: int = 100) -> list[JobRun]:
        return self.store.runs(job_id, limit)

    # -- execution ------------------------------------------------------------

    async def tick(self, now: float | None = None) -> int:
        """Claim and execute all due jobs; returns number started."""
        now = now if now is not None else time.time()
        self.last_tick = now
        started = 0
        for job in self.store.due(now):
            if await self._claim(job):
                started += 1
        self.executed += started
        return started

    async def run_now(self, job_id: str) -> JobRun:
        job = self.get_job(job_id)
        return await self._execute(job.id)

    async def _claim(self, job: JobSpec) -> bool:
        if job.singleton and not self._leader_check():
            return False
        if job.owner and job.owner != self._node_id and not job.failover:
            return False
        if job.failover:
            if job.owner and job.owner != self._node_id:
                return False
            if not self.store.claim(job.id, self._node_id):
                return False
        self.store.update(job.id, owner=self._node_id)
        self._tasks.add(asyncio.create_task(self._execute(job.id), name=f"cluster-job-{job.id}"))
        return True

    async def _execute(self, job_id: str) -> JobRun:
        job = self.store.require(job_id)
        attempt = int(job.metadata.get("_attempts", 0)) + 1
        job.metadata["_attempts"] = attempt
        run = JobRun(
            job_id=job.id,
            job_name=job.name,
            node_id=self._node_id,
            state=JobState.RUNNING,
            started_at=time.time(),
            attempts=attempt,
        )
        self.store.add_run(run)
        handler = self.handlers.get(job.name)
        if handler is None:
            return self._fail(job, run, f"no handler registered for job {job.name!r}")
        try:
            async with self._semaphore:
                result = await asyncio.wait_for(
                    self._call(handler, job.payload),
                    timeout=None if job.timeout <= 0 else job.timeout,
                )
        except asyncio.CancelledError:
            run.state = JobState.FAILED
            run.error = "cancelled"
            run.finished_at = time.time()
            self.store.update(job.id, owner=None, next_run=self._retry_next(job))
            raise
        except TimeoutError:
            return self._fail(job, run, f"timed out after {job.timeout}s")
        except Exception as exc:  # noqa: BLE001 - record handler failures
            return self._fail(job, run, str(exc))
        run.result = result
        run.state = JobState.SUCCEEDED
        run.finished_at = time.time()
        self._finish_success(job, run)
        self.logger.log_event("job_succeeded", job=job.id, name=job.name)
        return run

    async def _call(self, handler: Handler, payload: dict[str, Any]) -> Any:
        result = handler(payload)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def _retry_next(self, job: JobSpec) -> float:
        now = time.time()
        if job.type == JobType.CRON:
            return CronExpression(job.cron).next_after(datetime.fromtimestamp(now)).timestamp()
        return now + job.interval

    def _fail(self, job: JobSpec, run: JobRun, error: str) -> JobRun:
        run.state = JobState.FAILED
        run.error = error
        run.finished_at = time.time()
        retries = int(job.metadata.get("retries", 0))
        if run.attempts <= retries:
            self.store.update(job.id, owner=None, next_run=self._retry_next(job))
            run.state = JobState.PENDING
        else:
            self.store.update(job.id, owner=None, next_run=0)
        self.metrics.record("job_failures", component="scheduler")
        self.logger.log_event("job_failed", job=job.id, name=job.name, error=error)
        return run

    def _finish_success(self, job: JobSpec, run: JobRun) -> None:
        now = time.time()
        if job.type == JobType.DELAYED:
            self.store.update(job.id, last_run=now, next_run=0)
            self.store.remove(job.id)
        elif job.type == JobType.CRON:
            next_run = CronExpression(job.cron).next_after(datetime.fromtimestamp(now)).timestamp()
            self.store.update(job.id, last_run=now, next_run=next_run)
        else:
            self.store.update(job.id, last_run=now, next_run=now + job.interval)
        self.metrics.record("job_successes", component="scheduler")

    def status(self) -> dict[str, Any]:
        jobs = self.jobs()
        return {
            "running": len(self._tasks),
            "paused": self._paused,
            "total_jobs": len(jobs),
            "pending": sum(1 for j in jobs if j.next_run > 0),
            "by_type": {t.value: sum(1 for j in jobs if j.type == t) for t in JobType},
            "last_tick": self.last_tick,
            "executed": self.executed,
        }
