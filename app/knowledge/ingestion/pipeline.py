from __future__ import annotations

import os
from typing import Any

from app.knowledge.ingestion.cleaner import TextCleaner
from app.knowledge.ingestion.config import IngestionConfig
from app.knowledge.ingestion.deduplication import DuplicateDetector
from app.knowledge.ingestion.language import HeuristicLanguageDetector, LanguageDetector
from app.knowledge.ingestion.loaders import DocumentLoader, create_loader
from app.knowledge.ingestion.metadata import MetadataExtractor
from app.knowledge.ingestion.models import IngestionResult, IngestionStage
from app.knowledge.ingestion.parsers import DocumentParser, create_parser
from app.knowledge.ingestion.validation import DocumentValidator
from app.knowledge.models import KnowledgeDocument
from app.knowledge.service import KnowledgeService


class IngestionPipeline:
    def __init__(
        self,
        knowledge_service: KnowledgeService,
        config: IngestionConfig | None = None,
        cleaner: TextCleaner | None = None,
        metadata_extractor: MetadataExtractor | None = None,
        language_detector: LanguageDetector | None = None,
        duplicate_detector: DuplicateDetector | None = None,
        validator: DocumentValidator | None = None,
    ):
        self._svc = knowledge_service
        self._config = config or IngestionConfig.from_env()
        self._cleaner = cleaner or TextCleaner()
        self._metadata_extractor = metadata_extractor or MetadataExtractor()
        self._language_detector = language_detector or HeuristicLanguageDetector()
        self._duplicate_detector = duplicate_detector or DuplicateDetector()
        self._validator = validator or DocumentValidator(self._config)

    async def ingest_file(
        self,
        path: str,
        collection_id: str,
        title: str | None = None,
        custom_metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        extension = os.path.splitext(path)[1].lower()
        loader = create_loader(extension)
        parser = create_parser(extension)

        stat = os.stat(path) if os.path.exists(path) else None

        return await self._run_pipeline(
            loader=loader,
            parser=parser,
            path=path,
            filename=os.path.basename(path),
            collection_id=collection_id,
            title=title or os.path.splitext(os.path.basename(path))[0],
            custom_metadata=custom_metadata,
            stat=stat,
        )

    async def ingest_bytes(
        self,
        data: bytes,
        filename: str,
        collection_id: str,
        title: str | None = None,
        custom_metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        extension = os.path.splitext(filename)[1].lower()
        loader = create_loader(extension)
        parser = create_parser(extension)

        return await self._run_pipeline(
            loader=loader,
            parser=parser,
            data=data,
            filename=filename,
            collection_id=collection_id,
            title=title or os.path.splitext(filename)[0],
            custom_metadata=custom_metadata,
        )

    async def _run_pipeline(
        self,
        loader: DocumentLoader,
        parser: DocumentParser,
        collection_id: str,
        title: str,
        custom_metadata: dict[str, Any] | None = None,
        path: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        stat: Any | None = None,
    ) -> IngestionResult:
        stages: list[str] = []

        if path:
            loaded = await loader.load(path)
        elif data is not None and filename:
            loaded = await loader.load_bytes(data, filename)
        else:
            raise ValueError("Either path or data+filename required")
        stages.append(IngestionStage.LOAD.value)

        loaded = await self._validator.validate(loaded)
        stages.append(IngestionStage.VALIDATE.value)

        parsed_text = await parser.parse(loaded)
        stages.append(IngestionStage.PARSE.value)

        cleaned_text = await self._cleaner.clean(parsed_text)
        stages.append(IngestionStage.CLEAN.value)

        meta_kwargs: dict[str, Any] = {"custom_metadata": custom_metadata}
        if stat is not None:
            meta_kwargs["stat"] = stat
        if path is not None:
            meta_kwargs["path"] = path
        meta = await self._metadata_extractor.extract(loaded, **meta_kwargs)
        stages.append(IngestionStage.METADATA.value)

        lang_code, lang_conf = await self._language_detector.detect(cleaned_text)
        stages.append(IngestionStage.LANGUAGE.value)

        is_dup, checksum = await self._duplicate_detector.check(loaded)
        stages.append(IngestionStage.DEDUP.value)

        if is_dup:
            if not self._config.allow_duplicate_document:
                existing = await self._find_existing_by_checksum(checksum)
                if existing:
                    return IngestionResult(
                        document_id=existing.id,
                        collection_id=collection_id,
                        title=existing.title,
                        content=existing.content,
                        source=existing.source,
                        language=lang_code,
                        language_confidence=lang_conf,
                        checksum=checksum,
                        is_duplicate=True,
                        size=loaded.size,
                        mime_type=loaded.mime_type,
                        metadata=meta,
                        stages_completed=stages,
                    )

        doc = await self._svc.create_document(
            collection_id=collection_id,
            title=title,
            content=cleaned_text,
            source=f"ingestion:{filename or path}",
            metadata=[{"key": k, "value": str(v)} for k, v in meta.items()],
            tags=[],
        )
        self._duplicate_detector.add_checksum(checksum)
        stages.append(IngestionStage.STORE.value)

        return IngestionResult(
            document_id=doc.id,
            collection_id=collection_id,
            title=doc.title,
            content=doc.content,
            source=doc.source,
            language=lang_code,
            language_confidence=lang_conf,
            checksum=checksum,
            is_duplicate=is_dup,
            size=loaded.size,
            mime_type=loaded.mime_type,
            metadata=meta,
            stages_completed=stages,
        )

    async def _find_existing_by_checksum(self, checksum: str) -> KnowledgeDocument | None:
        all_docs = await self._svc.list_documents(limit=1000)
        for doc in all_docs:
            for meta in doc.metadata:
                if meta.key == "checksum" and meta.value == checksum:
                    return doc
        return None

    @property
    def config(self) -> IngestionConfig:
        return self._config
