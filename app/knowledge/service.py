from __future__ import annotations

from typing import Any

from app.knowledge.models import (
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeMetadata,
    KnowledgeStatus,
)
from app.knowledge.validation import (
    ValidationError,
    validate_collection_name,
    validate_document_title,
    validate_tags,
)


class KnowledgeService:
    def __init__(self, repository: Any):
        self._repo = repository

    async def create_collection(
        self,
        name: str,
        description: str = "",
        metadata: list[dict[str, str]] | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeCollection:
        name = validate_collection_name(name)
        tags = validate_tags(tags)
        meta_objects = [KnowledgeMetadata.from_dict(m) for m in (metadata or [])]
        collection = KnowledgeCollection(
            name=name,
            description=description,
            metadata=meta_objects,
            tags=tags,
        )
        return await self._repo.create_collection(collection)

    async def get_collection(self, collection_id: str) -> KnowledgeCollection | None:
        return await self._repo.get_collection(collection_id)

    async def update_collection(
        self,
        collection_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        metadata: list[dict[str, str]] | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeCollection | None:
        existing = await self._repo.get_collection(collection_id)
        if not existing:
            return None
        if name is not None:
            existing.name = validate_collection_name(name)
        if description is not None:
            existing.description = description
        if status is not None:
            existing.status = KnowledgeStatus(status)
        if metadata is not None:
            existing.metadata = [KnowledgeMetadata.from_dict(m) for m in metadata]
        if tags is not None:
            existing.tags = validate_tags(tags)
        return await self._repo.update_collection(existing)

    async def delete_collection(self, collection_id: str) -> bool:
        return await self._repo.delete_collection(collection_id)

    async def list_collections(self, skip: int = 0, limit: int = 100) -> list[KnowledgeCollection]:
        return await self._repo.list_collections(skip=skip, limit=limit)

    async def create_document(
        self,
        collection_id: str,
        title: str,
        content: str = "",
        source: str = "",
        metadata: list[dict[str, str]] | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeDocument:
        coll = await self._repo.get_collection(collection_id)
        if not coll:
            raise ValidationError(f"Collection '{collection_id}' not found")
        title = validate_document_title(title)
        tags = validate_tags(tags)
        meta_objects = [KnowledgeMetadata.from_dict(m) for m in (metadata or [])]
        document = KnowledgeDocument(
            collection_id=collection_id,
            title=title,
            content=content,
            source=source,
            metadata=meta_objects,
            tags=tags,
        )
        return await self._repo.create_document(document)

    async def get_document(self, document_id: str) -> KnowledgeDocument | None:
        return await self._repo.get_document(document_id)

    async def update_document(
        self,
        document_id: str,
        title: str | None = None,
        content: str | None = None,
        source: str | None = None,
        status: str | None = None,
        metadata: list[dict[str, str]] | None = None,
        tags: list[str] | None = None,
    ) -> KnowledgeDocument | None:
        existing = await self._repo.get_document(document_id)
        if not existing:
            return None
        if title is not None:
            existing.title = validate_document_title(title)
        if content is not None:
            existing.content = content
        if source is not None:
            existing.source = source
        if status is not None:
            existing.status = KnowledgeStatus(status)
        if metadata is not None:
            existing.metadata = [KnowledgeMetadata.from_dict(m) for m in metadata]
        if tags is not None:
            existing.tags = validate_tags(tags)
        return await self._repo.update_document(existing)

    async def delete_document(self, document_id: str) -> bool:
        return await self._repo.delete_document(document_id)

    async def list_documents(self, collection_id: str = "", skip: int = 0, limit: int = 100) -> list[KnowledgeDocument]:
        return await self._repo.list_documents(
            collection_id=collection_id,
            skip=skip,
            limit=limit,
        )

    async def search_documents(self, query: str, collection_id: str = "", limit: int = 20) -> list[KnowledgeDocument]:
        return await self._repo.search_documents(
            query=query,
            collection_id=collection_id,
            limit=limit,
        )

    async def get_statistics(self, collection_id: str = "") -> dict[str, Any]:
        return await self._repo.get_statistics(collection_id=collection_id)

    async def add_document_tags(self, document_id: str, tags: list[str]) -> KnowledgeDocument | None:
        doc = await self._repo.get_document(document_id)
        if not doc:
            return None
        new_tags = validate_tags(tags)
        existing_set = set(doc.tags)
        for t in new_tags:
            if t not in existing_set:
                doc.tags.append(t)
        return await self._repo.update_document(doc)

    async def remove_document_tags(self, document_id: str, tags: list[str]) -> KnowledgeDocument | None:
        doc = await self._repo.get_document(document_id)
        if not doc:
            return None
        remove_set = set(tags)
        doc.tags = [t for t in doc.tags if t not in remove_set]
        return await self._repo.update_document(doc)

    async def add_collection_tags(self, collection_id: str, tags: list[str]) -> KnowledgeCollection | None:
        coll = await self._repo.get_collection(collection_id)
        if not coll:
            return None
        new_tags = validate_tags(tags)
        existing_set = set(coll.tags)
        for t in new_tags:
            if t not in existing_set:
                coll.tags.append(t)
        return await self._repo.update_collection(coll)

    async def remove_collection_tags(self, collection_id: str, tags: list[str]) -> KnowledgeCollection | None:
        coll = await self._repo.get_collection(collection_id)
        if not coll:
            return None
        remove_set = set(tags)
        coll.tags = [t for t in coll.tags if t not in remove_set]
        return await self._repo.update_collection(coll)

    async def close(self) -> None:
        await self._repo.close()
