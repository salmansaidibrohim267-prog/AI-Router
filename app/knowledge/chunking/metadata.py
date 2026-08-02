from __future__ import annotations

from typing import Any

from app.knowledge.models import KnowledgeDocument


class ChunkMetadataBuilder:
    async def build(
        self,
        document: KnowledgeDocument,
        chunk_index: int,
        content: str,
        section: list[str] | None = None,
        page_number: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        doc_meta = {m.key: m.value for m in document.metadata}

        if "language" in doc_meta:
            meta["language"] = doc_meta["language"]
        if document.source:
            meta["source"] = document.source
        if document.tags:
            meta["tags"] = list(document.tags)
        meta["version"] = document.version
        meta["chunk_index"] = chunk_index
        meta["document_title"] = document.title
        meta["document_id"] = document.id

        if section:
            meta["section"] = section
        if page_number is not None:
            meta["page_number"] = page_number

        meta.update(extra)
        return meta
