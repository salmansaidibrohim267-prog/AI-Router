from __future__ import annotations

from typing import Any

from app.knowledge.chunking.models import ChunkPreview


class ChunkStatistics:
    @staticmethod
    def compute(chunks: list[ChunkPreview]) -> dict[str, Any]:
        if not chunks:
            return {
                "total_chunks": 0,
                "average_size": 0,
                "average_token": 0,
                "max_size": 0,
                "min_size": 0,
                "total_characters": 0,
                "total_tokens": 0,
            }

        sizes = [c.character_count for c in chunks]
        tokens = [c.token_estimate for c in chunks]
        total_chars = sum(sizes)
        total_tokens = sum(tokens)

        return {
            "total_chunks": len(chunks),
            "average_size": round(total_chars / len(chunks), 1),
            "average_token": round(total_tokens / len(chunks), 1),
            "max_size": max(sizes),
            "min_size": min(sizes),
            "total_characters": total_chars,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def overlap_percentage(
        chunks: list[ChunkPreview], document_length: int
    ) -> float:
        if not chunks or document_length == 0:
            return 0.0
        total_content = sum(len(c.content) for c in chunks)
        ratio = total_content / document_length
        return round(max(0.0, (ratio - 1.0) * 100), 2)
