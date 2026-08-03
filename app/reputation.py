"""Reputation engine with dynamic scoring, trend detection, and provider aging."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any

# Reputation weights
REPUTATION_WEIGHTS = {
    "success_rate": 0.35,
    "latency": 0.25,
    "uptime": 0.15,
    "cost": 0.10,
    "consistency": 0.10,
    "trend": 0.05,
}

# Aging decay constant: 0.999 means stats lose ~0.1% influence per second
AGING_DECAY_PER_SECOND = 0.999

# Rolling windows for trend detection
SHORT_WINDOW = 20
LONG_WINDOW = 100


class Trend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"


@dataclass
class TrendData:
    """Trend analysis result for a provider."""

    trend: Trend = Trend.STABLE
    short_window_error_rate: float = 0.0
    long_window_error_rate: float = 0.0
    score_delta: float = 0.0


def compute_trend(request_history: deque[bool]) -> TrendData:
    """Detect provider trend by comparing short vs long window error rates."""
    if not request_history:
        return TrendData(trend=Trend.STABLE, score_delta=0.0)

    all_items = list(request_history)
    total = len(all_items)

    short_items = all_items[-SHORT_WINDOW:] if total >= SHORT_WINDOW else all_items
    long_items = all_items

    short_errors = sum(1 for s in short_items if not s)
    long_errors = sum(1 for s in long_items if not s)

    short_error_rate = short_errors / len(short_items) if short_items else 0.0
    long_error_rate = long_errors / len(long_items) if long_items else 0.0

    if len(short_items) < 5 or len(long_items) < 10:
        return TrendData(
            trend=Trend.STABLE,
            short_window_error_rate=short_error_rate,
            long_window_error_rate=long_error_rate,
            score_delta=0.0,
        )

    trend: Trend
    score_delta: float

    if short_error_rate < long_error_rate * 0.8:
        trend = Trend.IMPROVING
        score_delta = min(15.0, (long_error_rate - short_error_rate) * 50.0)
    elif short_error_rate > long_error_rate * 1.2:
        trend = Trend.DEGRADING
        score_delta = -min(30.0, (short_error_rate - long_error_rate) * 50.0)
    else:
        trend = Trend.STABLE
        score_delta = 0.0

    return TrendData(
        trend=trend,
        short_window_error_rate=short_error_rate,
        long_window_error_rate=long_error_rate,
        score_delta=score_delta,
    )


def compute_reputation(
    success_rate: float,
    ewma_latency: float,
    avg_cost: float,
    uptime_seconds: float,
    consecutive_success: int,
    consecutive_failure: int,
) -> float:
    """Compute a dynamic reputation score from 0-100.

    Combines multiple weighted factors. Higher = more reputable.
    """
    # Success rate (0-100)
    sr_score = success_rate * 100.0

    # Latency score (0-100, inverse relationship)
    if ewma_latency <= 0:
        lat_score = 100.0
    else:
        lat_score = max(0.0, 100.0 - ewma_latency / 5.0)

    # Uptime (0-100, more uptime = better, caps at 7 days)
    uptime_hours = uptime_seconds / 3600.0
    uptime_score = min(100.0, uptime_hours * 0.6)

    # Cost efficiency (0-100, lower cost = better)
    if avg_cost <= 0:
        cost_score = 100.0
    else:
        cost_score = max(0.0, 100.0 - avg_cost * 2000.0)

    # Consistency (0-100)
    consistency = consecutive_success - consecutive_failure * 2
    consistency_score = max(0.0, min(100.0, 50.0 + consistency * 5.0))

    total = (
        sr_score * REPUTATION_WEIGHTS["success_rate"]
        + lat_score * REPUTATION_WEIGHTS["latency"]
        + uptime_score * REPUTATION_WEIGHTS["uptime"]
        + cost_score * REPUTATION_WEIGHTS["cost"]
        + consistency_score * REPUTATION_WEIGHTS["consistency"]
    )
    return round(total, 2)


def apply_aging(stats: Any, decay_per_second: float = AGING_DECAY_PER_SECOND) -> None:
    """Apply exponential decay to old statistics based on time since last_seen."""
    now = time.time()
    elapsed = now - stats.last_seen
    if elapsed <= 0:
        return

    factor = decay_per_second**elapsed

    stats.total_latency *= factor
    stats.ewma_latency *= factor
    stats.total_cost *= factor
    stats.total_prompt_tokens = int(stats.total_prompt_tokens * factor)
    stats.total_completion_tokens = int(stats.total_completion_tokens * factor)
    stats.total_requests = int(stats.total_requests * factor)
    stats.successful_requests = int(stats.successful_requests * factor)
    stats.failed_requests = int(stats.failed_requests * factor)


def circuit_breaker_multiplier(state: str | None) -> float:
    """Convert circuit breaker state to a routing multiplier.

    closed  → 100% (normal operation)
    half-open → 40% (testing recovery)
    open    → 0% (disabled)
    None/empty/unknown → 100% (treat as closed, case-insensitive)
    """
    if not state:
        return 1.0
    lower = state.lower()
    if lower == "closed":
        return 1.0
    elif lower == "half-open":
        return 0.4
    elif lower == "open":
        return 0.0
    return 1.0  # unknown state, treat as closed
