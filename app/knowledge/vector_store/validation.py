from __future__ import annotations

from typing import Any

from app.knowledge.vector_store.exceptions import (
    CollectionNotFoundError,
    DuplicateIdError,
    InvalidMetadataError,
    InvalidNamespaceError,
    InvalidScoreError,
    VectorDimensionError,
)
from app.knowledge.vector_store.models import DistanceMetric


class VectorStoreValidator:
    def __init__(self, dimensions: int = 384):
        self._dimensions = dimensions

    def validate_collection_name(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise InvalidNamespaceError("Collection name cannot be empty")
        if not all(c.isalnum() or c in "-_" for c in name):
            raise InvalidNamespaceError(
                "Collection name must be alphanumeric with dashes/underscores"
            )
        return name

    def validate_namespace(self, namespace: str) -> str:
        namespace = namespace.strip()
        if not namespace:
            raise InvalidNamespaceError("Namespace cannot be empty")
        return namespace

    def validate_vector(self, vector: list[float]) -> list[float]:
        if not vector:
            raise InvalidNamespaceError("Vector cannot be empty")
        expected = self._dimensions
        if len(vector) != expected:
            raise VectorDimensionError(expected, len(vector))
        return vector

    def validate_score(self, score: float) -> float:
        if score < 0.0 or score > 1.0:
            raise InvalidScoreError(score)
        return score

    def validate_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        if metadata is None:
            return {}
        if not isinstance(metadata, dict):
            raise InvalidMetadataError("Metadata must be a dict")
        for k, v in metadata.items():
            if not isinstance(k, str) or not k.strip():
                raise InvalidMetadataError("Metadata keys must be non-empty strings")
            if isinstance(v, dict):
                self.validate_metadata(v)
        return metadata

    def check_collection_exists(self, name: str, exists: bool):
        if not exists:
            raise CollectionNotFoundError(name)

    def check_duplicate_ids(self, ids: list[str]) -> list[str]:
        seen: set[str] = set()
        for id in ids:
            if id in seen:
                raise DuplicateIdError(id)
            seen.add(id)
        return list(seen)
