from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorStoreConfig:
    backend: str = "memory"
    collection: str = "knowledge_vectors"
    namespace: str = "default"
    distance: str = "cosine"
    dimensions: int = 384
    batch_size: int = 64
    timeout: int = 30
    max_retry: int = 3

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_prefer_grpc: bool = False

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_auth: str = ""

    pgvector_dsn: str = "postgresql://postgres:postgres@localhost:5432/vectordb"
    pgvector_table: str = "vectors"
    pgvector_pool_size: int = 10

    redis_url: str = "redis://localhost:6379/0"
    redis_index: str = "vectors"
    redis_prefix: str = "vec:"

    @classmethod
    def from_env(cls) -> VectorStoreConfig:
        return cls(
            backend=os.getenv("VECTOR_BACKEND", "memory"),
            collection=os.getenv("VECTOR_COLLECTION", "knowledge_vectors"),
            namespace=os.getenv("VECTOR_NAMESPACE", "default"),
            distance=os.getenv("VECTOR_DISTANCE", "cosine"),
            dimensions=int(os.getenv("VECTOR_DIMENSIONS", "384")),
            batch_size=int(os.getenv("VECTOR_BATCH_SIZE", "64")),
            timeout=int(os.getenv("VECTOR_TIMEOUT", "30")),
            max_retry=int(os.getenv("VECTOR_MAX_RETRY", "3")),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY", ""),
            qdrant_prefer_grpc=os.getenv("QDRANT_PREFER_GRPC", "0") == "1",
            chroma_host=os.getenv("CHROMA_HOST", "localhost"),
            chroma_port=int(os.getenv("CHROMA_PORT", "8000")),
            chroma_auth=os.getenv("CHROMA_AUTH", ""),
            pgvector_dsn=os.getenv("PGVECTOR_DSN", "postgresql://postgres:postgres@localhost:5432/vectordb"),
            pgvector_table=os.getenv("PGVECTOR_TABLE", "vectors"),
            pgvector_pool_size=int(os.getenv("PGVECTOR_POOL_SIZE", "10")),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            redis_index=os.getenv("REDIS_INDEX", "vectors"),
            redis_prefix=os.getenv("REDIS_PREFIX", "vec:"),
        )
