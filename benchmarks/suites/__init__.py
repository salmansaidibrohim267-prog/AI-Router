"""Benchmark suites (Stage 10.10).

Self-contained in-process benchmarks: throughput, latency, memory, CPU,
concurrency, failover and RAG retrieval quality.
"""

from .base import BenchmarkReport, SuiteResult, Target, mean, percentile
from .runner import SUITE_BUILDERS, SuiteRunner
from .suites import (
    ConcurrencySuite,
    CpuSuite,
    FailoverSuite,
    LatencySuite,
    MemorySuite,
    RagDoc,
    RagQualitySuite,
    ThroughputSuite,
)

__all__ = [
    "Target",
    "SuiteResult",
    "BenchmarkReport",
    "mean",
    "percentile",
    "ThroughputSuite",
    "LatencySuite",
    "MemorySuite",
    "CpuSuite",
    "ConcurrencySuite",
    "FailoverSuite",
    "RagDoc",
    "RagQualitySuite",
    "SUITE_BUILDERS",
    "SuiteRunner",
]
