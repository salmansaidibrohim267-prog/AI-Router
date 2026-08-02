from __future__ import annotations

import re
from typing import Any, Callable

from app.memory.exceptions import MemoryExtractionError
from app.memory.models import ExtractedMemory, MemoryCategory


class MemoryExtractor:
    def __init__(self, extraction_func: Callable | None = None):
        self._extraction_func = extraction_func

    def extract(self, text: str) -> list[ExtractedMemory]:
        if not text or not text.strip():
            return []
        try:
            if self._extraction_func is not None:
                raw = self._extraction_func(text)
                if isinstance(raw, list):
                    return [self._normalize(item) for item in raw]
                return [ExtractedMemory(content=str(raw))]
            return self._extract_by_patterns(text)
        except MemoryExtractionError:
            raise
        except Exception as e:
            raise MemoryExtractionError(f"Memory extraction failed: {e}") from e

    def _normalize(self, item: Any) -> ExtractedMemory:
        if isinstance(item, ExtractedMemory):
            return item
        if isinstance(item, dict):
            return ExtractedMemory(
                content=str(item.get("content", "")),
                category=MemoryCategory(item.get("category", "general")),
                confidence=float(item.get("confidence", 0.5)),
                importance=float(item.get("importance", 0.5)),
                metadata=item.get("metadata", {}),
            )
        return ExtractedMemory(content=str(item))

    def _extract_by_patterns(self, text: str) -> list[ExtractedMemory]:
        memories: list[ExtractedMemory] = []
        for pattern, category in self.PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                content = self._clean(match.group(0))
                if not content:
                    continue
                memories.append(
                    ExtractedMemory(
                        content=content,
                        category=category,
                        confidence=self._confidence_for(category),
                        importance=self._importance_for(category),
                    )
                )
        for entity in self._extract_entities(text):
            memories.append(
                ExtractedMemory(
                    content=f"Entity: {entity}",
                    category=MemoryCategory.ENTITY,
                    confidence=0.4,
                    importance=0.3,
                    metadata={"entity": entity},
                )
            )
        return memories

    PATTERNS: list[tuple[str, MemoryCategory]] = [
        (r"(?:I like|I prefer|I love|I hate|I enjoy|I don'?t like|my favorite|my favourite|I am fond of)[^.!?\n]*", MemoryCategory.PREFERENCE),
        (r"(?:I want to|I would like to|I hope to|I aim to|my goal is|I am working towards|I plan to|I wish to)[^.!?\n]*", MemoryCategory.GOAL),
        (r"(?:I am|I'?m|she is|he is|it is|we are|they are|my name is|the fact is|it costs|it takes|it has)[^.!?\n]*", MemoryCategory.FACT),
        (r"(?:I decided|I have decided|I choose|I chose|I will go with|we decided|decision:|I picked)[^.!?\n]*", MemoryCategory.DECISION),
        (r"(?:I can'?t|I cannot|I must|I have to|I need to avoid|I am not allowed|I don'?t want to|constraint:|I am unable to)[^.!?\n]*", MemoryCategory.CONSTRAINT),
        (r"(?:I need to|I have to remember|remind me|my task is|I should|I will do|todo:|I must remember)[^.!?\n]*", MemoryCategory.TASK),
        (r"(?:remember that|note that|important:|for future reference)[^.!?\n]*", MemoryCategory.GENERAL),
    ]

    def _extract_entities(self, text: str) -> list[str]:
        candidates = re.findall(r"\b[A-Z][a-z]+\b", text)
        stopwords = {"I", "The", "A", "An", "And", "Or", "But", "For", "With", "From", "To", "My", "It", "She", "He", "They", "We", "You", "This", "That", "Today", "Tomorrow", "Yes", "No", "Now", "Also", "One", "Two", "First", "Last"}
        return list(dict.fromkeys(c for c in candidates if c not in stopwords))

    def _clean(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.strip()).strip(" ,.!?;:")

    def _confidence_for(self, category: MemoryCategory) -> float:
        return {
            MemoryCategory.PREFERENCE: 0.7,
            MemoryCategory.GOAL: 0.75,
            MemoryCategory.FACT: 0.6,
            MemoryCategory.DECISION: 0.8,
            MemoryCategory.CONSTRAINT: 0.8,
            MemoryCategory.TASK: 0.75,
            MemoryCategory.GENERAL: 0.5,
        }.get(category, 0.5)

    def _importance_for(self, category: MemoryCategory) -> float:
        return {
            MemoryCategory.PREFERENCE: 0.7,
            MemoryCategory.GOAL: 0.9,
            MemoryCategory.FACT: 0.5,
            MemoryCategory.DECISION: 0.8,
            MemoryCategory.CONSTRAINT: 0.9,
            MemoryCategory.TASK: 0.7,
            MemoryCategory.GENERAL: 0.4,
        }.get(category, 0.5)
