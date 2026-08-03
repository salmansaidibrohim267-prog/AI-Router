"""Benchmark runner for AI Router."""

from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

from app.cache import cache_manager
from app.models import ChatRequest, Message, MessageRole
from app.router import router
from app.stats import stats


@dataclass
class BenchmarkResult:
    target: str
    num_requests: int
    concurrency: int
    stream: bool
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0
    fallback_count: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    provider_success: dict[str, int] = field(default_factory=dict)
    provider_failure: dict[str, int] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time

    @property
    def average_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return statistics.mean(self.latencies_ms)

    @property
    def p95_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lats = sorted(self.latencies_ms)
        idx = int(len(sorted_lats) * 0.95)
        return sorted_lats[min(idx, len(sorted_lats) - 1)]

    @property
    def p99_latency_ms(self) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lats = sorted(self.latencies_ms)
        idx = int(len(sorted_lats) * 0.99)
        return sorted_lats[min(idx, len(sorted_lats) - 1)]

    @property
    def throughput_reqs_per_sec(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.num_requests / self.duration_seconds

    @property
    def success_rate(self) -> float:
        if self.num_requests == 0:
            return 0.0
        return (self.num_requests - self.errors) / self.num_requests

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "num_requests": self.num_requests,
            "concurrency": self.concurrency,
            "stream": self.stream,
            "duration_seconds": round(self.duration_seconds, 3),
            "average_latency_ms": round(self.average_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "throughput_reqs_per_sec": round(self.throughput_reqs_per_sec, 2),
            "success_rate": round(self.success_rate, 4),
            "errors": self.errors,
            "fallback_count": self.fallback_count,
            "provider_success": dict(self.provider_success),
            "provider_failure": dict(self.provider_failure),
            "min_latency_ms": round(min(self.latencies_ms), 2) if self.latencies_ms else 0,
            "max_latency_ms": round(max(self.latencies_ms), 2) if self.latencies_ms else 0,
        }


async def _run_single_request(
    model: str,
    messages: list[Message],
    stream: bool,
    semaphore: asyncio.Semaphore,
    result: BenchmarkResult,
    index: int,
) -> None:
    async with semaphore:
        req = ChatRequest(model=model, messages=messages, stream=stream)
        start = time.perf_counter()
        try:
            if stream:
                async for _chunk in router.stream_chat(req):
                    pass
                latency = (time.perf_counter() - start) * 1000
                result.latencies_ms.append(latency)
            else:
                _ = await router.chat(req)
                latency = (time.perf_counter() - start) * 1000
                result.latencies_ms.append(latency)
        except Exception:
            latency = (time.perf_counter() - start) * 1000
            result.latencies_ms.append(latency)
            result.errors += 1


async def _run_single_streaming(
    model: str, messages: list[Message], result: BenchmarkResult, semaphore: asyncio.Semaphore
) -> None:  # noqa: E501
    await _run_single_request(model, messages, True, semaphore, result, 0)


async def _run_single_non_streaming(
    model: str, messages: list[Message], result: BenchmarkResult, semaphore: asyncio.Semaphore
) -> None:  # noqa: E501
    await _run_single_request(model, messages, False, semaphore, result, 0)


async def run_benchmark(
    *,
    model: str = "gpt-4o-mini",
    provider: str | None = None,
    num_requests: int = 10,
    concurrency: int = 5,
    stream: bool = False,
    prompt: str = "Say hello in one word",
    target: str = "internal",
) -> BenchmarkResult:
    await router.initialize()

    messages = [Message(role=MessageRole.USER, content=prompt)]
    result = BenchmarkResult(
        target=target,
        num_requests=num_requests,
        concurrency=concurrency,
        stream=stream,
    )

    if provider:
        router.provider_manager.enable_provider(provider)

    semaphore = asyncio.Semaphore(concurrency)
    tasks = []

    result.start_time = time.time()

    for i in range(num_requests):
        task = _run_single_request(model, messages, stream, semaphore, result, i)
        tasks.append(task)

    await asyncio.gather(*tasks)

    result.end_time = time.time()

    fallback_metrics = [m for name, m in router.metrics.items() if m.total_requests > m.successful_requests]
    result.fallback_count = len(fallback_metrics)

    for name, m in router.metrics.items():
        if m.successful_requests > 0:
            result.provider_success[name] = m.successful_requests
        if m.failed_requests > 0:
            result.provider_failure[name] = m.failed_requests

    return result


async def get_system_metrics() -> dict[str, Any]:
    latency_stats = {}
    for name, m in router.metrics.items():
        if m.total_requests > 0:
            latency_stats[name] = {
                "avg_latency_ms": round(m.avg_latency, 2) if m.avg_latency != float("inf") else 0,
                "total_requests": m.total_requests,
                "success_rate": round(m.success_rate, 4),
            }

    _ = router.get_provider_stats()
    s = stats.summary()

    fallback_count = sum(1 for m in router.metrics.values() if m.total_requests > m.successful_requests)

    cache_stats = cache_manager.get_all_stats()
    total_hits = sum(cs.get("hits", 0) for cs in cache_stats.values())
    total_misses = sum(cs.get("misses", 0) for cs in cache_stats.values())
    cache_hit_ratio = total_hits / (total_hits + total_misses) if (total_hits + total_misses) > 0 else 0.0

    return {
        "latency": latency_stats,
        "success_rate": round(s.success_rate, 4),
        "total_requests": s.total_requests,
        "fallback_count": fallback_count,
        "cache_hit_ratio": round(cache_hit_ratio, 4),
        "provider_usage": dict(s.provider_usage),
        "model_usage": dict(s.model_usage),
        "task_usage": dict(s.task_usage),
    }
