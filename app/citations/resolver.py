from __future__ import annotations

from typing import Any, Callable

from app.citations.config import CitationConfig
from app.citations.exceptions import CitationResolutionError
from app.citations.models import CitationSource


class SourceResolver:
    """Resolves raw retrieved chunks / memory items / dicts into CitationSources.

    Accepts, in order of preference:
      - CitationSource instances (passed through)
      - dicts (converted via CitationSource.from_dict)
      - objects with `.chunk_id`, `.content`, `.score` (e.g. RAG RetrievedChunk)
      - objects with `.content` and `.metadata` (e.g. memory MemoryItem)
    A custom `metadata_mapper` callable may be supplied to extract metadata from
    arbitrary objects before the generic heuristics are applied.
    """

    def __init__(
        self,
        config: CitationConfig | None = None,
        metadata_mapper: Callable[[Any], dict[str, Any] | None] | None = None,
    ):
        self._config = config or CitationConfig()
        self._metadata_mapper = metadata_mapper

    def _extract_metadata(self, obj: Any) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if self._metadata_mapper is not None:
            try:
                mapped = self._metadata_mapper(obj)
                if isinstance(mapped, dict):
                    metadata.update(mapped)
            except Exception:
                pass
        raw = getattr(obj, "metadata", None)
        if isinstance(raw, dict):
            metadata.update(raw)
        return metadata

    def _from_dict(self, data: dict[str, Any]) -> CitationSource:
        source = CitationSource.from_dict(data)
        source.content = str(data.get("content", "")) or source.content
        source.retrieval_score = float(data.get("retrieval_score", data.get("score", source.retrieval_score)))
        return source

    def _from_retrieved(self, obj: Any) -> CitationSource:
        metadata = self._extract_metadata(obj)
        chunk_id = str(getattr(obj, "chunk_id", metadata.get("chunk_id", "")))
        fallback_id = str(getattr(obj, "id", "") or "")
        source = CitationSource(
            source_id=chunk_id or fallback_id or metadata.get("source_id", ""),
            chunk_id=chunk_id,
            content=str(getattr(obj, "content", "")),
            retrieval_score=float(getattr(obj, "score", metadata.get("retrieval_score", 0.0)) or 0.0),
            rerank_score=float(getattr(obj, "rerank_score", metadata.get("rerank_score", 0.0)) or 0.0),
            metadata=metadata,
        )
        self._apply_metadata(source, metadata)
        return source

    def _from_generic(self, obj: Any) -> CitationSource:
        metadata = self._extract_metadata(obj)
        content = str(getattr(obj, "content", ""))
        fallback_id = str(getattr(obj, "id", "") or "")
        source = CitationSource(
            source_id=metadata.get("source_id", metadata.get("chunk_id", fallback_id)),
            content=content,
            retrieval_score=float(metadata.get("retrieval_score", 0.0)),
            rerank_score=float(metadata.get("rerank_score", 0.0)),
            metadata=metadata,
        )
        self._apply_metadata(source, metadata)
        return source

    @staticmethod
    def _apply_metadata(source: CitationSource, metadata: dict[str, Any]) -> None:
        for key, attr in (
            ("document_id", "document_id"),
            ("chunk_id", "chunk_id"),
            ("filename", "filename"),
            ("title", "title"),
            ("author", "author"),
            ("page", "page"),
            ("section", "section"),
            ("url", "url"),
            ("published_at", "published_at"),
            ("retrieved_at", "retrieved_at"),
        ):
            value = metadata.get(key)
            if value is not None and value != "":
                setattr(source, attr, str(value))
        if not source.source_id:
            source.source_id = source.chunk_id or metadata.get("source_id", "")

    def _resolve_one(self, raw: Any) -> CitationSource:
        if isinstance(raw, CitationSource):
            return raw
        if isinstance(raw, dict):
            return self._from_dict(raw)
        if hasattr(raw, "chunk_id") or (hasattr(raw, "content") and hasattr(raw, "score")):
            return self._from_retrieved(raw)
        if hasattr(raw, "content"):
            return self._from_generic(raw)
        raise CitationResolutionError(f"Unsupported source type: {type(raw).__name__}")

    def resolve(self, raw_sources: list[Any]) -> list[CitationSource]:
        resolved: list[CitationSource] = []
        seen: set[str] = set()
        for raw in raw_sources:
            try:
                source = self._resolve_one(raw)
            except CitationResolutionError:
                raise
            except Exception as e:
                raise CitationResolutionError(f"Failed to resolve source: {e}") from e
            if self._config.dedupe_sources:
                key = source.source_id or f"{source.document_id}:{source.chunk_id}"
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
            resolved.append(source)
        return resolved

    async def resolve_async(self, raw_sources: list[Any]) -> list[CitationSource]:
        return self.resolve(raw_sources)

    @staticmethod
    def from_rag_chunks(chunks: list[Any]) -> list[CitationSource]:
        resolver = SourceResolver()
        return resolver.resolve(chunks)
