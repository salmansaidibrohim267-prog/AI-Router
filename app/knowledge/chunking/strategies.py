from __future__ import annotations

import math
import re
from typing import Any, Protocol

from app.knowledge.chunking.models import ChunkPreview
from app.knowledge.chunking.tokenizer import HeuristicTokenEstimator, TokenEstimator
from app.knowledge.models import KnowledgeDocument


class ChunkStrategy(Protocol):
    async def split(
        self,
        document: KnowledgeDocument,
        **kwargs: Any,
    ) -> list[ChunkPreview]:
        ...


_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


class _BaseStrategy:
    def __init__(self, token_estimator: TokenEstimator | None = None):
        self._estimator = token_estimator or HeuristicTokenEstimator()

    def _make_chunk(
        self,
        content: str,
        index: int,
        start_offset: int,
        section: list[str] | None = None,
        page_number: int | None = None,
    ) -> ChunkPreview:
        end_offset = start_offset + len(content)
        return ChunkPreview(
            content=content,
            chunk_index=index,
            start_offset=start_offset,
            end_offset=end_offset,
            token_estimate=self._estimator.estimate(content),
            character_count=len(content),
            section=section or [],
            page_number=page_number,
        )


class FixedSizeChunkStrategy(_BaseStrategy):
    def __init__(
        self,
        max_characters: int = 1000,
        overlap: int = 200,
        token_estimator: TokenEstimator | None = None,
    ):
        super().__init__(token_estimator)
        self._max = max_characters
        self._overlap = overlap

    async def split(
        self,
        document: KnowledgeDocument,
        **kwargs: Any,
    ) -> list[ChunkPreview]:
        text = document.content
        chunks: list[ChunkPreview] = []
        start = 0
        index = 0

        while start < len(text):
            end = start + self._max
            if end >= len(text):
                end = len(text)
            else:
                break_pos = self._find_break(text, start, end)
                if break_pos > start:
                    end = break_pos

            chunk_text = text[start:end]
            chunks.append(self._make_chunk(chunk_text, index, start))
            index += 1

            next_start = end - self._overlap
            if next_start <= start:
                next_start = end
            start = next_start

            if start >= len(text):
                break

        return chunks

    def _find_break(self, text: str, start: int, end: int) -> int:
        segment = text[start:end]
        for pattern in (r"\n\n", r"\n", r". ", r" "):
            matches = list(re.finditer(pattern, segment))
            if matches:
                last = matches[-1]
                candidate = start + last.end()
                if candidate > start:
                    return candidate
        return end


class RecursiveChunkStrategy(_BaseStrategy):
    def __init__(
        self,
        max_characters: int = 1000,
        overlap: int = 200,
        token_estimator: TokenEstimator | None = None,
    ):
        super().__init__(token_estimator)
        self._max = max_characters
        self._overlap = overlap

    async def split(
        self,
        document: KnowledgeDocument,
        **kwargs: Any,
    ) -> list[ChunkPreview]:
        text = document.content
        return self._split_recursive(text, 0)

    def _split_recursive(
        self,
        text: str,
        base_index: int,
        section: list[str] | None = None,
        level_hint: str | None = None,
    ) -> list[ChunkPreview]:
        if len(text) <= self._max:
            return [self._make_chunk(text, base_index, 0, section)]

        level = self._detect_level(text, level_hint)
        if level == "heading":
            parts = self._split_by_heading(text)
            return self._process_parts(parts, base_index, section, level)
        elif level == "paragraph":
            parts = self._split_by_paragraph(text)
            return self._process_parts(parts, base_index, section, level)
        elif level == "sentence":
            parts = self._split_by_sentence(text)
            return self._process_parts(parts, base_index, section, level)
        else:
            parts = self._split_by_word(text)
            return self._process_parts(parts, base_index, section, level)

    def _detect_level(self, text: str, current_level: str | None = None) -> str:
        if current_level != "heading":
            has_headings = bool(re.search(r"^#{1,6}\s", text, re.MULTILINE))
            if has_headings:
                parts, _ = self._split_heading_boundaries(text)
                if len(parts) > 1:
                    return "heading"
        paras = [p for p in text.split("\n\n") if p.strip()]
        if len(paras) > 1 and any(len(p) > self._max for p in paras):
            return "paragraph"
        sentences = _SENTENCE_PATTERN.split(text)
        if len(sentences) > 1 and any(len(s) > self._max for s in sentences):
            return "sentence"
        return "word"

    def _split_heading_boundaries(self, text: str) -> tuple[list[str], list[str]]:
        parts = re.split(r"(?=^#{1,6}\s)", text, flags=re.MULTILINE)
        parts = [p.strip() for p in parts if p.strip()]
        headings = []
        for p in parts:
            m = re.match(r"^(#{1,6}\s+.+)$", p, re.MULTILINE)
            if m:
                headings.append(m.group(1))
        return parts, headings

    def _split_by_heading(self, text: str) -> list[str]:
        parts, _ = self._split_heading_boundaries(text)
        return parts

    def _split_by_paragraph(self, text: str) -> list[str]:
        parts = re.split(r"\n\s*\n", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_by_sentence(self, text: str) -> list[str]:
        parts = _SENTENCE_PATTERN.split(text)
        return [p.strip() for p in parts if p.strip()]

    def _split_by_word(self, text: str) -> list[str]:
        parts: list[str] = []
        while len(text) > self._max:
            chunk = text[:self._max]
            space = chunk.rfind(" ")
            if space > len(chunk) // 2:
                chunk = chunk[:space]
            parts.append(chunk.strip())
            text = text[len(chunk):].strip()
        if text:
            parts.append(text.strip())
        return parts

    def _process_parts(
        self,
        parts: list[str],
        base_index: int,
        section: list[str] | None = None,
        level: str | None = None,
    ) -> list[ChunkPreview]:
        chunks: list[ChunkPreview] = []
        current_heading = list(section or [])
        index = base_index
        for part in parts:
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", part, re.MULTILINE)
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()
                current_heading = current_heading[:level - 1] + [heading_text]
                content = part
            else:
                content = part

            if len(content) <= self._max:
                chunks.append(self._make_chunk(content, index, 0, current_heading.copy()))
                index += 1
            else:
                next_hint = "paragraph" if level == "heading" else level
                sub_chunks = self._split_recursive(
                    content, index, current_heading.copy(), level_hint=next_hint
                )
                chunks.extend(sub_chunks)
                index += len(sub_chunks)
        return chunks


class ParagraphChunkStrategy(_BaseStrategy):
    def __init__(
        self,
        max_characters: int = 1000,
        overlap: int = 0,
        token_estimator: TokenEstimator | None = None,
    ):
        super().__init__(token_estimator)
        self._max = max_characters
        self._overlap = overlap

    async def split(
        self,
        document: KnowledgeDocument,
        **kwargs: Any,
    ) -> list[ChunkPreview]:
        text = document.content
        paragraphs = re.split(r"\n\s*\n", text)
        chunks: list[ChunkPreview] = []
        index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(para) <= self._max:
                chunks.append(self._make_chunk(para, index, 0))
                index += 1
            else:
                sub = FixedSizeChunkStrategy(
                    max_characters=self._max,
                    overlap=self._overlap,
                    token_estimator=self._estimator,
                )
                sub_doc = KnowledgeDocument(content=para)
                sub_chunks = await sub.split(sub_doc)
                for sc in sub_chunks:
                    sc.chunk_index = index
                    chunks.append(sc)
                    index += 1
        return chunks


class SentenceChunkStrategy(_BaseStrategy):
    def __init__(
        self,
        sentences_per_chunk: int = 5,
        overlap_sentences: int = 1,
        token_estimator: TokenEstimator | None = None,
    ):
        super().__init__(token_estimator)
        self._sentences = sentences_per_chunk
        self._overlap = overlap_sentences

    async def split(
        self,
        document: KnowledgeDocument,
        **kwargs: Any,
    ) -> list[ChunkPreview]:
        text = document.content
        sentences = _SENTENCE_PATTERN.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]
        chunks: list[ChunkPreview] = []
        index = 0
        stride = self._sentences - self._overlap
        if stride < 1:
            stride = 1

        i = 0
        while i < len(sentences):
            group = sentences[i:i + self._sentences]
            content = " ".join(group)
            chunks.append(self._make_chunk(content, index, 0))
            index += 1
            i += stride
        return chunks


class SlidingWindowChunkStrategy(_BaseStrategy):
    def __init__(
        self,
        window_size: int = 1000,
        stride: int = 500,
        token_estimator: TokenEstimator | None = None,
    ):
        super().__init__(token_estimator)
        self._window = window_size
        self._stride = stride

    async def split(
        self,
        document: KnowledgeDocument,
        **kwargs: Any,
    ) -> list[ChunkPreview]:
        text = document.content
        chunks: list[ChunkPreview] = []
        index = 0
        start = 0

        while start < len(text):
            end = min(start + self._window, len(text))
            chunk_text = text[start:end]
            chunks.append(self._make_chunk(chunk_text, index, start))
            index += 1
            start += self._stride

        return chunks


_STRATEGY_MAP: dict[str, type[ChunkStrategy]] = {
    "fixed": FixedSizeChunkStrategy,
    "recursive": RecursiveChunkStrategy,
    "paragraph": ParagraphChunkStrategy,
    "sentence": SentenceChunkStrategy,
    "sliding_window": SlidingWindowChunkStrategy,
}


def create_strategy(
    name: str,
    chunk_size: int = 1000,
    overlap: int = 200,
    token_estimator: TokenEstimator | None = None,
) -> ChunkStrategy:
    cls = _STRATEGY_MAP.get(name)
    if not cls:
        raise ValueError(f"Unknown chunk strategy: {name}")

    kwargs: dict[str, Any] = {}
    if name == "sentence":
        kwargs["sentences_per_chunk"] = max(1, chunk_size // 200)
        kwargs["overlap_sentences"] = max(1, overlap // 200)
    elif name == "sliding_window":
        kwargs["window_size"] = chunk_size
        kwargs["stride"] = chunk_size - overlap if chunk_size > overlap else chunk_size // 2
    else:
        kwargs["max_characters"] = chunk_size
        kwargs["overlap"] = overlap

    kwargs["token_estimator"] = token_estimator
    return cls(**kwargs)
