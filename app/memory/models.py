from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class MemoryType(str, Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    SESSION = "session"
    PERSISTENT = "persistent"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class MemoryCategory(str, Enum):
    PREFERENCE = "preference"
    GOAL = "goal"
    FACT = "fact"
    ENTITY = "entity"
    DECISION = "decision"
    CONSTRAINT = "constraint"
    TASK = "task"
    GENERAL = "general"


class MemoryEventType(str, Enum):
    STORE = "store"
    RETRIEVE = "retrieve"
    UPDATE = "update"
    DELETE = "delete"
    ARCHIVE = "archive"
    PRUNE = "prune"
    COMPACT = "compact"


@dataclass
class MemoryScope:
    tenant_id: str = ""
    workspace_id: str = ""
    user_id: str = ""
    session_id: str = ""

    def filter(self) -> dict[str, Any]:
        f: dict[str, Any] = {}
        if self.tenant_id:
            f["tenant_id"] = self.tenant_id
        if self.workspace_id:
            f["workspace_id"] = self.workspace_id
        if self.user_id:
            f["user_id"] = self.user_id
        if self.session_id:
            f["session_id"] = self.session_id
        return f

    def is_isolated(self, item: "MemoryItem") -> bool:
        if self.tenant_id and item.tenant_id != self.tenant_id:
            return False
        if self.workspace_id and item.workspace_id != self.workspace_id:
            return False
        if self.user_id and item.user_id != self.user_id:
            return False
        if self.session_id and item.session_id != self.session_id:
            return False
        return True

    def __bool__(self) -> bool:
        return bool(self.tenant_id or self.workspace_id or self.user_id or self.session_id)


@dataclass
class MemoryItem:
    id: str = ""
    content: str = ""
    memory_type: MemoryType = MemoryType.SHORT_TERM
    category: MemoryCategory = MemoryCategory.GENERAL
    tenant_id: str = ""
    workspace_id: str = ""
    user_id: str = ""
    session_id: str = ""
    importance: float = 0.5
    confidence: float = 0.8
    access_count: int = 0
    created_at: float = 0.0
    last_accessed_at: float = 0.0
    last_updated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    archived: bool = False
    deleted: bool = False

    def __post_init__(self) -> None:
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.last_accessed_at:
            self.last_accessed_at = now
        if not self.last_updated_at:
            self.last_updated_at = now
        if not self.id:
            import uuid
            self.id = uuid.uuid4().hex[:16]

    def touch(self) -> None:
        self.access_count += 1
        self.last_accessed_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "category": self.category.value,
            "tenant_id": self.tenant_id,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "importance": self.importance,
            "confidence": self.confidence,
            "access_count": self.access_count,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "last_updated_at": self.last_updated_at,
            "metadata": self.metadata,
            "archived": self.archived,
            "deleted": self.deleted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryItem":
        item = cls(
            id=data.get("id", ""),
            content=data.get("content", ""),
            memory_type=MemoryType(data.get("memory_type", "short_term")),
            category=MemoryCategory(data.get("category", "general")),
            tenant_id=data.get("tenant_id", ""),
            workspace_id=data.get("workspace_id", ""),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            importance=data.get("importance", 0.5),
            confidence=data.get("confidence", 0.8),
            access_count=data.get("access_count", 0),
            metadata=data.get("metadata", {}),
            embedding=data.get("embedding"),
            archived=data.get("archived", False),
            deleted=data.get("deleted", False),
        )
        item.created_at = data.get("created_at", 0.0) or time.time()
        item.last_accessed_at = data.get("last_accessed_at", 0.0) or time.time()
        item.last_updated_at = data.get("last_updated_at", 0.0) or time.time()
        return item


@dataclass
class ExtractedMemory:
    content: str
    category: MemoryCategory = MemoryCategory.GENERAL
    confidence: float = 0.5
    importance: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "category": self.category.value,
            "confidence": self.confidence,
            "importance": self.importance,
            "metadata": self.metadata,
        }


@dataclass
class MemoryQuery:
    text: str = ""
    scope: MemoryScope = field(default_factory=MemoryScope)
    top_k: int = 10
    memory_types: list[MemoryType] = field(default_factory=list)
    categories: list[MemoryCategory] = field(default_factory=list)
    min_score: float = 0.0


@dataclass
class MemorySearchResult:
    item: MemoryItem
    score: float = 0.0
    similarity: float = 0.0
    recency: float = 0.0
    access: float = 0.0
    importance: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item.to_dict(),
            "score": round(self.score, 4),
            "components": {
                "similarity": round(self.similarity, 4),
                "recency": round(self.recency, 4),
                "access": round(self.access, 4),
                "importance": round(self.importance, 4),
                "confidence": round(self.confidence, 4),
            },
        }


@dataclass
class MemorySummary:
    text: str = ""
    scope: MemoryScope = field(default_factory=MemoryScope)
    entries_count: int = 0
    categories: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "entries_count": self.entries_count,
            "categories": self.categories,
        }


@dataclass
class MemoryMetrics:
    total_ops: int = 0
    total_stores: int = 0
    total_retrieves: int = 0
    total_updates: int = 0
    total_deletes: int = 0
    total_searches: int = 0
    total_extractions: int = 0
    total_summarizations: int = 0
    total_archives: int = 0
    total_prunes: int = 0
    total_compactions: int = 0
    total_latency_ms: float = 0.0
    errors: int = 0
    stored_items: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_ops": self.total_ops,
            "total_stores": self.total_stores,
            "total_retrieves": self.total_retrieves,
            "total_updates": self.total_updates,
            "total_deletes": self.total_deletes,
            "total_searches": self.total_searches,
            "total_extractions": self.total_extractions,
            "total_summarizations": self.total_summarizations,
            "total_archives": self.total_archives,
            "total_prunes": self.total_prunes,
            "total_compactions": self.total_compactions,
            "total_latency_ms": round(self.total_latency_ms, 4),
            "errors": self.errors,
            "stored_items": self.stored_items,
        }
