"""Statistics tracking for AI Router."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.models import StatsSummary, TaskType


@dataclass
class ModelStats:
    """Statistics for a specific model."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    last_request_time: float = 0
    last_latency_ms: float = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency_ms / self.successful_requests

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def failure_rate(self) -> float:
        return 1.0 - self.success_rate


@dataclass
class ProviderStats:
    """Statistics for a provider."""
    models: dict[str, ModelStats] = field(default_factory=lambda: defaultdict(ModelStats))
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests


class RouterStats:
    """Global router statistics."""

    def __init__(self):
        self._lock = threading.RLock()
        self.providers: dict[str, ProviderStats] = defaultdict(ProviderStats)
        self.tasks: dict[TaskType, int] = defaultdict(int)
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.failed_requests: int = 0
        self.total_latency_ms: float = 0.0
        self.start_time: float = time.time()

    def record(
        self,
        provider: str,
        model: str,
        task: TaskType,
        latency_ms: float,
        success: bool,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """Record a request."""
        with self._lock:
            self.total_requests += 1
            self.total_latency_ms += latency_ms
            self.tasks[task] += 1

            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1

            # Provider stats
            pstats = self.providers[provider]
            pstats.total_requests += 1
            pstats.total_latency_ms += latency_ms
            if success:
                pstats.successful_requests += 1
            else:
                pstats.failed_requests += 1

            # Model stats
            mstats = pstats.models[model]
            mstats.total_requests += 1
            mstats.last_request_time = time.time()
            mstats.last_latency_ms = latency_ms
            if success:
                mstats.successful_requests += 1
                mstats.total_latency_ms += latency_ms
                mstats.min_latency_ms = min(mstats.min_latency_ms, latency_ms)
                mstats.max_latency_ms = max(mstats.max_latency_ms, latency_ms)
                mstats.total_prompt_tokens += prompt_tokens
                mstats.total_completion_tokens += completion_tokens
                mstats.total_tokens += total_tokens
            else:
                mstats.failed_requests += 1

    def summary(self) -> StatsSummary:
        """Get statistics summary."""
        with self._lock:
            avg_latency = 0.0
            if self.total_requests > 0:
                avg_latency = self.total_latency_ms / self.total_requests

            success_rate = 0.0
            if self.total_requests > 0:
                success_rate = self.successful_requests / self.total_requests

            provider_usage = {
                name: stats.total_requests
                for name, stats in self.providers.items()
            }

            model_usage = {}
            for pstats in self.providers.values():
                for model, mstats in pstats.models.items():
                    model_usage[model] = mstats.total_requests

            task_usage = {task.value: count for task, count in self.tasks.items()}

            # Provider ranking by success rate and latency
            provider_ranking = sorted(
                [
                    {
                        "provider": name,
                        "requests": stats.total_requests,
                        "success_rate": stats.success_rate,
                        "avg_latency_ms": stats.total_latency_ms / stats.successful_requests if stats.successful_requests > 0 else 0,
                    }
                    for name, stats in self.providers.items()
                ],
                key=lambda x: (x["success_rate"], -x["avg_latency_ms"]),
                reverse=True,
            )

            # Model ranking
            model_ranking = sorted(
                [
                    {
                        "model": model,
                        "provider": provider,
                        "requests": mstats.total_requests,
                        "success_rate": mstats.success_rate,
                        "avg_latency_ms": mstats.avg_latency_ms,
                    }
                    for provider, pstats in self.providers.items()
                    for model, mstats in pstats.models.items()
                ],
                key=lambda x: (x["success_rate"], -x["avg_latency_ms"]),
                reverse=True,
            )

            return StatsSummary(
                total_requests=self.total_requests,
                successful_requests=self.successful_requests,
                failed_requests=self.failed_requests,
                average_latency_ms=round(avg_latency, 2),
                success_rate=round(success_rate, 4),
                failure_rate=round(1 - success_rate, 4),
                provider_usage=provider_usage,
                model_usage=model_usage,
                task_usage=task_usage,
                provider_ranking=provider_ranking[:10],
                model_ranking=model_ranking[:10],
            )

    def get_provider_stats(self, provider: str) -> dict[str, Any] | None:
        """Get stats for a specific provider."""
        with self._lock:
            if provider not in self.providers:
                return None
            pstats = self.providers[provider]
            return {
                "provider": provider,
                "total_requests": pstats.total_requests,
                "successful_requests": pstats.successful_requests,
                "failed_requests": pstats.failed_requests,
                "success_rate": pstats.success_rate,
                "avg_latency_ms": pstats.total_latency_ms / pstats.successful_requests if pstats.successful_requests > 0 else 0,
                "models": {
                    model: {
                        "requests": mstats.total_requests,
                        "success_rate": mstats.success_rate,
                        "avg_latency_ms": mstats.avg_latency_ms,
                        "min_latency_ms": mstats.min_latency_ms if mstats.min_latency_ms != float('inf') else 0,
                        "max_latency_ms": mstats.max_latency_ms,
                        "total_tokens": mstats.total_tokens,
                    }
                    for model, mstats in pstats.models.items()
                },
            }

    def get_model_stats(self, provider: str, model: str) -> dict[str, Any] | None:
        """Get stats for a specific model across all providers."""
        with self._lock:
            pstats = self.providers.get(provider)
            if not pstats or model not in pstats.models:
                return None
            mstats = pstats.models[model]
            return {
                "model": model,
                "provider": provider,
                "requests": mstats.total_requests,
                "success_rate": mstats.success_rate,
                "avg_latency_ms": mstats.avg_latency_ms,
                "min_latency_ms": mstats.min_latency_ms if mstats.min_latency_ms != float('inf') else 0,
                "max_latency_ms": mstats.max_latency_ms,
                "total_prompt_tokens": mstats.total_prompt_tokens,
                "total_completion_tokens": mstats.total_completion_tokens,
                "total_tokens": mstats.total_tokens,
                "last_request_time": mstats.last_request_time,
                "last_latency_ms": mstats.last_latency_ms,
            }

    def get_task_stats(self, task: TaskType | None = None) -> dict[str, Any]:
        """Get stats for tasks."""
        with self._lock:
            if task:
                count = self.tasks.get(task, 0)
                return {
                    "task": task.value,
                    "requests": count,
                    "percentage": count / self.total_requests * 100 if self.total_requests > 0 else 0,
                }
            return {t.value: count for t, count in self.tasks.items()}

    def get_error_stats(self) -> dict[str, int]:
        """Get error distribution statistics."""
        with self._lock:
            return {
                "total_errors": self.failed_requests,
                "success_rate": self.successful_requests / self.total_requests if self.total_requests > 0 else 1.0,
            }


    def _get_provider_latency(self):
        """Get provider latency for dashboard."""
        with self._lock:
            result = {}
            for name, pstats in self.providers.items():
                latency = pstats.total_latency_ms / pstats.successful_requests if pstats.successful_requests > 0 else 0
                obj = type("obj", (object,), {"avg_latency_ms": latency})()
                result[name] = obj
            return result
    def reset(self) -> None:
        """Reset all statistics."""
        with self._lock:
            self.providers.clear()
            self.tasks.clear()
            self.total_requests = 0
            self.successful_requests = 0
            self.failed_requests = 0
            self.total_latency_ms = 0.0
            self.start_time = time.time()

    def get_uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self.start_time


# Global stats instance
stats = RouterStats()