from __future__ import annotations

from app.memory.config import MemoryVectorConfig
from app.memory.exceptions import MemoryDuplicateError
from app.memory.models import MemoryItem


class MemoryDeduplicator:
    def __init__(self, config: MemoryVectorConfig | None = None):
        self._config = config or MemoryVectorConfig()

    def find_duplicate(
        self,
        content: str,
        candidates: list[MemoryItem],
    ) -> MemoryItem | None:
        threshold = self._config.dedup_similarity_threshold
        best: tuple[float, MemoryItem] = (0.0, None)  # type: ignore[assignment]
        target = set(content.lower().split())
        if not target:
            return None
        for item in candidates:
            overlap = self._overlap(target, item.content)
            if overlap > best[0]:
                best = (overlap, item)
        if best[0] >= threshold and best[1] is not None:
            return best[1]
        return None

    def _overlap(self, target: set[str], content: str) -> float:
        other = set(content.lower().split())
        if not other:
            return 0.0
        return len(target & other) / min(len(target), len(other))

    def deduplicate(
        self,
        items: list[MemoryItem],
        enforce: bool = False,
    ) -> list[MemoryItem]:
        unique: list[MemoryItem] = []
        for item in items:
            dup = self.find_duplicate(item.content, unique)
            if dup is not None:
                if enforce:
                    raise MemoryDuplicateError(f"Duplicate of existing memory {dup.id}")
                continue
            unique.append(item)
        return unique
