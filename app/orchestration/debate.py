from __future__ import annotations

import asyncio
import time
from typing import Any

from app.orchestration.models import DebateResult
from app.orchestration.metrics import debate_count_total
from app.router import AIRouter
from app.models import ChatRequest, Message, MessageRole


class DebateEngine:
    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._reviewer_model = self._config.get("reviewer_model", "")

    @staticmethod
    def _parse_review(text: str) -> tuple[str, str]:
        import json
        import re
        stripped = text.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if match:
            stripped = match.group(1).strip()
        try:
            data = json.loads(stripped)
            winner = data.get("winner", "A")
            reason = data.get("reason", "")
            return winner, reason
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            fixed = stripped.replace("'", '"')
            fixed = re.sub(r"(?<!\\)\\(?![/\\\"btnfru'])", "\\\\", fixed)
            data = json.loads(fixed)
            winner = data.get("winner", "A")
            reason = data.get("reason", "")
            return winner, reason
        except (json.JSONDecodeError, ValueError):
            pass
        match = re.search(r'"winner"\s*:\s*"([AB])"', stripped)
        if match:
            return match.group(1), stripped
        match = re.search(r'"winner"\s*:\s*"([^"]+)"', stripped)
        if match:
            return match.group(1), stripped
        if "winner" in stripped.lower():
            match = re.search(r'winner[^:]*:\s*"?([AB])"?', stripped, re.IGNORECASE)
            if match:
                return match.group(1).upper(), stripped
        if "A" in stripped.upper() and "B" in stripped.upper():
            return "A", stripped
        return "A", stripped

    async def run_debate(
        self,
        request: ChatRequest,
        provider_a: str,
        provider_b: str,
        router: AIRouter,
    ) -> DebateResult:
        debate_count_total.inc()

        debate_start = time.perf_counter()

        async def get_argument(provider: str) -> tuple[str, str, str] | None:
            try:
                req = request.model_copy()
                req.metadata = req.metadata or {}
                req.metadata["preferred_provider"] = provider
                start = time.perf_counter()
                response = await router.chat(req)
                content = response.choices[0].message.content if response.choices else ""
                model = getattr(response, "model", "")
                return provider, model, content
            except Exception:
                return None

        task_a = get_argument(provider_a)
        task_b = get_argument(provider_b)
        results = await asyncio.gather(task_a, task_b, return_exceptions=True)

        arg_a: tuple[str, str, str] = ("", "", "")
        arg_b: tuple[str, str, str] = ("", "", "")

        for i, r in enumerate(results):
            if isinstance(r, tuple) and r[2]:
                if i == 0:
                    arg_a = r
                else:
                    arg_b = r

        if not arg_a[2] and not arg_b[2]:
            return DebateResult(
                provider_a=provider_a,
                provider_b=provider_b,
                argument_a="",
                argument_b="",
                final_content="",
                winner="",
                reviewer_notes="Both providers failed",
            )

        if not arg_a[2]:
            return DebateResult(
                provider_a=provider_a,
                provider_b=provider_b,
                argument_a="",
                argument_b=arg_b[2],
                final_content=arg_b[2],
                winner=provider_b,
                reviewer_notes="Provider A failed, using B",
            )

        if not arg_b[2]:
            return DebateResult(
                provider_a=provider_a,
                provider_b=provider_b,
                argument_a=arg_a[2],
                argument_b="",
                final_content=arg_a[2],
                winner=provider_a,
                reviewer_notes="Provider B failed, using A",
            )

        review_prompt = (
            "You are a judge evaluating two AI responses to the same prompt.\n\n"
            f"Prompt:\n{request.messages[-1].content if request.messages else ''}\n\n"
            f"Response A ({arg_a[0]}):\n{arg_a[2]}\n\n"
            f"Response B ({arg_b[0]}):\n{arg_b[2]}\n\n"
            "Evaluate both responses on:\n"
            "1. Accuracy\n2. Completeness\n3. Clarity\n\n"
            "Return JSON: {\"winner\": \"A\" or \"B\", \"reason\": \"...\"}"
        )

        try:
            review_req = ChatRequest(
                messages=[Message(role=MessageRole.USER, content=review_prompt)],
                model=self._reviewer_model or "",
            )
            review_response = await router.chat(review_req)
            review_text = review_response.choices[0].message.content if review_response.choices else ""
            winner_key, reviewer_notes = self._parse_review(review_text)
        except Exception:
            winner_key = "A"
            reviewer_notes = "Review failed, defaulting to A"

        if winner_key == "B":
            final_content = arg_b[2]
            winner = provider_b
        else:
            final_content = arg_a[2]
            winner = provider_a

        return DebateResult(
            provider_a=provider_a,
            provider_b=provider_b,
            argument_a=arg_a[2],
            argument_b=arg_b[2],
            final_content=final_content,
            winner=winner,
            reviewer_notes=reviewer_notes,
        )
