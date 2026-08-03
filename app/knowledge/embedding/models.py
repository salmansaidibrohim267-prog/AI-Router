from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmbeddingResult:
    vector: list[float]
    model: str
    provider: str
    dimensions: int
    token_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "vector": self.vector,
            "model": self.model,
            "provider": self.provider,
            "dimensions": self.dimensions,
            "token_count": self.token_count,
        }


@dataclass
class EmbeddingRecord:
    id: str = ""
    document_id: str = ""
    chunk_id: str = ""
    model: str = ""
    provider: str = ""
    dimensions: int = 0
    vector: list[float] = field(default_factory=list)
    token_count: int = 0
    metadata: list[Any] = field(default_factory=list)
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "model": self.model,
            "provider": self.provider,
            "dimensions": self.dimensions,
            "vector": self.vector,
            "token_count": self.token_count,
            "metadata": [m.to_dict() if hasattr(m, "to_dict") else m for m in self.metadata],
            "created_at": self.created_at,
        }
