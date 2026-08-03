from __future__ import annotations

from app.knowledge.chunking.models import ChunkPreview


class ChunkValidationError(ValueError):
    pass


class ChunkValidator:
    def __init__(self, min_chunk_size: int = 100, max_chunk_size: int = 2000):
        self._min = min_chunk_size
        self._max = max_chunk_size

    def validate(self, chunk: ChunkPreview) -> ChunkPreview:
        if not chunk.content or not chunk.content.strip():
            raise ChunkValidationError("Empty chunk content")
        if chunk.character_count < self._min:
            raise ChunkValidationError(f"Chunk too small: {chunk.character_count} chars (min {self._min})")
        if chunk.character_count > self._max:
            raise ChunkValidationError(f"Chunk too large: {chunk.character_count} chars (max {self._max})")
        if chunk.end_offset <= chunk.start_offset:
            raise ChunkValidationError("Invalid chunk offsets")
        if chunk.token_estimate < 1:
            raise ChunkValidationError("Invalid token estimate")
        return chunk
