from __future__ import annotations

import logging
from typing import Any

from app.memory.store import MemoryStore
from app.models import ChatRequest, Message, MessageRole

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    def __init__(self, router: Any, config: dict[str, Any] | None = None):
        self._router = router
        self._config = config or {}
        self._max_tokens = self._config.get("max_summary_tokens", 500)
        self._summary_model = self._config.get("summary_model", "")

    async def summarize(
        self,
        messages: list[dict[str, Any]],
        existing_summary: str = "",
    ) -> str:
        if not messages:
            return existing_summary

        prompt = "Summarize the following conversation concisely.\n\n"
        if existing_summary:
            prompt += f"Previous summary:\n{existing_summary}\n\n"
        prompt += "New messages:\n"
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            prompt += f"{role}: {content}\n"
        prompt += f"\nProvide a concise summary (max {self._max_tokens} tokens)."

        try:
            req = ChatRequest(
                messages=[Message(role=MessageRole.USER, content=prompt)],
                model=self._summary_model or "",
                max_tokens=self._max_tokens,
            )
            response = await self._router.chat(req)
            if response and response.choices:
                return response.choices[0].message.content or existing_summary
        except Exception as e:
            logger.warning(f"Summarization failed: {e}")

        return existing_summary

    async def compress_messages(
        self,
        messages: list[dict[str, Any]],
        target_token_count: int,
        store: MemoryStore | None = None,
        session_id: str = "",
    ) -> list[dict[str, Any]]:
        if len(messages) <= 1:
            return messages

        summary = ""
        if store and session_id:
            summary_key = f"summary:{session_id}"
            existing = store.get(summary_key)
            if existing:
                summary = existing.get("text", "")

        recent = messages[-4:] if len(messages) > 4 else messages
        older = messages[:-4] if len(messages) > 4 else []

        if older:
            new_summary = await self.summarize(older, summary)
            if new_summary and store and session_id:
                store.set(
                    f"summary:{session_id}",
                    {"text": new_summary, "compressed_at": __import__("time").time()},
                )
            if new_summary:
                summary_msg = {
                    "role": "system",
                    "content": f"Conversation summary: {new_summary}",
                }
                return [summary_msg] + recent

        return messages

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return len(text) // 4
