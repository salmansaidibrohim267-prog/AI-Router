from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class ChunkingConfig:
    strategy: str = "fixed"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    min_chunk_size: int = 100
    max_chunk_size: int = 2000
    token_estimator: str = "heuristic"

    @classmethod
    def from_env(cls) -> ChunkingConfig:
        return cls(
            strategy=os.getenv("CHUNK_STRATEGY", "fixed"),
            chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
            min_chunk_size=int(os.getenv("MIN_CHUNK_SIZE", "100")),
            max_chunk_size=int(os.getenv("MAX_CHUNK_SIZE", "2000")),
            token_estimator=os.getenv("TOKEN_ESTIMATOR", "heuristic"),
        )
