from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KnowledgeStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass
class KnowledgeMetadata:
    key: str
    value: str
    value_type: str = "string"

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "value": self.value, "value_type": self.value_type}

    @staticmethod
    def from_dict(data: dict[str, str]) -> KnowledgeMetadata:
        return KnowledgeMetadata(
            key=data["key"],
            value=data["value"],
            value_type=data.get("value_type", "string"),
        )


@dataclass
class KnowledgeCollection:
    id: str = ""
    name: str = ""
    description: str = ""
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE
    metadata: list[KnowledgeMetadata] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: int = 1
    document_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "metadata": [m.to_dict() for m in self.metadata],
            "tags": self.tags,
            "version": self.version,
            "document_count": self.document_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> KnowledgeCollection:
        return KnowledgeCollection(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            status=KnowledgeStatus(data.get("status", "active")),
            metadata=[KnowledgeMetadata.from_dict(m) for m in data.get("metadata", [])],
            tags=data.get("tags", []),
            version=data.get("version", 1),
            document_count=data.get("document_count", 0),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )


@dataclass
class KnowledgeDocument:
    id: str = ""
    collection_id: str = ""
    title: str = ""
    content: str = ""
    source: str = ""
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE
    metadata: list[KnowledgeMetadata] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: int = 1
    chunk_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "collection_id": self.collection_id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "status": self.status.value,
            "metadata": [m.to_dict() for m in self.metadata],
            "tags": self.tags,
            "version": self.version,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=data.get("id", ""),
            collection_id=data.get("collection_id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            source=data.get("source", ""),
            status=KnowledgeStatus(data.get("status", "active")),
            metadata=[KnowledgeMetadata.from_dict(m) for m in data.get("metadata", [])],
            tags=data.get("tags", []),
            version=data.get("version", 1),
            chunk_count=data.get("chunk_count", 0),
            created_at=data.get("created_at", 0.0),
            updated_at=data.get("updated_at", 0.0),
        )


@dataclass
class KnowledgeChunk:
    id: str = ""
    document_id: str = ""
    collection_id: str = ""
    content: str = ""
    chunk_index: int = 0
    start_offset: int = 0
    end_offset: int = 0
    token_estimate: int = 0
    character_count: int = 0
    metadata: list[KnowledgeMetadata] = field(default_factory=list)
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "collection_id": self.collection_id,
            "content": self.content,
            "chunk_index": self.chunk_index,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "token_estimate": self.token_estimate,
            "character_count": self.character_count,
            "metadata": [m.to_dict() for m in self.metadata],
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> KnowledgeChunk:
        return KnowledgeChunk(
            id=data.get("id", ""),
            document_id=data.get("document_id", ""),
            collection_id=data.get("collection_id", ""),
            content=data.get("content", ""),
            chunk_index=data.get("chunk_index", 0),
            start_offset=data.get("start_offset", 0),
            end_offset=data.get("end_offset", 0),
            token_estimate=data.get("token_estimate", 0),
            character_count=data.get("character_count", 0),
            metadata=[KnowledgeMetadata.from_dict(m) for m in data.get("metadata", [])],
            created_at=data.get("created_at", 0.0),
        )
