"""Adaptive routing engine with multi-dimensional scoring."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.capability_registry import capability_registry
from app.costs import MODEL_COST_OVERRIDES, PROVIDER_COST_PER_1K
from app.token_intelligence import token_intelligence

ROLLING_WINDOW = 100
EWMA_ALPHA = 0.3


class OptimizationMode(str, Enum):
    QUALITY = "quality"
    BALANCED = "balanced"
    CHEAPEST = "cheapest"
    FASTEST = "fastest"


MODE_WEIGHTS: dict[OptimizationMode, dict[str, float]] = {
    OptimizationMode.QUALITY: {
        "latency": 0.20,
        "reliability": 0.35,
        "cost": 0.05,
        "config": 0.10,
        "preference": 0.10,
        "context": 0.15,
        "recency": 0.05,
    },
    OptimizationMode.BALANCED: {
        "latency": 0.25,
        "reliability": 0.25,
        "cost": 0.15,
        "config": 0.10,
        "preference": 0.10,
        "context": 0.10,
        "recency": 0.05,
    },
    OptimizationMode.CHEAPEST: {
        "latency": 0.10,
        "reliability": 0.15,
        "cost": 0.40,
        "config": 0.10,
        "preference": 0.10,
        "context": 0.10,
        "recency": 0.05,
    },
    OptimizationMode.FASTEST: {
        "latency": 0.40,
        "reliability": 0.20,
        "cost": 0.05,
        "config": 0.10,
        "preference": 0.10,
        "context": 0.10,
        "recency": 0.05,
    },
}


PERFECT_COST: float = 0.04


@dataclass
class RoutingContext:
    """Context for a routing decision."""

    task: str = ""
    prompt_token_estimate: int = 0
    expected_completion_tokens: int = 0
    optimization_mode: OptimizationMode = OptimizationMode.BALANCED
    user_preference: str | None = None
    retry_attempt: int = 0
    required_capabilities: set[str] = field(default_factory=set)


@dataclass
class ProviderReputation:
    """Reputation snapshot for a provider at scoring time."""

    success_rate: float = 0.0
    avg_latency: float = 0.0
    ewma_latency: float = 0.0
    avg_cost: float = 0.0
    consecutive_success: int = 0
    consecutive_failure: int = 0
    rolling_success_rate: float = 1.0
    rolling_failure_rate: float = 0.0
    recent_error_rate: float = 0.0
    total_requests: int = 0
    uptime_seconds: float = 0.0
    last_failure_ago: float = 0.0
    last_success_ago: float = 0.0
    reputation_score: float = 50.0
    trend_delta: float = 0.0
    circuit_breaker_multiplier: float = 1.0
    benchmark_score: float = 50.0


def build_reputation(
    metrics: Any, now: float | None = None, circuit_breaker_state: str | None = None
) -> ProviderReputation:  # noqa: E501
    """Build a reputation snapshot from provider metrics.

    Includes dynamic reputation score, trend analysis, and circuit breaker multiplier.
    """
    if now is None:
        now = time.time()

    from app.benchmark.live import live_benchmark
    from app.reputation import circuit_breaker_multiplier, compute_reputation, compute_trend

    trend_data = compute_trend(metrics.request_history) if hasattr(metrics, "request_history") else None
    trend_delta = trend_data.score_delta if trend_data else 0.0

    rep_score = compute_reputation(
        success_rate=metrics.success_rate,
        ewma_latency=metrics.ewma_latency,
        avg_cost=metrics.avg_cost,
        uptime_seconds=getattr(metrics, "uptime_seconds", 0.0),
        consecutive_success=metrics.consecutive_success,
        consecutive_failure=metrics.consecutive_failures,
    )

    cb_mult = circuit_breaker_multiplier(circuit_breaker_state)

    bm = live_benchmark.get_or_create(metrics.name) if hasattr(metrics, "name") and metrics.name else None
    benchmark_score = bm.get_aggregated_score() if bm else 50.0

    return ProviderReputation(
        success_rate=metrics.success_rate,
        avg_latency=metrics.avg_latency if metrics.avg_latency != float("inf") else 0.0,
        ewma_latency=metrics.ewma_latency,
        avg_cost=metrics.avg_cost,
        consecutive_success=metrics.consecutive_success,
        consecutive_failure=metrics.consecutive_failures,
        rolling_success_rate=metrics.rolling_success_rate,
        rolling_failure_rate=metrics.rolling_failure_rate,
        recent_error_rate=1.0 - metrics.rolling_success_rate,
        total_requests=metrics.total_requests,
        uptime_seconds=getattr(metrics, "uptime_seconds", 0.0),
        last_failure_ago=now - metrics.last_failure_time if metrics.last_failure_time > 0 else float("inf"),
        last_success_ago=now - metrics.last_success_time if metrics.last_success_time > 0 else float("inf"),
        reputation_score=rep_score,
        trend_delta=trend_delta,
        circuit_breaker_multiplier=cb_mult,
        benchmark_score=benchmark_score,
    )


def estimate_prompt_tokens(text: str, model: str = "", provider: str = "") -> int:
    """Estimate tokens using token intelligence engine, with fallback."""
    if model:
        return token_intelligence.estimate(text, model, provider)
    return max(1, len(text) // 4)


def get_model_context_window(model: str, provider: str = "") -> int | None:
    """Get context window for a model from the capability registry."""
    model_key = model.split("/")[-1] if "/" in model else model
    if provider:
        ctx = capability_registry.get_context_window(provider, model_key)
        if ctx is not None:
            return ctx
    cap = capability_registry.get_by_model(model_key)
    return cap.context_window if cap else None


def get_model_cost(provider: str, model: str) -> float:
    """Get combined prompt+completion cost per 1K tokens."""
    model_key = model.split("/")[-1] if "/" in model else model
    if model_key in MODEL_COST_OVERRIDES:
        p = MODEL_COST_OVERRIDES[model_key]
    else:
        p = PROVIDER_COST_PER_1K.get(provider, {"prompt": 0.01, "completion": 0.03})
    return p["prompt"] + p["completion"]


class RoutingEngine:
    """Adaptive routing engine with configurable multi-dimensional scoring."""

    def __init__(self, mode: OptimizationMode | str = OptimizationMode.BALANCED):
        if isinstance(mode, str):
            mode = OptimizationMode(mode)
        self._mode = mode

    @property
    def mode(self) -> OptimizationMode:
        return self._mode

    def set_mode(self, mode: OptimizationMode | str) -> None:
        if isinstance(mode, str):
            mode = OptimizationMode(mode)
        self._mode = mode

    def get_weights(self) -> dict[str, float]:
        return dict(MODE_WEIGHTS[self._mode])

    def score_provider(
        self,
        provider: str,
        model: str,
        rep: ProviderReputation,
        health_status: Any,
        base_score: int,
        context: RoutingContext,
    ) -> float:
        """Multi-dimensional provider scoring. Higher score = better candidate.

        Combines latency, reliability, cost, config preference, user preference,
        context window suitability, recency, and failure penalties.
        """
        if health_status is not None:
            from app.models import ProviderStatus

            if getattr(health_status, "status", health_status) != ProviderStatus.HEALTHY:
                return -99999.0

        w = MODE_WEIGHTS[self._mode]

        # Latency score: 0-100, lower EWMA = better
        ewma = rep.ewma_latency
        if ewma <= 0:
            latency_score = 100.0
        else:
            latency_score = max(0.0, 100.0 - ewma / 5.0)

        # Reliability score: rolling success rate * 100
        reliability_score = rep.rolling_success_rate * 100.0

        # Cost score: 0-100, cheaper = higher
        cost = get_model_cost(provider, model)
        cost_score = max(0.0, 100.0 - (cost / PERFECT_COST) * 100.0)

        # Config score
        config_score = float(base_score)

        # User preference
        pref_score = 100.0 if (context.user_preference and context.user_preference.lower() == provider.lower()) else 0.0

        # Context suitability
        ctx_window = get_model_context_window(model)
        if ctx_window and context.prompt_token_estimate > ctx_window:
            ctx_score = -5000.0
        elif ctx_window:
            ratio = context.prompt_token_estimate / ctx_window
            ctx_score = max(0.0, 100.0 - ratio * 100.0)
        else:
            ctx_score = 50.0

        # Recency / adaptive learning bonus
        consec_bonus = min(rep.consecutive_success * 5.0, 25.0)
        consec_penalty = min(rep.consecutive_failure * 10.0, 100.0)
        recency_score = consec_bonus - consec_penalty

        # Failure penalty
        failure_penalty = rep.rolling_failure_rate * -100.0

        # Retry penalty (each retry reduces score for alternative providers)
        retry_penalty = context.retry_attempt * -50.0

        # Dynamic reputation score (0-100, from reputation engine)
        reputation_score = rep.reputation_score

        # Trend delta (from trend detection)
        trend_delta = rep.trend_delta

        # Live benchmark score (0-100, from rolling window performance)
        benchmark_score = rep.benchmark_score

        # Capability penalty: if model lacks a required capability, exclude it
        capability_penalty = 0.0
        if context.required_capabilities:
            for cap in context.required_capabilities:
                if not capability_registry.has_capability(provider, model, cap):
                    capability_penalty -= 50000.0

        score = (
            latency_score * w["latency"]
            + reliability_score * w["reliability"]
            + cost_score * w["cost"]
            + config_score * w["config"]
            + pref_score * w["preference"]
            + ctx_score * w["context"]
            + recency_score * w["recency"]
            + reputation_score * 0.10  # reputation as 10% factor
            + trend_delta  # trend directly affects score
            + benchmark_score * 0.05  # live benchmark as 5% factor
            + failure_penalty
            + retry_penalty
            + capability_penalty
        )
        # Circuit breaker multiplier: closed=100%, half-open=40%, open=0%
        score *= rep.circuit_breaker_multiplier
        return score

    def rank_providers(
        self,
        candidates: list[tuple[str, str]],
        metrics_map: dict[str, Any],
        provider_manager: Any,
        context: RoutingContext,
        return_scores: bool = False,
    ) -> list[tuple[str, str]] | list[tuple[float, str, str]]:
        """Rank provider-model pairs by adaptive score. Highest first.

        If return_scores=True, returns list of (score, provider, model) tuples.
        """
        now = time.time()
        scored: list[tuple[float, str, str]] = []
        for provider, model in candidates:
            m = metrics_map.get(provider)
            from app.providers.manager import ProviderManager

            if isinstance(provider_manager, ProviderManager):
                cb_state = provider_manager.get_circuit_state(provider)
            else:
                cb_state = None
            rep = build_reputation(m, now, circuit_breaker_state=cb_state) if m else ProviderReputation()
            h = provider_manager.get_health_status(provider)
            if isinstance(h, dict):
                h = h.get(provider)
            score = self.score_provider(provider, model, rep, h, 0, context)
            scored.append((score, provider, model))
        scored.sort(key=lambda x: x[0], reverse=True)
        if return_scores:
            return scored
        return [(p, m) for _, p, m in scored]


routing_engine = RoutingEngine()
