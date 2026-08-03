from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Callable

from app.distributed.models import RetryPolicy

logger = logging.getLogger(__name__)


class ExponentialBackoff:
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, multiplier: float = 2.0, jitter: float = 0.1):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (self.multiplier**attempt), self.max_delay)
        jitter_amount = delay * self.jitter
        return delay + random.uniform(-jitter_amount, jitter_amount)


class RetryPolicyManager:
    def __init__(self, policy: RetryPolicy | None = None):
        self._policy = policy or RetryPolicy()

    @property
    def policy(self) -> RetryPolicy:
        return self._policy

    def should_retry(self, attempt: int, error: Exception | None = None) -> bool:
        return attempt < self._policy.max_retries

    def get_delay(self, attempt: int) -> float:
        return self._policy.get_delay(attempt)

    async def execute_with_retry(
        self,
        fn: Callable[[], Any],
        on_retry: Callable[[int, Exception], Any] | None = None,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(self._policy.max_retries + 1):
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except Exception as e:
                last_error = e
                if not self.should_retry(attempt, e):
                    raise
                delay = self.get_delay(attempt)
                logger.warning(f"Retry {attempt + 1}/{self._policy.max_retries} after {delay:.2f}s: {e}")
                if on_retry:
                    if asyncio.iscoroutinefunction(on_retry):
                        await on_retry(attempt, e)
                    else:
                        on_retry(attempt, e)
                await asyncio.sleep(delay)
        if last_error:
            raise last_error
        return None
