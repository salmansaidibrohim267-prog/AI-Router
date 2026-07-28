import time
import pytest
from app.rate_limit import (
    RateLimitConfig,
    TokenBucket,
    SlidingWindowRateLimiter,
    RateLimiter,
)


class TestTokenBucket:
    def setup_method(self):
        self.bucket = TokenBucket(rate=10.0, burst=5)

    def test_consume_success(self):
        assert self.bucket.consume(1) is True

    def test_consume_exceeds_burst(self):
        for _ in range(5):
            self.bucket.consume(1)
        assert self.bucket.consume(1) is False

    def test_get_wait_time_zero_when_available(self):
        assert self.bucket.get_wait_time(1) == 0.0


class TestSlidingWindowRateLimiter:
    def setup_method(self):
        self.limiter = SlidingWindowRateLimiter(requests=5, window_seconds=60)

    def test_is_allowed_below_limit(self):
        allowed, _ = self.limiter.is_allowed("test_key")
        assert allowed is True

    def test_is_allowed_above_limit(self):
        for _ in range(5):
            self.limiter.is_allowed("test_key")
        allowed, info = self.limiter.is_allowed("test_key")
        assert allowed is False
        assert info["remaining"] == 0

    def test_is_allowed_with_cost(self):
        self.limiter.is_allowed("key", cost=5)
        allowed, _ = self.limiter.is_allowed("key")
        assert allowed is False

    def test_get_status(self):
        for _ in range(3):
            self.limiter.is_allowed("key")
        status = self.limiter.get_status("key")
        assert status["used"] == 3
        assert status["limit"] == 5
        assert status["remaining"] == 2


class TestRateLimiter:
    def setup_method(self):
        self.limiter = RateLimiter()

    def test_set_limit(self):
        config = RateLimitConfig(requests=10, window_seconds=30)
        self.limiter.set_limit("custom", config)
        assert "custom" in self.limiter._limiters

    def test_is_allowed_default(self):
        allowed, _ = self.limiter.is_allowed("default_key")
        assert allowed is True

    def test_is_allowed_blocks(self):
        for _ in range(100):
            self.limiter.is_allowed("busy_key")
        allowed, _ = self.limiter.is_allowed("busy_key")
        assert allowed is False

    def test_get_status(self):
        self.limiter.is_allowed("key")
        status = self.limiter.get_status("key")
        assert "used" in status
        assert "limit" in status

    def test_reset(self):
        for _ in range(100):
            self.limiter.is_allowed("key")
        self.limiter.reset("key")
        allowed, _ = self.limiter.is_allowed("key")
        assert allowed is True

    def test_set_default(self):
        config = RateLimitConfig(requests=5, window_seconds=10)
        self.limiter.set_default(config)
        assert self.limiter._default_config.requests == 5
