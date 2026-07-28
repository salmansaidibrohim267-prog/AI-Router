"""Live benchmark engine with rolling window metrics per provider."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

MAX_RECORDS_PER_PROVIDER = 200000
WINDOWS_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "1hour": 3600,
    "24hour": 86400,
}


@dataclass
class RequestRecord:
    """Single request measurement."""
    timestamp: float
    latency_ms: float
    first_token_latency_ms: float
    tokens: int
    success: bool
    timeout: bool
    model: str


@dataclass
class WindowSnapshot:
    """Computed statistics for a single time window."""
    requests: int = 0
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    min_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    avg_first_token_latency_ms: float = 0.0
    tokens_per_sec: float = 0.0
    throughput_req_per_sec: float = 0.0
    failure_rate: float = 0.0
    timeout_rate: float = 0.0
    total_tokens: int = 0


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * pct / 100)))
    return sorted_vals[idx]


def _compute_window(
    records: list[RequestRecord],
    window_start: float,
) -> WindowSnapshot:
    """Compute windowed statistics from a list of records within a time window."""
    if not records:
        return WindowSnapshot()

    windowed = [r for r in records if r.timestamp >= window_start]
    if not windowed:
        return WindowSnapshot()

    n = len(windowed)
    successes = sum(1 for r in windowed if r.success)
    failures = sum(1 for r in windowed if not r.success and not r.timeout)
    timeouts = sum(1 for r in windowed if r.timeout)
    total_tokens = sum(r.tokens for r in windowed)

    latencies = [r.latency_ms for r in windowed]
    ftl = [r.first_token_latency_ms for r in windowed if r.first_token_latency_ms > 0]

    avg_lat = sum(latencies) / n
    min_lat = min(latencies)
    max_lat = max(latencies)

    if ftl:
        avg_ftl = sum(ftl) / len(ftl)
    else:
        avg_ftl = 0.0

    sorted_lat = sorted(latencies)

    elapsed = time.time() - window_start
    duration = max(elapsed, max_lat / 1000.0)

    return WindowSnapshot(
        requests=n,
        successes=successes,
        failures=failures,
        timeouts=timeouts,
        avg_latency_ms=round(avg_lat, 2),
        p50_latency_ms=round(_percentile(sorted_lat, 50), 2),
        p95_latency_ms=round(_percentile(sorted_lat, 95), 2),
        p99_latency_ms=round(_percentile(sorted_lat, 99), 2),
        min_latency_ms=round(min_lat, 2),
        max_latency_ms=round(max_lat, 2),
        avg_first_token_latency_ms=round(avg_ftl, 2),
        tokens_per_sec=round(total_tokens / duration, 2) if duration > 0 else 0.0,
        throughput_req_per_sec=round(n / duration, 2) if duration > 0 else 0.0,
        failure_rate=round(failures / n, 4) if n > 0 else 0.0,
        timeout_rate=round(timeouts / n, 4) if n > 0 else 0.0,
        total_tokens=total_tokens,
    )


class ProviderBenchmark:
    """Rolling window benchmark data for a single provider."""

    def __init__(self, name: str):
        self.name = name
        self._records: deque[RequestRecord] = deque(maxlen=MAX_RECORDS_PER_PROVIDER)
        self._lock = threading.RLock()

    def record(
        self,
        latency_ms: float,
        first_token_latency_ms: float,
        tokens: int,
        success: bool,
        timeout: bool,
        model: str,
    ) -> None:
        with self._lock:
            self._records.append(RequestRecord(
                timestamp=time.time(),
                latency_ms=latency_ms,
                first_token_latency_ms=first_token_latency_ms,
                tokens=tokens,
                success=success,
                timeout=timeout,
                model=model,
            ))

    def get_snapshot(self) -> dict[str, WindowSnapshot]:
        """Compute statistics for all configured windows."""
        now = time.time()
        with self._lock:
            records = list(self._records)

        result = {}
        for window_name, window_sec in WINDOWS_SECONDS.items():
            window_start = now - window_sec
            result[window_name] = _compute_window(records, window_start)
        return result

    def get_aggregated_score(self) -> float:
        """Compute a single benchmark score for routing decisions (0-100)."""
        snapshots = self.get_snapshot()
        s5 = snapshots.get("5min")
        if not s5 or s5.requests < 5:
            s1 = snapshots.get("1min")
            if s1 and s1.requests >= 3:
                s5 = s1
            else:
                return 50.0

        # Score based on recent performance
        latency_score = max(0.0, 100.0 - s5.avg_latency_ms / 10.0)
        reliability_score = (1.0 - s5.failure_rate - s5.timeout_rate) * 100.0
        throughput_score = min(100.0, s5.tokens_per_sec * 5.0)

        return round(
            latency_score * 0.40 + reliability_score * 0.35 + throughput_score * 0.25,
            2,
        )

    def reset(self) -> None:
        with self._lock:
            self._records.clear()

    @property
    def total_records(self) -> int:
        with self._lock:
            return len(self._records)


class LiveBenchmark:
    """Global live benchmark tracker for all providers."""

    def __init__(self):
        self._providers: dict[str, ProviderBenchmark] = {}
        self._lock = threading.RLock()

    def get_or_create(self, name: str) -> ProviderBenchmark:
        with self._lock:
            if name not in self._providers:
                self._providers[name] = ProviderBenchmark(name)
            return self._providers[name]

    def record(
        self,
        provider: str,
        latency_ms: float,
        first_token_latency_ms: float = 0.0,
        tokens: int = 0,
        success: bool = True,
        timeout: bool = False,
        model: str = "",
    ) -> None:
        pb = self.get_or_create(provider)
        pb.record(
            latency_ms=latency_ms,
            first_token_latency_ms=first_token_latency_ms,
            tokens=tokens,
            success=success,
            timeout=timeout,
            model=model,
        )

    def get_provider_snapshot(self, provider: str) -> dict[str, Any]:
        pb = self.get_or_create(provider)
        raw = pb.get_snapshot()
        return {
            name: {
                "requests": ws.requests,
                "successes": ws.successes,
                "failures": ws.failures,
                "timeouts": ws.timeouts,
                "avg_latency_ms": ws.avg_latency_ms,
                "p50_latency_ms": ws.p50_latency_ms,
                "p95_latency_ms": ws.p95_latency_ms,
                "p99_latency_ms": ws.p99_latency_ms,
                "min_latency_ms": ws.min_latency_ms,
                "max_latency_ms": ws.max_latency_ms,
                "avg_first_token_latency_ms": ws.avg_first_token_latency_ms,
                "tokens_per_sec": ws.tokens_per_sec,
                "throughput_req_per_sec": ws.throughput_req_per_sec,
                "failure_rate": ws.failure_rate,
                "timeout_rate": ws.timeout_rate,
                "total_tokens": ws.total_tokens,
            }
            for name, ws in raw.items()
        }

    def get_snapshot(self) -> dict[str, Any]:
        """Get full live benchmark snapshot for all providers."""
        with self._lock:
            names = list(self._providers.keys())
        result = {}
        for name in names:
            result[name] = self.get_provider_snapshot(name)
        return result

    def get_ranking(self) -> list[dict[str, Any]]:
        """Rank providers by benchmark score."""
        with self._lock:
            names = list(self._providers.keys())
        ranked = []
        for name in names:
            pb = self._providers[name]
            score = pb.get_aggregated_score()
            ranked.append({
                "provider": name,
                "score": score,
                "total_records": pb.total_records,
            })
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked

    def get_fastest(self) -> str | None:
        ranked = self.get_ranking()
        return ranked[0]["provider"] if ranked else None

    def reset(self) -> None:
        with self._lock:
            for pb in self._providers.values():
                pb.reset()


live_benchmark = LiveBenchmark()
