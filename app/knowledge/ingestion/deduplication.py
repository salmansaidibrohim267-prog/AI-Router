from __future__ import annotations

import hashlib

from app.knowledge.ingestion.models import LoadedDocument


class DuplicateDetector:
    def __init__(self, existing_checksums: set[str] | None = None):
        self._existing = existing_checksums or set()

    def checksum(self, document: LoadedDocument) -> str:
        return hashlib.sha256(document.content).hexdigest()

    async def is_duplicate(self, document: LoadedDocument, **kwargs) -> bool:
        cs = self.checksum(document)
        return cs in self._existing

    async def check(self, document: LoadedDocument, **kwargs) -> tuple[bool, str]:
        cs = self.checksum(document)
        return (cs in self._existing, cs)

    def add_checksum(self, checksum: str) -> None:
        self._existing.add(checksum)

    def bulk_add(self, checksums: set[str]) -> None:
        self._existing.update(checksums)
