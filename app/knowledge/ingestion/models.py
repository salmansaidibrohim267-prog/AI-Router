from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IngestionStage(str, Enum):
    LOAD = "load"
    PARSE = "parse"
    CLEAN = "clean"
    METADATA = "metadata"
    LANGUAGE = "language"
    DEDUP = "dedup"
    VALIDATE = "validate"
    STORE = "store"


@dataclass
class LoadedDocument:
    filename: str
    extension: str
    mime_type: str
    content: bytes
    size: int
    encoding: str = "utf-8"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    document_id: str
    collection_id: str
    title: str
    content: str
    source: str
    language: str
    language_confidence: float
    checksum: str
    is_duplicate: bool
    size: int
    mime_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    stages_completed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "collection_id": self.collection_id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "language": self.language,
            "language_confidence": self.language_confidence,
            "checksum": self.checksum,
            "is_duplicate": self.is_duplicate,
            "size": self.size,
            "mime_type": self.mime_type,
            "metadata": self.metadata,
            "stages_completed": self.stages_completed,
        }
