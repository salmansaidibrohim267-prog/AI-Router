from __future__ import annotations

import logging
from typing import Any

from app.memory.summary import ConversationSummarizer

logger = logging.getLogger(__name__)


class CompressionStats:
    def __init__(self):
        self.total_compressed: int = 0
        self.total_original_tokens: int = 0
        self.total_compressed_tokens: int = 0
        self.compression_count: int = 0

    @property
    def ratio(self) -> float:
        if self.total_original_tokens == 0:
            return 1.0
        return self.total_compressed_tokens / self.total_original_tokens

    def record(self, original: int, compressed: int) -> None:
        self.compression_count += 1
        self.total_original_tokens += original
        self.total_compressed_tokens += compressed

    def to_dict(self) -> dict[str, Any]:
        return {
            "compression_count": self.compression_count,
            "total_original_tokens": self.total_original_tokens,
            "total_compressed_tokens": self.total_compressed_tokens,
            "ratio": round(self.ratio, 4),
        }


class ContextCompressor:
    def __init__(
        self,
        router: Any,
        summarizer: ConversationSummarizer | None = None,
        config: dict[str, Any] | None = None,
    ):
        self._router = router
        self._summarizer = summarizer or ConversationSummarizer(router)
        self._config = config or {}
        self._max_tokens = self._config.get("max_context_tokens", 8000)
        self._compression_ratio = self._config.get("compression_ratio", 0.5)
        self.stats = CompressionStats()

    async def compress(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int = 0,
    ) -> list[dict[str, Any]]:
        if not messages:
            return messages

        token_limit = max_tokens or self._max_tokens
        estimated = self._estimate_tokens(messages)

        if estimated <= token_limit:
            return messages

        original_len = estimated
        logger.info(f"Compressing {estimated} tokens into budget of {token_limit}")

        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        max_non_system = int(token_limit * self._compression_ratio)
        if self._estimate_tokens(non_system) <= max_non_system:
            return messages[-6:] if len(messages) > 6 else messages

        recent = non_system[-4:] if len(non_system) > 4 else non_system
        older = non_system[:-4] if len(non_system) > 4 else []

        summary = ""
        if older:
            summary = await self._summarizer.summarize(older)
            self.stats.record(original_len, self._estimate_tokens(recent + system_msgs))

        compressed = system_msgs.copy()
        if summary:
            compressed.append(
                {
                    "role": "system",
                    "content": f"Previous conversation summary: {summary}",
                }
            )
        compressed.extend(recent)

        if not compressed:
            compressed = messages[-1:]

        logger.info(f"Compressed {estimated} -> {self._estimate_tokens(compressed)} tokens ({self.stats.ratio:.1%})")
        return compressed

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        return ConversationSummarizer.estimate_tokens(" ".join(m.get("content", "") for m in messages))
