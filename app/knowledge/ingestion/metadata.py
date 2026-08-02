from __future__ import annotations

import hashlib
import os
import time
from typing import Any

from app.knowledge.ingestion.models import LoadedDocument

try:
    import charset_normalizer

    HAS_CHARSET = True
except ImportError:
    HAS_CHARSET = False


class MetadataExtractor:
    async def extract(self, document: LoadedDocument, **kwargs) -> dict[str, Any]:
        meta: dict[str, Any] = {}

        meta["filename"] = document.filename
        meta["extension"] = document.extension
        meta["mime_type"] = document.mime_type
        meta["size"] = document.size
        meta["checksum"] = hashlib.sha256(document.content).hexdigest()
        meta["encoding"] = self._detect_encoding(document.content, document.encoding)

        stat = kwargs.get("stat")
        if stat:
            st = stat if hasattr(stat, "st_mtime") else None
            if st is None and isinstance(kwargs.get("path"), str):
                try:
                    st = os.stat(kwargs["path"])
                except (OSError, TypeError):
                    st = None
            if st:
                meta["created_at"] = getattr(st, "st_ctime", time.time())
                meta["modified_at"] = getattr(st, "st_mtime", time.time())

        custom = kwargs.get("custom_metadata", {})
        if custom:
            meta["custom"] = custom

        return meta

    def _detect_encoding(self, data: bytes, fallback: str) -> str:
        if HAS_CHARSET:
            try:
                result = charset_normalizer.from_bytes(data[:10000])
                if result.best():
                    return str(result.best().encoding)
            except Exception:
                pass
        return fallback
