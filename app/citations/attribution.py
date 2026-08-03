from __future__ import annotations

import inspect
import re
from typing import Any, Callable, Protocol

from app.citations.exceptions import CitationAttributionError
from app.citations.models import CitationMapping, CitationSource

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class SentenceSplitter:
    def split(self, text: str, max_chars: int = 400) -> list[tuple[str, int, int]]:
        if not text or not text.strip():
            return []
        parts = _SENTENCE_RE.split(text.strip())
        sentences: list[tuple[str, int, int]] = []
        offset = 0
        for part in parts:
            part = part.strip()
            if not part:  # pragma: no cover - defensive guard, unreachable by regex
                continue
            start = offset
            end = start + len(part)
            if len(part) > max_chars:
                for i in range(0, len(part), max_chars):
                    piece = part[i : i + max_chars]
                    sentences.append((piece, start + i, start + i + len(piece)))
            else:
                sentences.append((part, start, end))
            offset = end + 1
        return sentences


class AttributionStrategy(Protocol):
    name: str

    def score(self, sentence: str, source: CitationSource) -> float:  # pragma: no cover - protocol stub
        ...

    async def score_async(self, sentence: str, source: CitationSource) -> float:  # pragma: no cover - protocol stub
        ...


class TokenOverlapAttributionStrategy:
    name = "token_overlap"

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9']+", text.lower()))

    def score(self, sentence: str, source: CitationSource) -> float:
        st = self._tokens(sentence)
        ct = self._tokens(source.content)
        if not st or not ct:
            return 0.0
        return len(st & ct) / len(st)

    async def score_async(self, sentence: str, source: CitationSource) -> float:
        return self.score(sentence, source)


class EmbeddingAttributionStrategy:
    name = "embedding"

    def __init__(self, embedder: Callable[[str], Any]):
        self._embedder = embedder
        self._embedder_is_async = inspect.iscoroutinefunction(embedder)

    def _vector(self, result: Any) -> list[float]:
        if isinstance(result, list):
            return result
        if hasattr(result, "vector"):
            return result.vector
        raise CitationAttributionError("Embedder must return a vector or an object with .vector")

    def _cosine(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)

    def score(self, sentence: str, source: CitationSource) -> float:
        if self._embedder_is_async:
            raise CitationAttributionError("Async embedder requires generate_async; use async scoring")
        s_vec = self._vector(self._embedder(sentence))
        c_vec = self._vector(self._embedder(source.content))
        return self._cosine(s_vec, c_vec)

    async def score_async(self, sentence: str, source: CitationSource) -> float:
        if not self._embedder_is_async:
            return self.score(sentence, source)
        s_vec = self._vector(await self._embedder(sentence))
        c_vec = self._vector(await self._embedder(source.content))
        return self._cosine(s_vec, c_vec)


class SentenceAttributionMapper:
    def __init__(
        self,
        strategy: AttributionStrategy,
        threshold: float = 0.25,
        max_sources_per_sentence: int = 3,
        max_chars: int = 400,
    ):
        self._strategy = strategy
        self._threshold = threshold
        self._max_sources = max_sources_per_sentence
        self._max_chars = max_chars
        self._splitter = SentenceSplitter()

    @property
    def strategy(self) -> AttributionStrategy:
        return self._strategy

    def map(
        self,
        text: str,
        sources: list[CitationSource],
    ) -> list[CitationMapping]:
        mappings: list[CitationMapping] = []
        for sentence, start, end in self._splitter.split(text, self._max_chars):
            scored: list[tuple[str, float]] = []
            for source in sources:
                try:
                    score = self._strategy.score(sentence, source)
                except Exception:
                    score = 0.0
                if score >= self._threshold:
                    scored.append((source.source_id, score))
            scored.sort(key=lambda item: item[1], reverse=True)
            scored = scored[: self._max_sources]
            best = scored[0][1] if scored else 0.0
            mappings.append(
                CitationMapping(
                    sentence=sentence,
                    source_ids=[sid for sid, _ in scored],
                    scores={sid: s for sid, s in scored},
                    start=start,
                    end=end,
                    attribution_score=best,
                )
            )
        return mappings

    async def map_async(
        self,
        text: str,
        sources: list[CitationSource],
    ) -> list[CitationMapping]:
        mappings: list[CitationMapping] = []
        for sentence, start, end in self._splitter.split(text, self._max_chars):
            scored: list[tuple[str, float]] = []
            for source in sources:
                try:
                    score = await self._strategy.score_async(sentence, source)
                except Exception:
                    score = 0.0
                if score >= self._threshold:
                    scored.append((source.source_id, score))
            scored.sort(key=lambda item: item[1], reverse=True)
            scored = scored[: self._max_sources]
            best = scored[0][1] if scored else 0.0
            mappings.append(
                CitationMapping(
                    sentence=sentence,
                    source_ids=[sid for sid, _ in scored],
                    scores={sid: s for sid, s in scored},
                    start=start,
                    end=end,
                    attribution_score=best,
                )
            )
        return mappings
