from __future__ import annotations

import time
from typing import Any

from app.orchestration.models import AgentResult, ReflectionScore
from app.orchestration.metrics import reflection_retry_total
from app.router import AIRouter
from app.models import ChatRequest, Message, MessageRole


class ReflectionEngine:
    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._threshold = self._config.get("threshold", 0.7)
        self._max_retries = self._config.get("max_retries", 2)
        self._fallback_providers = self._config.get("fallback_providers", [])

    async def evaluate(
        self,
        result: AgentResult,
        router: AIRouter,
        request: ChatRequest | None = None,
    ) -> ReflectionScore:
        if not result.content:
            return ReflectionScore(
                overall=0.0,
                should_retry=True,
                reason="Empty response",
            )

        eval_prompt = (
            "Evaluate the following response on three criteria (score 0.0 to 1.0):\n"
            "1. correctness: Is the answer factually correct?\n"
            "2. hallucination: Does the answer contain made-up information? (1.0 = no hallucination)\n"
            "3. completeness: Does the answer fully address the question?\n\n"
            f"Response:\n{result.content}\n\n"
            "Return scores in JSON format: {\"correctness\": 0.0, \"hallucination\": 0.0, \"completeness\": 0.0}"
        )

        try:
            eval_req = ChatRequest(
                messages=[Message(role=MessageRole.USER, content=eval_prompt)],
                model=getattr(request, "model", "") if request else "",
            )
            response = await router.chat(eval_req)
            content = response.choices[0].message.content if response.choices else "{}"
            scores = self._parse_scores(content)
        except Exception:
            return ReflectionScore(overall=0.5, should_retry=False, reason="Evaluation failed, defaulting")

        overall = (scores.get("correctness", 0.0) + scores.get("hallucination", 0.0) + scores.get("completeness", 0.0)) / 3.0

        should_retry = overall < self._threshold
        reason = ""
        if should_retry:
            reasons = []
            if scores.get("correctness", 1.0) < self._threshold:
                reasons.append("low correctness")
            if scores.get("hallucination", 1.0) < self._threshold:
                reasons.append("possible hallucination")
            if scores.get("completeness", 1.0) < self._threshold:
                reasons.append("incomplete")
            reason = ", ".join(reasons) if reasons else "below threshold"

        return ReflectionScore(
            correctness=scores.get("correctness", 0.0),
            hallucination=scores.get("hallucination", 0.0),
            completeness=scores.get("completeness", 0.0),
            overall=overall,
            should_retry=should_retry,
            reason=reason,
        )

    async def reflect_and_retry(
        self,
        result: AgentResult,
        router: AIRouter,
        request: ChatRequest | None = None,
        max_retries: int | None = None,
    ) -> tuple[AgentResult, ReflectionScore]:
        max_retries = max_retries or self._max_retries
        current = result
        retries = 0

        while retries <= max_retries:
            score = await self.evaluate(current, router, request)
            if not score.should_retry:
                return current, score
            if retries >= max_retries:
                return current, score
            retries += 1
            reflection_retry_total.inc()
            improvement_prompt = (
                f"The previous response needs improvement: {score.reason}\n"
                f"Previous response:\n{current.content}\n\n"
                "Please provide an improved response addressing the issues above."
            )
            retry_req = ChatRequest(
                messages=[Message(role=MessageRole.USER, content=improvement_prompt)],
                model=getattr(request, "model", "") if request else "",
                metadata={},
            )
            if self._fallback_providers:
                fallback_idx = (retries - 1) % len(self._fallback_providers)
                retry_req.metadata["preferred_provider"] = self._fallback_providers[fallback_idx]
            try:
                response = await router.chat(retry_req)
                content = response.choices[0].message.content if response.choices else ""
                if content:
                    current = AgentResult(
                        agent=current.agent,
                        step=current.step,
                        content=content,
                        provider=getattr(response, "provider", ""),
                        model=getattr(response, "model", ""),
                    )
            except Exception:
                pass

        final_score = await self.evaluate(current, router, request)
        return current, final_score

    def _parse_scores(self, text: str) -> dict[str, float]:
        import json
        import re
        try:
            data = json.loads(text)
            return {
                "correctness": float(data.get("correctness", 0.0)),
                "hallucination": float(data.get("hallucination", 0.0)),
                "completeness": float(data.get("completeness", 0.0)),
            }
        except (json.JSONDecodeError, ValueError, TypeError):
            match = re.search(r'"correctness"\s*:\s*([\d.]+)', text)
            c = float(match.group(1)) if match else 0.5
            match = re.search(r'"hallucination"\s*:\s*([\d.]+)', text)
            h = float(match.group(1)) if match else 0.5
            match = re.search(r'"completeness"\s*:\s*([\d.]+)', text)
            co = float(match.group(1)) if match else 0.5
            return {"correctness": c, "hallucination": h, "completeness": co}
