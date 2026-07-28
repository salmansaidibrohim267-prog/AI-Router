"""Rate limiting for AI Router."""

from __future__ import annotations

import time
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests: int = 100
    window_seconds: int = 60
    burst: int = 10


class TokenBucket:
    """Token bucket rate limiter."""

    def __init__(self, rate: float, burst: int):
        self.rate = rate  # tokens per second
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.time()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get estimated wait time for tokens."""
        with self._lock:
            if self.tokens >= tokens:
                return 0.0
            return (tokens - self.tokens) / self.rate


class SlidingWindowRateLimiter:
    """Sliding window rate limiter."""

    def __init__(self, requests: int, window_seconds: int):
        self.requests = requests
        self.window_seconds = window_seconds
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _cleanup_old(self, key: str, now: float) -> None:
        """Remove timestamps outside the window."""
        window = self._windows[key]
        cutoff = now - self.window_seconds
        while window and window[0] < cutoff:
            window.popleft()

    def is_allowed(self, key: str, cost: int = 1) -> tuple[bool, dict[str, Any]]:
        """Check if request is allowed."""
        now = time.time()

        with self._lock:
            self._cleanup_old(key, now)
            window = self._windows[key]

            if len(window) + cost <= self.requests:
                for _ in range(cost):
                    window.append(now)
                return True, {
                    "allowed": True,
                    "remaining": self.requests - len(window),
                    "reset_time": window[0] + self.window_seconds if window else now + self.window_seconds,
                }

            return False, {
                "allowed": False,
                "remaining": 0,
                "reset_time": window[0] + self.window_seconds if window else now + self.window_seconds,
                "retry_after": int(window[0] + self.window_seconds - now) + 1,
            }

    def get_status(self, key: str) -> dict[str, Any]:
        """Get current rate limit status."""
        now = time.time()

        with self._lock:
            self._cleanup_old(key, now)
            window = self._windows[key]

            return {
                "used": len(window),
                "limit": self.requests,
                "remaining": max(0, self.requests - len(window)),
                "reset_time": window[0] + self.window_seconds if window else now + self.window_seconds,
            }


class RateLimiter:
    """Combined rate limiter with multiple strategies."""

    def __init__(self):
        self._limiters: dict[str, SlidingWindowRateLimiter] = {}
        self._configs: dict[str, RateLimitConfig] = {}
        self._lock = threading.RLock()
        self._default_config = RateLimitConfig()

    def set_limit(self, key: str, config: RateLimitConfig) -> None:
        """Set rate limit for a key."""
        with self._lock:
            self._configs[key] = config
            self._limiters[key] = SlidingWindowRateLimiter(
                config.requests,
                config.window_seconds,
            )

    def get_limiter(self, key: str) -> SlidingWindowRateLimiter:
        """Get or create limiter for key."""
        with self._lock:
            if key not in self._limiters:
                config = self._configs.get(key, self._default_config)
                self._limiters[key] = SlidingWindowRateLimiter(
                    config.requests,
                    config.window_seconds,
                )
            return self._limiters[key]

    def is_allowed(
        self,
        key: str,
        cost: int = 1,
    ) -> tuple[bool, dict[str, Any]]:
        """Check if request is allowed."""
        limiter = self.get_limiter(key)
        return limiter.is_allowed(key, cost)

    def get_status(self, key: str) -> dict[str, Any]:
        """Get rate limit status."""
        limiter = self.get_limiter(key)
        return limiter.get_status(key)

    def reset(self, key: str) -> None:
        """Reset rate limit for key."""
        with self._lock:
            if key in self._limiters:
                self._limiters[key] = SlidingWindowRateLimiter(
                    self._configs.get(key, self._default_config).requests,
                    self._configs.get(key, self._default_config).window_seconds,
                )

    def set_default(self, config: RateLimitConfig) -> None:
        """Set default rate limit config."""
        self._default_config = config


# Global rate limiter
rate_limiter = RateLimiter()