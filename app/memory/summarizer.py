from __future__ import annotations

from typing import Any

from app.memory.exceptions import MemorySummarizationError
from app.memory.models import MemoryCategory, MemoryItem


class MemorySummarizer:
    def __init__(self, summarizer_func: Any | None = None):
        self._summarizer_func = summarizer_func

    async def summarize(
        self,
        items: list[MemoryItem],
        style: str = "concise",
    ) -> str:
        if not items:
            return ""
        try:
            if self._summarizer_func is not None:
                if callable(self._summarizer_func):
                    result = self._summarizer_func(items, style=style)
                    if hasattr(result, "__await__"):
                        return str(await result)
                    return str(result)
            if style == "key_points":
                return self._key_points(items)
            if style == "grouped":
                return self._grouped(items)
            return self._concise(items)
        except MemorySummarizationError:
            raise
        except Exception as e:
            raise MemorySummarizationError(f"Memory summarization failed: {e}") from e

    def _concise(self, items: list[MemoryItem]) -> str:
        parts: list[str] = []
        for item in sorted(items, key=lambda i: i.importance, reverse=True)[:10]:
            parts.append(f"- {item.content}")
        return "\n".join(parts)

    def _key_points(self, items: list[MemoryItem]) -> str:
        parts: list[str] = []
        for item in sorted(items, key=lambda i: (i.importance, i.confidence), reverse=True)[:20]:
            parts.append(f"- {item.content}")
        return "Key memories:\n" + "\n".join(parts)

    def _grouped(self, items: list[MemoryItem]) -> str:
        groups: dict[MemoryCategory, list[str]] = {}
        for item in items:
            groups.setdefault(item.category, []).append(item.content)
        lines: list[str] = []
        for category in MemoryCategory:
            if category in groups:
                lines.append(f"{category.value.title()}:\n" + "\n".join(f"- {c}" for c in groups[category]))
        return "\n\n".join(lines)
