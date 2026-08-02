"""Throughput, latency, concurrency, memory, CPU, failover and RAG suites."""

from __future__ import annotations

import threading
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Any, Callable

from .base import SuiteResult, Target, mean, percentile


class ThroughputSuite:
    """Measures requests/second sustained over ``duration`` seconds."""

    def __init__(self, duration: float = 0.5) -> None:
        self.duration = duration

    def run(self, target: Target) -> SuiteResult:
        start = time.perf_counter()
        count = 0
        while time.perf_counter() - start < self.duration:
            target()
            count += 1
        elapsed = time.perf_counter() - start
        throughput = count / elapsed if elapsed else 0.0
        return SuiteResult(
            name="throughput",
            metrics={"requests": float(count), "requests_per_second": round(throughput, 2), "duration_seconds": round(elapsed, 4)},
        )


class LatencySuite:
    """Measures mean / p50 / p95 / p99 latency over ``iterations`` calls."""

    def __init__(self, iterations: int = 200, latency_fn: Callable[[], float] | None = None) -> None:
        self.iterations = iterations
        self.latency_fn = latency_fn or (lambda: 0.001)

    def run(self, target: Target) -> SuiteResult:
        latencies: list[float] = []
        for _ in range(self.iterations):
            start = time.perf_counter()
            target()
            latencies.append((time.perf_counter() - start) * 1000.0)
        return SuiteResult(
            name="latency",
            metrics={
                "iterations": float(self.iterations),
                "mean_ms": mean(latencies),
                "p50_ms": percentile(latencies, 0.50),
                "p95_ms": percentile(latencies, 0.95),
                "p99_ms": percentile(latencies, 0.99),
                "max_ms": round(max(latencies), 4),
            },
        )


class MemorySuite:
    """Measures peak and resident allocation via tracemalloc."""

    def __init__(self, iterations: int = 5000, alloc_bytes: int = 128) -> None:
        self.iterations = iterations
        self.alloc_bytes = alloc_bytes

    def run(self, target: Target) -> SuiteResult:
        tracemalloc.start()
        start = tracemalloc.take_snapshot()
        for _ in range(self.iterations):
            target()
        end = tracemalloc.take_snapshot()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        diff = sum(stat.size_diff for stat in end.compare_to(start, "lineno"))
        return SuiteResult(
            name="memory",
            metrics={
                "peak_bytes": float(peak),
                "delta_bytes": float(diff),
                "allocations": float(tracemalloc.get_traced_memory()[1] if False else peak),
            },
            detail="tracemalloc peak",
        )


class CpuSuite:
    """Measures CPU-bound throughput on a compute target."""

    def __init__(self, loops: int = 200000) -> None:
        self.loops = loops

    def run(self, target: Target) -> SuiteResult:
        start = time.perf_counter()
        for _ in range(self.loops):
            target()
        elapsed = time.perf_counter() - start
        return SuiteResult(
            name="cpu",
            metrics={
                "loops": float(self.loops),
                "elapsed_seconds": round(elapsed, 4),
                "loops_per_second": round(self.loops / elapsed, 2) if elapsed else 0.0,
            },
        )


class ConcurrencySuite:
    """Measures throughput under ``workers`` concurrent threads."""

    def __init__(self, workers: int = 8, per_worker: int = 50) -> None:
        self.workers = workers
        self.per_worker = per_worker

    def run(self, target: Target) -> SuiteResult:
        barrier = threading.Barrier(self.workers)
        counts: list[int] = [0] * self.workers
        errors: list[int] = [0] * self.workers

        def _worker(index: int) -> None:
            barrier.wait()
            for _ in range(self.per_worker):
                try:
                    target()
                    counts[index] += 1
                except Exception:
                    errors[index] += 1

        start = time.perf_counter()
        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(self.workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        elapsed = time.perf_counter() - start
        total = sum(counts)
        return SuiteResult(
            name="concurrency",
            metrics={
                "workers": float(self.workers),
                "total_requests": float(total),
                "errors": float(sum(errors)),
                "requests_per_second": round(total / elapsed, 2) if elapsed else 0.0,
            },
            passed=sum(errors) == 0,
            detail=f"elapsed={round(elapsed, 4)}s" if sum(errors) else "no errors",
        )


class FailoverSuite:
    """Measures recovery time when the target starts failing.

    The wrapped target raises for ``failure_until`` seconds then recovers;
    the suite records how long the failure was observed and the recovered
    latency.
    """

    def __init__(self, failure_seconds: float = 0.2, probe_interval: float = 0.01) -> None:
        self.failure_seconds = failure_seconds
        self.probe_interval = probe_interval

    def run(self, target: Target) -> SuiteResult:
        failed = 0
        recovered_at: float | None = None
        start = time.perf_counter()
        while time.perf_counter() - start < self.failure_seconds + 0.5:
            try:
                target()
            except Exception:
                failed += 1
            else:
                if recovered_at is None:
                    recovered_at = time.perf_counter()
                break
            time.sleep(self.probe_interval)
        recovery_ms = ((recovered_at - start) * 1000.0) if recovered_at is not None else -1.0
        return SuiteResult(
            name="failover",
            metrics={
                "observed_failures": float(failed),
                "recovery_ms": round(recovery_ms, 2),
                "recovered": float(recovered_at is not None),
            },
            passed=recovered_at is not None,
            detail="target recovered" if recovered_at is not None else "target never recovered",
        )


@dataclass
class RagDoc:
    """A document in the retrieval benchmark corpus."""

    id: str
    text: str


class RagQualitySuite:
    """Measures retrieval precision/recall against a known corpus.

    ``retriever(query) -> list[RagDoc]``. Each query has one relevant doc id;
    precision = relevant retrieved / retrieved; recall = relevant found / total relevant.
    """

    def __init__(
        self,
        corpus: list[RagDoc] | None = None,
        queries: list[tuple[str, str]] | None = None,
    ) -> None:
        self.corpus = corpus if corpus is not None else [
            RagDoc("d1", "The AI Router routes requests to the best provider based on health."),
            RagDoc("d2", "Billing tracks usage per tenant and produces monthly invoices."),
            RagDoc("d3", "The security framework signs releases with HMAC-SHA256."),
            RagDoc("d4", "SLOs define error budgets and burn rates for alerting."),
        ]
        self.queries = queries if queries is not None else [
            ("how does routing choose a provider", "d1"),
            ("how are tenants billed", "d2"),
            ("how are releases signed", "d3"),
            ("what is an error budget", "d4"),
        ]

    def _score(self, retriever: Callable[[str], list[RagDoc]]) -> tuple[float, float, int, int]:
        precisions: list[float] = []
        recalls: list[float] = []
        for query, expected_id in self.queries:
            retrieved = retriever(query)
            relevant = [doc for doc in retrieved if doc.id == expected_id]
            precision = len(relevant) / len(retrieved) if retrieved else 0.0
            recall = 1.0 if relevant else 0.0
            precisions.append(precision)
            recalls.append(recall)
        return mean(precisions), mean(recalls), len(self.queries), 0

    def run(self, retriever: Callable[[str], list[RagDoc]]) -> SuiteResult:
        precision, recall, query_count, _ = self._score(retriever)
        return SuiteResult(
            name="rag_quality",
            metrics={
                "precision": precision,
                "recall": recall,
                "f1": round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0,
                "queries": float(query_count),
            },
            passed=precision >= 0.5 and recall >= 0.5,
            detail="precision/recall over corpus",
        )
