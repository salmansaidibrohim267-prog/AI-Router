from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model: str = "text-embedding-3-small"
    batch_size: int = 16
    timeout: int = 60
    max_retry: int = 3
    cache_enabled: bool = True
    cache_ttl: int = 3600
    dimensions: int = 384

    @classmethod
    def from_env(cls) -> EmbeddingConfig:
        return cls(
            provider=os.getenv("EMBEDDING_PROVIDER", "local"),
            model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "16")),
            timeout=int(os.getenv("EMBEDDING_TIMEOUT", "60")),
            max_retry=int(os.getenv("EMBEDDING_MAX_RETRY", "3")),
            cache_enabled=os.getenv("EMBEDDING_CACHE_ENABLED", "1") == "1",
            cache_ttl=int(os.getenv("EMBEDDING_CACHE_TTL", "3600")),
        )
