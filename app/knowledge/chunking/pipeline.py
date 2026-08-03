from __future__ import annotations

import json
import time
from typing import Any

from app.knowledge.chunking.config import ChunkingConfig
from app.knowledge.chunking.metadata import ChunkMetadataBuilder
from app.knowledge.chunking.models import ChunkingResult, ChunkPreview
from app.knowledge.chunking.statistics import ChunkStatistics
from app.knowledge.chunking.strategies import ChunkStrategy, create_strategy
from app.knowledge.chunking.tokenizer import HeuristicTokenEstimator, TokenEstimator
from app.knowledge.chunking.validator import ChunkValidationError, ChunkValidator
from app.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeMetadata
from app.knowledge.service import KnowledgeService


class ChunkingPipeline:
    def __init__(
        self,
        knowledge_service: KnowledgeService,
        config: ChunkingConfig | None = None,
        strategy: ChunkStrategy | None = None,
        validator: ChunkValidator | None = None,
        metadata_builder: ChunkMetadataBuilder | None = None,
        token_estimator: TokenEstimator | None = None,
    ):
        self._svc = knowledge_service
        self._config = config or ChunkingConfig.from_env()
        self._estimator = token_estimator or HeuristicTokenEstimator()
        self._strategy = strategy or create_strategy(
            self._config.strategy,
            chunk_size=self._config.chunk_size,
            overlap=self._config.chunk_overlap,
            token_estimator=self._estimator,
        )
        self._validator = validator or ChunkValidator(
            min_chunk_size=self._config.min_chunk_size,
            max_chunk_size=self._config.max_chunk_size,
        )
        self._metadata_builder = metadata_builder or ChunkMetadataBuilder()

    async def chunk_document(
        self,
        document_id: str,
        **kwargs: Any,
    ) -> ChunkingResult:
        doc = await self._svc.get_document(document_id)
        if not doc:
            raise ValueError(f"Document not found: {document_id}")
        return await self.chunk(doc, **kwargs)

    async def chunk(
        self,
        document: KnowledgeDocument,
        strategy: ChunkStrategy | None = None,
        **kwargs: Any,
    ) -> ChunkingResult:
        strat = strategy or self._strategy
        previews = await strat.split(document, **kwargs)

        validated: list[ChunkPreview] = []
        for p in previews:
            try:
                self._validator.validate(p)
                validated.append(p)
            except ChunkValidationError:
                continue

        chunks: list[KnowledgeChunk] = []
        now = time.time()

        for i, preview in enumerate(validated):
            section_str = json.dumps(preview.section) if preview.section else "[]"

            meta_dict = await self._metadata_builder.build(
                document=document,
                chunk_index=i,
                content=preview.content,
                section=preview.section,
                page_number=preview.page_number,
            )
            meta_objects = [KnowledgeMetadata(key=k, value=str(v)) for k, v in meta_dict.items()]
            meta_objects.insert(
                0,
                KnowledgeMetadata(
                    key="section",
                    value=section_str,
                ),
            )
            if preview.page_number is not None:
                meta_objects.insert(
                    0,
                    KnowledgeMetadata(
                        key="page_number",
                        value=str(preview.page_number),
                    ),
                )

            chunk = KnowledgeChunk(
                document_id=document.id,
                collection_id=document.collection_id,
                content=preview.content,
                chunk_index=i,
                start_offset=preview.start_offset,
                end_offset=preview.end_offset,
                token_estimate=preview.token_estimate,
                character_count=preview.character_count,
                metadata=meta_objects,
                created_at=now,
            )
            chunks.append(chunk)

        stats = ChunkStatistics.compute(validated)
        stats["overlap_percentage"] = ChunkStatistics.overlap_percentage(validated, len(document.content))

        return ChunkingResult(
            document_id=document.id,
            collection_id=document.collection_id,
            total_chunks=len(chunks),
            chunks=chunks,
            statistics=stats,
        )

    async def preview(
        self,
        document: KnowledgeDocument,
        strategy: ChunkStrategy | None = None,
        **kwargs: Any,
    ) -> ChunkingResult:
        strat = strategy or self._strategy
        previews = await strat.split(document, **kwargs)

        stats = ChunkStatistics.compute(previews)
        stats["overlap_percentage"] = ChunkStatistics.overlap_percentage(previews, len(document.content))

        return ChunkingResult(
            document_id=document.id,
            collection_id=document.collection_id,
            total_chunks=len(previews),
            chunks=[],
            previews=previews,
            statistics=stats,
        )

    async def save_chunks(
        self,
        document_id: str,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        saved: list[KnowledgeChunk] = []
        for chunk in chunks:
            saved.append(await self._svc._repo.create_chunk(chunk))
        return saved

    @property
    def config(self) -> ChunkingConfig:
        return self._config
