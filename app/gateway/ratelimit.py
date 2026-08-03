"""Rate limiting strategies for the API Gateway (Stage 10.4).

Implements Token Bucket, Leaky Bucket, Sliding Window, and Fixed Window
algorithms behind a common :class:`RateLimitStrategy` interface, plus a
thread-safe :class:`RateLimiter` registry with per-key policies.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any

from .config import GatewayConfig
from .exceptions import RateLimitExceededError
from .models import RateLimitDecision


class RateLimitStrategy:
    """Strategy interface for rate limiting algorithms."""

    name: str = "base"

    def check(self, key: str, cost: int = 1) -> RateLimitDecision:
        raise NotImplementedError

    def reset(self, key: str) -> None:
        raise NotImplementedError

    def status(self, key: str) -> dict[str, Any]:
        raise NotImplementedError


class TokenBucketLimiter(RateLimitStrategy):
    """Token Bucket: refills tokens continuously; allows bursts up to capacity."""

    name = "token_bucket"

    def __init__(self, rate_per_second: float, burst: int, initial: float | None = None):
        self.rate_per_second = rate_per_second
        self.burst = burst
        self._tokens: dict[str, float] = defaultdict(lambda: float(burst) if initial is None else float(initial))
        self._updated: dict[str, float] = defaultdict(time.time)
        self._lock = threading.Lock()

    def _refill(self, key: str, now: float) -> float:
        tokens = self._tokens[key]
        elapsed = now - self._updated[key]
        tokens = min(self.burst, tokens + elapsed * self.rate_per_second)
        self._tokens[key] = tokens
        self._updated[key] = now
        return tokens

    def check(self, key: str, cost: int = 1) -> RateLimitDecision:
        with self._lock:
            now = time.time()
            tokens = self._refill(key, now)
            if tokens >= cost:
                self._tokens[key] = tokens - cost
                return RateLimitDecision(
                    allowed=True,
                    strategy=self.name,
                    key=key,
                    limit=self.burst,
                    remaining=int(min(self.burst, self._tokens[key])),
                    reset_at=now + (self.burst - tokens + cost) / self.rate_per_second,
                )
            deficit = cost - tokens
            return RateLimitDecision(
                allowed=False,
                strategy=self.name,
                key=key,
                limit=self.burst,
                remaining=0,
                retry_after=deficit / self.rate_per_second,
                reset_at=now + deficit / self.rate_per_second,
            )

    def reset(self, key: str) -> None:
        with self._lock:
            self._tokens.pop(key, None)
            self._updated.pop(key, None)

    def status(self, key: str) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            tokens = self._refill(key, now)
            return {
                "strategy": self.name,
                "key": key,
                "available": tokens,
                "capacity": self.burst,
                "remaining": int(min(self.burst, tokens)),
                "rate_per_second": self.rate_per_second,
            }


class LeakyBucketLimiter(RateLimitStrategy):
    """Leaky Bucket: fixed processing rate; requests queue and drip out at a constant rate."""

    name = "leaky_bucket"

    def __init__(self, rate_per_second: float, capacity: int):
        self.rate_per_second = rate_per_second
        self.capacity = capacity
        self._queues: dict[str, deque[float]] = defaultdict(deque)
        self._last_drip: dict[str, float] = defaultdict(time.time)
        self._lock = threading.Lock()

    def _drain(self, key: str, now: float) -> None:
        queue = self._queues[key]
        elapsed = now - self._last_drip[key]
        drip_count = int(elapsed * self.rate_per_second)
        if drip_count <= 0:
            return
        for _ in range(min(drip_count, len(queue))):
            queue.popleft()
        self._last_drip[key] = now if drip_count > 0 else self._last_drip[key]

    def check(self, key: str, cost: int = 1) -> RateLimitDecision:
        with self._lock:
            now = time.time()
            self._drain(key, now)
            queue = self._queues[key]
            if len(queue) + cost <= self.capacity:
                for _ in range(cost):
                    queue.append(now)
                return RateLimitDecision(
                    allowed=True,
                    strategy=self.name,
                    key=key,
                    limit=self.capacity,
                    remaining=self.capacity - len(queue),
                    reset_at=now + len(queue) / self.rate_per_second,
                )
            oldest = queue[0] if queue else now
            retry_after = (len(queue) + cost - self.capacity) / self.rate_per_second
            return RateLimitDecision(
                allowed=False,
                strategy=self.name,
                key=key,
                limit=self.capacity,
                remaining=0,
                retry_after=retry_after,
                reset_at=oldest + (len(queue) + cost - self.capacity) / self.rate_per_second,
            )

    def reset(self, key: str) -> None:
        with self._lock:
            self._queues.pop(key, None)
            self._last_drip.pop(key, None)

    def status(self, key: str) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            self._drain(key, now)
            queue = self._queues[key]
            return {
                "strategy": self.name,
                "key": key,
                "queued": len(queue),
                "capacity": self.capacity,
                "remaining": self.capacity - len(queue),
                "rate_per_second": self.rate_per_second,
            }


class SlidingWindowLimiter(RateLimitStrategy):
    """Sliding Window: timestamps within a rolling window, weighted by precision."""

    name = "sliding_window"

    def __init__(self, limit: int, window_seconds: float, precision: float = 1.0):
        self.limit = limit
        self.window_seconds = window_seconds
        self.precision = precision
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> None:
        window = self._windows[key]
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

    def check(self, key: str, cost: int = 1) -> RateLimitDecision:
        with self._lock:
            now = time.time()
            self._prune(key, now)
            window = self._windows[key]
            if len(window) + cost <= self.limit:
                for _ in range(cost):
                    window.append(now)
                reset_at = (window[0] + self.window_seconds) if window else (now + self.window_seconds)
                return RateLimitDecision(
                    allowed=True,
                    strategy=self.name,
                    key=key,
                    limit=self.limit,
                    remaining=self.limit - len(window),
                    reset_at=reset_at,
                )
            oldest = window[0] if window else now
            return RateLimitDecision(
                allowed=False,
                strategy=self.name,
                key=key,
                limit=self.limit,
                remaining=0,
                retry_after=oldest + self.window_seconds - now,
                reset_at=oldest + self.window_seconds,
            )

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)

    def status(self, key: str) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            self._prune(key, now)
            window = self._windows[key]
            return {
                "strategy": self.name,
                "key": key,
                "used": len(window),
                "limit": self.limit,
                "remaining": max(0, self.limit - len(window)),
                "window_seconds": self.window_seconds,
            }


class FixedWindowLimiter(RateLimitStrategy):
    """Fixed Window: counter per aligned time bucket (e.g. 60s epochs)."""

    name = "fixed_window"

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self._counts: dict[str, dict[int, int]] = defaultdict(dict)
        self._lock = threading.Lock()

    def _bucket(self, now: float) -> int:
        return int(now // self.window_seconds)

    def check(self, key: str, cost: int = 1) -> RateLimitDecision:
        with self._lock:
            now = time.time()
            bucket = self._bucket(now)
            counts = self._counts[key]
            if bucket not in counts:
                counts.clear()
                counts[bucket] = 0
            if counts[bucket] + cost <= self.limit:
                counts[bucket] += cost
                reset_at = (bucket + 1) * self.window_seconds
                return RateLimitDecision(
                    allowed=True,
                    strategy=self.name,
                    key=key,
                    limit=self.limit,
                    remaining=self.limit - counts[bucket],
                    reset_at=reset_at,
                )
            reset_at = (bucket + 1) * self.window_seconds
            return RateLimitDecision(
                allowed=False,
                strategy=self.name,
                key=key,
                limit=self.limit,
                remaining=0,
                retry_after=reset_at - now,
                reset_at=reset_at,
            )

    def reset(self, key: str) -> None:
        with self._lock:
            self._counts.pop(key, None)

    def status(self, key: str) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            bucket = self._bucket(now)
            counts = self._counts[key]
            used = counts.get(bucket, 0)
            return {
                "strategy": self.name,
                "key": key,
                "used": used,
                "limit": self.limit,
                "remaining": max(0, self.limit - used),
                "window_seconds": self.window_seconds,
                "bucket": bucket,
            }


def create_rate_limit_strategy(name: str, config: GatewayConfig, **overrides: Any) -> RateLimitStrategy:
    """Strategy factory for the four built-in algorithms."""
    strategy = overrides.pop("strategy", name)
    if strategy == TokenBucketLimiter.name:
        return TokenBucketLimiter(
            rate_per_second=overrides.get("rate_per_second", config.default_requests_per_minute / 60.0),
            burst=overrides.get("burst", config.default_burst),
            initial=overrides.get("initial"),
        )
    if strategy == LeakyBucketLimiter.name:
        return LeakyBucketLimiter(
            rate_per_second=overrides.get("rate_per_second", config.default_requests_per_minute / 60.0),
            capacity=overrides.get("capacity", config.default_burst),
        )
    if strategy == SlidingWindowLimiter.name:
        return SlidingWindowLimiter(
            limit=overrides.get("limit", config.default_requests_per_minute),
            window_seconds=overrides.get("window_seconds", 60.0),
            precision=overrides.get("precision", config.sliding_window_precision),
        )
    if strategy == FixedWindowLimiter.name:
        return FixedWindowLimiter(
            limit=overrides.get("limit", config.default_requests_per_minute),
            window_seconds=overrides.get("window_seconds", 60.0),
        )
    raise ValueError(f"Unknown rate limit strategy {strategy!r}")


class RateLimiter:
    """Thread-safe registry of per-key rate limit policies over strategy instances."""

    def __init__(self, config: GatewayConfig | None = None):
        self._config = config or GatewayConfig()
        self._lock = threading.RLock()
        self._policies: dict[str, dict[str, Any]] = {}
        self._limiters: dict[str, RateLimitStrategy] = {}

    @property
    def config(self) -> GatewayConfig:
        return self._config

    def set_policy(
        self,
        key: str,
        strategy: str | None = None,
        limit: int | None = None,
        window_seconds: float | None = None,
        **overrides: Any,
    ) -> None:  # noqa: E501
        """Configure the policy for a limiter key."""
        with self._lock:
            self._policies[key] = {
                "strategy": strategy or self._config.default_rate_limit_strategy,
                "limit": limit,
                "window_seconds": window_seconds,
                "overrides": dict(overrides),
            }
            self._limiters.pop(key, None)

    def _build(self, policy: dict[str, Any]) -> RateLimitStrategy:
        strategy = policy["strategy"]
        overrides: dict[str, Any] = dict(policy.get("overrides") or {})
        if policy.get("limit") is not None:
            overrides.setdefault("limit", policy["limit"])
        if policy.get("window_seconds") is not None:
            overrides.setdefault("window_seconds", policy["window_seconds"])
        if strategy == TokenBucketLimiter.name:
            overrides.setdefault("burst", policy.get("limit") or self._config.default_burst)
        if strategy == LeakyBucketLimiter.name:
            overrides.setdefault("capacity", policy.get("limit") or self._config.default_burst)
        return create_rate_limit_strategy(strategy, self._config, **overrides)

    def limiter_for(self, key: str) -> RateLimitStrategy:
        with self._lock:
            if key not in self._limiters:
                policy = self._policies.get(key) or {
                    "strategy": self._config.default_rate_limit_strategy,
                    "limit": None,
                    "window_seconds": None,
                    "overrides": {},
                }
                self._limiters[key] = self._build(policy)
            return self._limiters[key]

    def check(self, key: str, cost: int = 1) -> RateLimitDecision:
        return self.limiter_for(key).check(key, cost=cost)

    def enforce(self, key: str, cost: int = 1) -> RateLimitDecision:
        """Check and raise :class:`RateLimitExceededError` when denied."""
        decision = self.check(key, cost=cost)
        if not decision.allowed:
            raise RateLimitExceededError(
                key=key,
                strategy=decision.strategy,
                retry_after=decision.retry_after,
                limit=decision.limit,
            )
        return decision

    def status(self, key: str) -> dict[str, Any]:
        return self.limiter_for(key).status(key)

    def reset(self, key: str) -> None:
        with self._lock:
            if key in self._limiters:
                self._limiters[key].reset(key)

    def reset_all(self) -> None:
        with self._lock:
            for limiter in self._limiters.values():
                for key in _strategy_keys(limiter):
                    limiter.reset(key)

    def policies(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {key: dict(policy) for key, policy in self._policies.items()}


def _strategy_keys(strategy: RateLimitStrategy) -> list[str]:
    """Extract known keys from a strategy's internal state (for reset_all)."""
    for attr in ("_tokens", "_queues", "_windows", "_counts"):
        container = getattr(strategy, attr, None)
        if isinstance(container, defaultdict):
            return list(container.keys())
    return []
