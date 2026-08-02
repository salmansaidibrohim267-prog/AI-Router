from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkPreview:
    content: str
    chunk_index: int
    start_offset: int
    end_offset: int
    token_estimate: int
    character_count: int
    metadata: dict[str, Any] = field(default_factory=dict)
    section: list[str] = field(default_factory=list)
    page_number: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "chunk_index": self.chunk_index,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "token_estimate": self.token_estimate,
            "character_count": self.character_count,
            "metadata": self.metadata,
            "section": self.section,
            "page_number": self.page_number,
        }


@dataclass
class ChunkingResult:
    document_id: str
    collection_id: str
    total_chunks: int
    chunks: list[Any]
    previews: list[ChunkPreview] | None = None
    statistics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "collection_id": self.collection_id,
            "total_chunks": self.total_chunks,
            "statistics": self.statistics,
            "chunks": [c.to_dict() for c in self.chunks] if not self.previews else [],
            "previews": [p.to_dict() for p in (self.previews or [])],
        }
