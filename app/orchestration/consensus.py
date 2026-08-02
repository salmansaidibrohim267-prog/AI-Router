from __future__ import annotations

import asyncio
import time
from typing import Any

from app.orchestration.models import ConsensusResult, ConsensusStrategy, VoteScore
from app.orchestration.metrics import consensus_count_total
from app.router import AIRouter
from app.models import ChatRequest, Message, MessageRole


class VotingEngine:
    def score_response(
        self,
        content: str,
        latency_ms: float,
        provider: str,
        model: str,
    ) -> VoteScore:
        quality = self._score_quality(content)
        cost = self._score_cost(provider, model)
        latency = self._score_latency(latency_ms)
        reliability = self._score_reliability(provider, model)
        overall = quality * 0.35 + cost * 0.15 + latency * 0.25 + reliability * 0.25
        return VoteScore(quality=quality, cost=cost, latency=latency, reliability=reliability, overall=overall)

    def _score_quality(self, content: str) -> float:
        if not content:
            return 0.0
        length = len(content)
        if length < 10:
            return 0.2
        if length < 50:
            return 0.5
        if length > 10000:
            return 0.8
        score = 0.6
        if any(word in content.lower() for word in ["therefore", "because", "however", "conclusion"]):
            score += 0.1
        if any(c in content for c in [".", "!", "?"]):
            score += 0.1
        if any(word in content.lower() for word in ["example", "for instance", "specifically"]):
            score += 0.1
        return min(score, 1.0)

    def _score_cost(self, provider: str, model: str) -> float:
        from app.costs import token_accounting
        try:
            cost_info = token_accounting.estimate_cost(provider, model, 100, 100)
            if cost_info <= 0:
                return 1.0
            return max(0.0, 1.0 - (cost_info / 0.01))
        except Exception:
            return 0.5

    def _score_latency(self, latency_ms: float) -> float:
        if latency_ms <= 0:
            return 0.5
        if latency_ms < 500:
            return 1.0
        if latency_ms < 2000:
            return 0.8
        if latency_ms < 5000:
            return 0.5
        if latency_ms < 10000:
            return 0.3
        return 0.1

    def _score_reliability(self, provider: str, model: str) -> float:
        from app.router import router
        stats = router.get_provider_stats()
        if provider in stats:
            p = stats[provider]
            success_rate = p.get("success_rate", 1.0)
            return success_rate
        return 0.8

    def choose_winner(self, votes: list[tuple[str, str, str, VoteScore]]) -> tuple[str, str, str, VoteScore]:
        if not votes:
            return "", "", "", VoteScore()
        sorted_votes = sorted(votes, key=lambda v: v[3].overall, reverse=True)
        return sorted_votes[0]


class ConsensusEngine:
    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._voting = VotingEngine()

    async def run_consensus(
        self,
        request: ChatRequest,
        providers: list[str],
        router: AIRouter,
        strategy: str = "majority_vote",
    ) -> ConsensusResult:
        consensus_count_total.labels(strategy=strategy).inc()

        responses: list[tuple[str, str, str, float]] = []

        async def query_provider(provider: str) -> tuple[str, str, str, float] | None:
            try:
                req_copy = request.model_copy()
                start = time.perf_counter()
                response = await router.chat(req_copy)
                latency = (time.perf_counter() - start) * 1000
                content = response.choices[0].message.content if response.choices else ""
                model = getattr(response, "model", "")
                return provider, model, content, latency
            except Exception:
                return None

        tasks = [query_provider(p) for p in providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_responses: list[tuple[str, str, str, float]] = []
        for r in results:
            if isinstance(r, tuple) and r[2]:
                valid_responses.append(r)

        if not valid_responses:
            return ConsensusResult(
                provider="",
                model="",
                content="",
                strategy=strategy,
                scores={},
            )

        strategy_enum = ConsensusStrategy(strategy)

        if strategy_enum == ConsensusStrategy.FIRST_SUCCESS:
            provider, model, content, latency = valid_responses[0]
            return ConsensusResult(
                provider=provider,
                model=model,
                content=content,
                strategy=strategy,
                votes=1,
                total_votes=len(providers),
            )

        if strategy_enum == ConsensusStrategy.BEST_LATENCY:
            best = min(valid_responses, key=lambda r: r[3])
            return ConsensusResult(
                provider=best[0],
                model=best[1],
                content=best[2],
                strategy=strategy,
                scores={"latency_ms": best[3]},
                votes=1,
                total_votes=len(providers),
            )

        if strategy_enum in (ConsensusStrategy.WEIGHTED_SCORE, ConsensusStrategy.HIGHEST_CONFIDENCE, ConsensusStrategy.BEST_QUALITY):
            scored: list[tuple[VoteScore, str, str, str, float]] = []
            for provider, model, content, latency in valid_responses:
                score = self._voting.score_response(content, latency, provider, model)
                scored.append((score, provider, model, content, latency))

            if strategy_enum == ConsensusStrategy.HIGHEST_CONFIDENCE:
                best = max(scored, key=lambda s: s[0].quality)
            elif strategy_enum == ConsensusStrategy.BEST_QUALITY:
                best = max(scored, key=lambda s: s[0].quality)
            else:
                best = max(scored, key=lambda s: s[0].overall)

            score, provider, model, content, latency = best
            return ConsensusResult(
                provider=provider,
                model=model,
                content=content,
                strategy=strategy,
                scores={
                    "quality": score.quality,
                    "cost": score.cost,
                    "latency": score.latency,
                    "reliability": score.reliability,
                    "overall": score.overall,
                },
                votes=1,
                total_votes=len(providers),
            )

        votes_dict: dict[str, list[tuple[str, str, str]]] = {}
        for provider, model, content, latency in valid_responses:
            simplified = content[:100].lower()
            votes_dict.setdefault(simplified, []).append((provider, model, content))
        winner = max(votes_dict.values(), key=len)
        winner_provider, winner_model, winner_content = winner[0]
        return ConsensusResult(
            provider=winner_provider,
            model=winner_model,
            content=winner_content,
            strategy=strategy,
            votes=len(winner),
            total_votes=len(valid_responses),
        )
