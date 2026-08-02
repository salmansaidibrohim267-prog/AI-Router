from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DistanceMetric(str, Enum):
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    DOT_PRODUCT = "dot_product"


@dataclass
class VectorCollection:
    name: str
    dimensions: int
    distance: DistanceMetric = DistanceMetric.COSINE
    namespace: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)
    vector_count: int = 0
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dimensions": self.dimensions,
            "distance": self.distance.value,
            "namespace": self.namespace,
            "metadata": self.metadata,
            "vector_count": self.vector_count,
            "created_at": self.created_at,
        }


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "vector": self.vector,
            "metadata": self.metadata,
            "namespace": self.namespace,
            "score": self.score,
        }


@dataclass
class SearchResult:
    id: str
    score: float
    vector: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"

    def to_dict(self, include_vector: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "score": self.score,
            "metadata": self.metadata,
            "namespace": self.namespace,
        }
        if include_vector:
            d["vector"] = self.vector
        return d


@dataclass
class UpsertRequest:
    id: str = ""
    vector: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"


@dataclass
class SearchRequest:
    vector: list[float] = field(default_factory=list)
    top_k: int = 10
    score_threshold: float | None = None
    collection: str = ""
    namespace: str = "default"
    filter: dict[str, Any] = field(default_factory=dict)
    include_metadata: bool = True
    include_vector: bool = False


@dataclass
class DeleteRequest:
    ids: list[str] = field(default_factory=list)
    filter: dict[str, Any] = field(default_factory=dict)
    collection: str = ""
    namespace: str = "default"


@dataclass
class VectorStoreStats:
    total_collections: int = 0
    total_vectors: int = 0
    storage_usage: int = 0
    average_search_latency: float = 0.0
    provider: str = ""
    dimensions: int = 0
    batch_throughput: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_collections": self.total_collections,
            "total_vectors": self.total_vectors,
            "storage_usage": self.storage_usage,
            "average_search_latency": self.average_search_latency,
            "provider": self.provider,
            "dimensions": self.dimensions,
            "batch_throughput": self.batch_throughput,
        }
