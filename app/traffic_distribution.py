"""Adaptive Traffic Distribution — weighted routing with canary, A/B, shadow, and starvation prevention."""

from __future__ import annotations

import random
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

REBALANCE_INTERVAL = 60
MIN_WEIGHT = 0.01
STARVATION_LOOKBACK = 100


@dataclass
class CanaryConfig:
    provider: str = ""
    model: str = ""
    max_traffic_share: float = 0.05
    min_confidence_requests: int = 100


@dataclass
class ABTestConfig:
    name: str = ""
    control_provider: str = ""
    control_model: str = ""
    variant_provider: str = ""
    variant_model: str = ""
    traffic_split: float = 0.5


@dataclass
class ShadowConfig:
    provider: str = ""
    model: str = ""
    capture_metrics: bool = True


@dataclass
class TrafficDistributionConfig:
    enabled: bool = True
    rebalance_interval_seconds: int = REBALANCE_INTERVAL
    min_weight: float = MIN_WEIGHT
    starvation_lookback: int = STARVATION_LOOKBACK
    canary: CanaryConfig | None = None
    ab_tests: list[ABTestConfig] = field(default_factory=list)
    shadow: ShadowConfig | None = None


@dataclass
class ProviderWeight:
    provider: str = ""
    model: str = ""
    score: float = 0.0
    weight: float = 0.0
    is_canary: bool = False
    is_shadow: bool = False
    assigned_requests: int = 0


@dataclass
class SelectionResult:
    provider: str = ""
    model: str = ""
    score: float = 0.0
    weight: float = 0.0
    ab_test_name: str = ""
    is_variant: bool = False
    shadow_provider: str = ""
    shadow_model: str = ""


class TrafficDistribution:
    """Adaptive traffic distribution with weighted selection, rebalancing, and special modes."""

    def __init__(self, config: TrafficDistributionConfig | None = None):
        self._config = config or TrafficDistributionConfig()
        self._weights: dict[str, ProviderWeight] = {}
        self._lock = threading.RLock()
        self._last_rebalance: float = 0
        self._selection_history: dict[str, int] = defaultdict(int)
        self._total_selections: int = 0
        self._rebalance_thread: threading.Thread | None = None
        self._running = False

    # --- Properties ---

    @property
    def config(self) -> TrafficDistributionConfig:
        return self._config

    @config.setter
    def config(self, value: TrafficDistributionConfig) -> None:
        self._config = value

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    # --- Weight computation ---

    def _compute_weights(self, scored: list[tuple[float, str, str]]) -> list[ProviderWeight]:
        """Convert raw scores to normalized weights with starvation prevention."""
        if not scored:
            return []

        raw: list[ProviderWeight] = []
        for score, provider, model in scored:
            pw = ProviderWeight(provider=provider, model=model, score=score)
            pw.is_canary = self._is_canary(provider, model)
            pw.is_shadow = self._is_shadow(provider, model)
            raw.append(pw)

        scores = [pw.score for pw in raw]
        min_s = min(scores)
        max_s = max(scores)
        score_range = max_s - min_s

        if score_range == 0:
            normalized = [1.0] * len(raw)
        else:
            normalized = [(s - min_s) / score_range for s in scores]

        for pw, norm in zip(raw, normalized, strict=False):
            pw.weight = norm

        self._apply_starvation_floor(raw)

        self._apply_canary_cap(raw)

        total = sum(pw.weight for pw in raw)
        if total > 0:
            for pw in raw:
                pw.weight /= total

        return raw

    @staticmethod
    def _apply_starvation_floor(weights: list[ProviderWeight]) -> None:
        """Ensure every non-shadow provider gets at least MIN_WEIGHT traffic share."""
        total = sum(w.weight for w in weights)
        if total <= 0:
            n = len([w for w in weights if not w.is_shadow])
            if n > 0:
                equal = 1.0 / len(weights)
                for w in weights:
                    w.weight = equal
            return

        for w in weights:
            w.weight /= total

        eligible = [w for w in weights if not w.is_shadow]
        deficit = 0.0
        for w in eligible:
            if w.weight < MIN_WEIGHT:
                deficit += MIN_WEIGHT - w.weight
                w.weight = MIN_WEIGHT

        if deficit > 0:
            above = [w for w in eligible if w.weight > MIN_WEIGHT]
            if above:
                above_excess = sum(w.weight - MIN_WEIGHT for w in above)
                reduction_ratio = min(1.0, deficit / above_excess) if above_excess > 0 else 0
                for w in above:
                    w.weight -= (w.weight - MIN_WEIGHT) * reduction_ratio

        total = sum(w.weight for w in weights)
        if total > 0:
            for w in weights:
                w.weight /= total

    def _apply_canary_cap(self, weights: list[ProviderWeight]) -> None:
        canary = self._config.canary
        if not canary:
            return
        for pw in weights:
            if pw.is_canary and pw.weight > canary.max_traffic_share:
                excess = pw.weight - canary.max_traffic_share
                pw.weight = canary.max_traffic_share
                eligible = [w for w in weights if not w.is_canary and not w.is_shadow]
                if eligible:
                    share = excess / len(eligible)
                    for w in eligible:
                        w.weight += share

    def _is_canary(self, provider: str, model: str) -> bool:
        c = self._config.canary
        return bool(c and c.provider == provider and c.model == model)

    def _is_shadow(self, provider: str, model: str) -> bool:
        s = self._config.shadow
        return bool(s and s.provider == provider and s.model == model)

    # --- Selection ---

    def select(
        self,
        scored: list[tuple[float, str, str]] | list[tuple[str, str]],
    ) -> SelectionResult | None:
        if not scored:
            return None

        if scored and isinstance(scored[0], tuple) and len(scored[0]) == 2:
            ranked_list = [(100.0, p, m) for p, m in scored]
        else:
            ranked_list = scored

        with self._lock:
            if self._needs_rebalance():
                self._rebuild_weights(ranked_list)

            weights = list(self._weights.values())
            if not weights:
                self._rebuild_weights(ranked_list)
                weights = list(self._weights.values())

        ab_result = self._check_ab_test(ranked_list)

        selected: ProviderWeight | None = None
        if self._config.enabled and weights:
            selected = self._weighted_pick(weights)
        else:
            best = ranked_list[0]
            key = f"{best[1]}::{best[2]}"
            selected = next(
                (w for w in weights if f"{w.provider}::{w.model}" == key),
                None,
            )
            if not selected:
                selected = ProviderWeight(
                    provider=best[1],
                    model=best[2],
                    score=best[0],
                    weight=1.0,
                )

        if not selected:
            best = ranked_list[0]
            selected = ProviderWeight(provider=best[1], model=best[2], score=best[0], weight=1.0)

        with self._lock:
            self._selection_history[selected.provider] += 1
            self._total_selections += 1
            selected.assigned_requests += 1

        result = SelectionResult(
            provider=selected.provider,
            model=selected.model,
            score=selected.score,
            weight=selected.weight,
        )

        if ab_result:
            result.ab_test_name = ab_result[0]
            result.is_variant = ab_result[1]
            if ab_result[1]:
                result.provider = ab_result[2]
                result.model = ab_result[3]

        shadow = self._config.shadow
        if shadow:
            result.shadow_provider = shadow.provider
            result.shadow_model = shadow.model

        return result

    def _weighted_pick(self, weights: list[ProviderWeight]) -> ProviderWeight | None:
        if not weights:
            return None
        total = sum(pw.weight for pw in weights)
        if total <= 0:
            return random.choice(weights)
        r = random.random() * total
        cumulative = 0.0
        for pw in weights:
            cumulative += pw.weight
            if r <= cumulative:
                return pw
        return weights[-1]

    def _check_ab_test(self, scored: list[tuple[float, str, str]]) -> tuple[str, bool, str, str] | None:
        for ab in self._config.ab_tests:
            if random.random() < ab.traffic_split:
                return (ab.name, True, ab.variant_provider, ab.variant_model)
            return (ab.name, False, ab.control_provider, ab.control_model)
        return None

    # --- Rebalancing ---

    def _needs_rebalance(self) -> bool:
        return (time.time() - self._last_rebalance) > self._config.rebalance_interval_seconds

    def _rebuild_weights(self, scored: list[tuple[float, str, str]]) -> None:
        self._weights.clear()
        for pw in self._compute_weights(scored):
            self._weights[f"{pw.provider}::{pw.model}"] = pw
        self._last_rebalance = time.time()

    def force_rebalance(self, scored: list[tuple[float, str, str]] | None = None) -> None:
        with self._lock:
            if scored:
                self._rebuild_weights(scored)

    # --- Background rebalancing ---

    def start(self, scored_provider: callable | None = None) -> None:
        if self._running:
            return
        self._running = True
        self._rebalance_thread = threading.Thread(
            target=self._rebalance_loop,
            args=(scored_provider,),
            daemon=True,
        )
        self._rebalance_thread.start()

    def stop(self) -> None:
        self._running = False

    def _rebalance_loop(self, scored_provider: callable | None) -> None:
        while self._running:
            time.sleep(self._config.rebalance_interval_seconds)
            if self._needs_rebalance() and scored_provider:
                try:
                    scored = scored_provider()
                    if scored:
                        with self._lock:
                            self._rebuild_weights(scored)
                except Exception:
                    pass

    # --- Stats ---

    def get_weights(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "provider": pw.provider,
                    "model": pw.model,
                    "score": round(pw.score, 2),
                    "weight": round(pw.weight, 4),
                    "is_canary": pw.is_canary,
                    "is_shadow": pw.is_shadow,
                    "assigned_requests": pw.assigned_requests,
                }
                for pw in sorted(
                    self._weights.values(),
                    key=lambda x: x.weight,
                    reverse=True,
                )
            ]

    def get_distribution_report(self) -> dict[str, Any]:
        with self._lock:
            weights = self.get_weights()
            total = self._total_selections
            selection_pct = {}
            if total > 0:
                for pw in self._weights.values():
                    selection_pct[pw.provider] = round(self._selection_history.get(pw.provider, 0) / total * 100, 2)
            return {
                "enabled": self._config.enabled,
                "rebalance_interval_seconds": self._config.rebalance_interval_seconds,
                "min_weight": self._config.min_weight,
                "total_selections": total,
                "selection_percentages": selection_pct,
                "weights": weights,
                "canary": {
                    "active": self._config.canary is not None,
                    "config": (
                        {
                            "provider": self._config.canary.provider,
                            "model": self._config.canary.model,
                            "max_traffic_share": self._config.canary.max_traffic_share,
                        }
                        if self._config.canary
                        else None
                    ),
                },
                "ab_tests": [
                    {
                        "name": ab.name,
                        "control": f"{ab.control_provider}/{ab.control_model}",
                        "variant": f"{ab.variant_provider}/{ab.variant_model}",
                        "traffic_split": ab.traffic_split,
                    }
                    for ab in self._config.ab_tests
                ],
                "shadow": {
                    "active": self._config.shadow is not None,
                    "provider": self._config.shadow.provider if self._config.shadow else None,
                    "model": self._config.shadow.model if self._config.shadow else None,
                },
            }

    def reset_stats(self) -> None:
        with self._lock:
            self._selection_history.clear()
            self._total_selections = 0
            for pw in self._weights.values():
                pw.assigned_requests = 0


traffic_distribution = TrafficDistribution()
