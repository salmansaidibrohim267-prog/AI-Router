from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CitationFormat(str, Enum):
    NUMERIC = "numeric"
    IEEE = "ieee"
    APA = "apa"
    MLA = "mla"
    MARKDOWN = "markdown"
    JSON = "json"
    CUSTOM = "custom"


@dataclass
class CitationSource:
    source_id: str
    document_id: str = ""
    chunk_id: str = ""
    filename: str = ""
    title: str = ""
    author: str = ""
    page: str = ""
    section: str = ""
    url: str = ""
    retrieved_at: float | None = None
    published_at: str = ""
    retrieval_score: float = 0.0
    rerank_score: float = 0.0
    attribution_score: float = 0.0
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.retrieved_at is None:
            self.retrieved_at = time.time()
        if not self.source_id and self.chunk_id:
            self.source_id = self.chunk_id

    @property
    def year(self) -> str:
        return self.published_at[:4] if len(self.published_at) >= 4 else ""

    @property
    def author_last(self) -> str:
        parts = [p.strip() for p in self.author.replace(",", " ").split() if p.strip()]
        return parts[-1] if parts else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "filename": self.filename,
            "title": self.title,
            "author": self.author,
            "page": self.page,
            "section": self.section,
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "published_at": self.published_at,
            "retrieval_score": self.retrieval_score,
            "rerank_score": self.rerank_score,
            "attribution_score": self.attribution_score,
            "content": self.content[:200],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CitationSource:
        return cls(
            source_id=str(data.get("source_id", "")),
            document_id=str(data.get("document_id", "")),
            chunk_id=str(data.get("chunk_id", "")),
            filename=str(data.get("filename", "")),
            title=str(data.get("title", "")),
            author=str(data.get("author", "")),
            page=str(data.get("page", "")),
            section=str(data.get("section", "")),
            url=str(data.get("url", "")),
            retrieved_at=data.get("retrieved_at"),
            published_at=str(data.get("published_at", "")),
            retrieval_score=float(data.get("retrieval_score", 0.0)),
            rerank_score=float(data.get("rerank_score", 0.0)),
            attribution_score=float(data.get("attribution_score", 0.0)),
            content=str(data.get("content", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CitationMapping:
    sentence: str
    source_ids: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    start: int = 0
    end: int = 0
    attribution_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentence": self.sentence,
            "source_ids": list(self.source_ids),
            "scores": {k: round(v, 4) for k, v in self.scores.items()},
            "start": self.start,
            "end": self.end,
            "attribution_score": round(self.attribution_score, 4),
        }


@dataclass
class Citation:
    citation_id: str
    sentence: str
    source_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    format: CitationFormat = CitationFormat.NUMERIC
    verified: bool = True
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "citation_id": self.citation_id,
            "sentence": self.sentence,
            "source_ids": list(self.source_ids),
            "confidence": round(self.confidence, 4),
            "format": self.format.value,
            "verified": self.verified,
            "note": self.note,
        }


@dataclass
class CitationResult:
    text: str
    rendered: str = ""
    format: CitationFormat = CitationFormat.NUMERIC
    citations: list[Citation] = field(default_factory=list)
    sources: list[CitationSource] = field(default_factory=list)
    mappings: list[CitationMapping] = field(default_factory=list)
    confidence: float = 0.0
    references: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "rendered": self.rendered,
            "format": self.format.value,
            "citations": [c.to_dict() for c in self.citations],
            "sources": [s.to_dict() for s in self.sources],
            "mappings": [m.to_dict() for m in self.mappings],
            "confidence": round(self.confidence, 4),
            "references": self.references,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


@dataclass
class CitationRequest:
    text: str
    sources: list[Any] = field(default_factory=list)
    query: str = ""
    format: CitationFormat | str = CitationFormat.NUMERIC
    resolve: bool = True
    validate: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    checked_citations: int = 0
    checked_sources: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "confidence": round(self.confidence, 4),
            "checked_citations": self.checked_citations,
            "checked_sources": self.checked_sources,
        }


@dataclass
class CitationMetrics:
    total_generations: int = 0
    total_async_generations: int = 0
    total_batch_items: int = 0
    total_validations: int = 0
    total_resolutions: int = 0
    total_formats: int = 0
    total_citations: int = 0
    total_sources: int = 0
    total_errors: int = 0
    total_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_generations": self.total_generations,
            "total_async_generations": self.total_async_generations,
            "total_batch_items": self.total_batch_items,
            "total_validations": self.total_validations,
            "total_resolutions": self.total_resolutions,
            "total_formats": self.total_formats,
            "total_citations": self.total_citations,
            "total_sources": self.total_sources,
            "total_errors": self.total_errors,
            "total_latency_ms": round(self.total_latency_ms, 4),
        }
