from __future__ import annotations

import json
import re
from typing import Any, Protocol

from app.citations.config import CitationConfig
from app.citations.exceptions import (
    CitationFormatError,
    UnknownCitationFormatError,
)
from app.citations.models import (
    Citation,
    CitationFormat,
    CitationResult,
    CitationSource,
)


class CitationFormatter(Protocol):
    name: str

    def render_inline(self, result: CitationResult) -> str:  # pragma: no cover - protocol stub
        ...

    def render_references(self, result: CitationResult) -> str:  # pragma: no cover - protocol stub
        ...

    def render(self, result: CitationResult) -> str:  # pragma: no cover - protocol stub
        ...


class _BaseFormatter:
    name = "base"

    def __init__(self, config: CitationConfig | None = None):
        self._config = config or CitationConfig()

    def _pairs(self, result: CitationResult) -> list[tuple[CitationMappingLike, Citation]]:
        citations = result.citations
        mappings = result.mappings
        pairs: list[tuple[CitationMappingLike, Citation]] = []
        if len(mappings) == len(citations):
            pairs = list(zip(mappings, citations))
        else:
            by_sentence = {c.sentence: c for c in citations}
            for mapping in mappings:
                citation = by_sentence.get(mapping.sentence)
                if citation is not None:
                    pairs.append((mapping, citation))
        return pairs


class CitationMappingLike(Protocol):
    sentence: str
    start: int
    end: int
    source_ids: list[str]


class NumericCitationFormatter(_BaseFormatter):
    name = "numeric"

    def render_inline(self, result: CitationResult) -> str:
        text = result.text
        pairs = sorted(
            self._pairs(result),
            key=lambda pair: pair[0].end,
            reverse=True,
        )
        for mapping, citation in pairs:
            marker = self._marker(result, citation)
            text = self._insert(text, marker, mapping)
        return text

    def _marker(self, result: CitationResult, citation: Citation) -> str:
        index = self._citation_index(result, citation)
        return f"[{index}]"

    def _insert(self, text: str, marker: str, mapping: CitationMappingLike) -> str:
        end = mapping.end
        if end > len(text):
            end = len(text)
        return text[:end] + marker + text[end:]

    def _citation_index(self, result: CitationResult, citation: Citation) -> int:
        for i, c in enumerate(result.citations, start=1):
            if c.citation_id == citation.citation_id:
                return i
        return 1

    def render_references(self, result: CitationResult) -> str:
        lines: list[str] = []
        for i, citation in enumerate(result.citations, start=1):
            parts: list[str] = []
            for source in self._sources_for(result, citation):
                parts.append(self._ref_entry(source))
            lines.append(f"[{i}] " + "; ".join(parts))
        return "\n".join(lines)

    def _sources_for(self, result: CitationResult, citation: Citation) -> list[CitationSource]:
        ids = set(citation.source_ids)
        return [s for s in result.sources if s.source_id in ids]

    def _primary_source(self, result: CitationResult, citation: Citation) -> CitationSource | None:
        sources = self._sources_for(result, citation)
        return sources[0] if sources else None

    def _ref_entry(self, source: CitationSource) -> str:
        parts = [p for p in (source.author, source.title) if p]
        if source.filename:
            parts.append(source.filename)
        if source.url:
            parts.append(source.url)
        return ", ".join(parts) if parts else source.source_id

    def render(self, result: CitationResult) -> str:
        body = self.render_inline(result)
        refs = self.render_references(result)
        return body + "\n\n" + refs


class IEEECitationFormatter(NumericCitationFormatter):
    name = "ieee"

    def _marker(self, result: CitationResult, citation: Citation) -> str:
        return super()._marker(result, citation)

    def _ref_entry(self, source: CitationSource) -> str:
        author = source.author or source.filename
        year = source.year
        parts: list[str] = []
        if author:
            parts.append(author)
        if source.title:
            parts.append(f'"{source.title}"')
        if source.section:
            parts.append(f"sec. {source.section}")
        if source.page:
            parts.append(f"p. {source.page}")
        if year:
            parts.append(year)
        if source.url:
            parts.append(source.url)
        return ", ".join(parts) if parts else source.source_id


class APACitationFormatter(NumericCitationFormatter):
    name = "apa"

    def _marker(self, result: CitationResult, citation: Citation) -> str:
        source = self._primary_source(result, citation)
        if source is None:
            return "(n.d.)"
        author = source.author_last
        year = source.year
        if author:
            inner = ", ".join(p for p in (author, year) if p)
        elif source.title:
            inner = ", ".join(p for p in (source.title, year) if p)
        else:
            inner = year or "n.d."
        if source.page:
            inner += f", p. {source.page}"
        return f"({inner})"

    def render_references(self, result: CitationResult) -> str:
        seen: set[str] = set()
        lines: list[str] = []
        for citation in result.citations:
            for source in self._sources_for(result, citation):
                if source.source_id in seen:
                    continue
                seen.add(source.source_id)
                lines.append(self._ref_entry(source))
        return "\n".join(lines)

    def _ref_entry(self, source: CitationSource) -> str:
        author = source.author_last
        year = source.year or "n.d."
        title = source.title or source.filename or source.source_id
        parts = [f"{author} ({year})." if author else f"{title} ({year})."]
        if author and source.title:
            parts = [f"{author} ({year}). {title}."]
        if source.url:
            parts.append(f"Retrieved from {source.url}")
        return " ".join(parts)


class MLACitationFormatter(NumericCitationFormatter):
    name = "mla"

    def _marker(self, result: CitationResult, citation: Citation) -> str:
        source = self._primary_source(result, citation)
        if source is None:
            return "(n.p.)"
        author = source.author_last or source.filename
        inner = author
        if source.page:
            inner += f" {source.page}"
        return f"({inner})"

    def render_references(self, result: CitationResult) -> str:
        seen: set[str] = set()
        lines: list[str] = []
        for citation in result.citations:
            for source in self._sources_for(result, citation):
                if source.source_id in seen:
                    continue
                seen.add(source.source_id)
                lines.append(self._ref_entry(source))
        return "\n".join(lines)

    def _ref_entry(self, source: CitationSource) -> str:
        last = source.author_last
        full = source.author
        title = source.title or source.filename or source.source_id
        parts: list[str] = []
        if last:
            first = full[: -len(last)].strip() if full.endswith(last) else full
            parts.append(f"{last}, {first}." if first else f"{last}.")
        parts.append(f'"{title}."')
        if source.year:
            parts.append(source.year + ",")
        if source.url:
            parts.append(source.url + ".")
        return " ".join(parts)


class MarkdownCitationFormatter(NumericCitationFormatter):
    name = "markdown"

    def _marker(self, result: CitationResult, citation: Citation) -> str:
        index = self._citation_index(result, citation)
        return f"[^{index}]"

    def render_references(self, result: CitationResult) -> str:
        lines: list[str] = []
        for i, citation in enumerate(result.citations, start=1):
            parts: list[str] = []
            for source in self._sources_for(result, citation):
                ref_parts = [p for p in (source.author, f'*{source.title}*' if source.title else "") if p]
                if source.filename:
                    ref_parts.append(source.filename)
                if source.page:
                    ref_parts.append(f"p. {source.page}")
                if source.url:
                    ref_parts.append(source.url)
                parts.append(", ".join(ref_parts) if ref_parts else source.source_id)
            lines.append(f"[^{i}]: " + "; ".join(parts))
        return "\n".join(lines)


class JSONCitationFormatter(_BaseFormatter):
    name = "json"

    def render_inline(self, result: CitationResult) -> str:
        return self.render(result)

    def render_references(self, result: CitationResult) -> str:
        return ""

    def render(self, result: CitationResult) -> str:
        payload: dict[str, Any] = {
            "text": result.text,
            "format": result.format.value,
            "confidence": round(result.confidence, 4),
            "citations": [c.to_dict() for c in result.citations],
            "sources": [s.to_dict() for s in result.sources],
            "references": self._references(result),
        }
        return json.dumps(payload, indent=self._config.json_indent)

    def _references(self, result: CitationResult) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for citation in result.citations:
            for source in result.sources:
                if source.source_id in citation.source_ids:
                    refs.append(
                        {
                            "citation_id": citation.citation_id,
                            "source_id": source.source_id,
                            "title": source.title,
                            "author": source.author,
                            "url": source.url,
                            "page": source.page,
                            "confidence": round(citation.confidence, 4),
                        }
                    )
        return refs


class CustomCitationFormatter(NumericCitationFormatter):
    name = "custom"

    def __init__(self, config: CitationConfig | None = None, template: str | None = None):
        super().__init__(config)
        self._template = template or self._config.custom_template

    def _ref_entry(self, source: CitationSource) -> str:
        fields = {
            "index": "",
            "author": source.author,
            "title": source.title,
            "year": source.year,
            "filename": source.filename,
            "page": source.page,
            "section": source.section,
            "url": source.url,
            "document_id": source.document_id,
            "chunk_id": source.chunk_id,
        }
        try:
            return self._template.format(**fields)
        except (KeyError, IndexError, ValueError) as e:
            raise CitationFormatError(f"Invalid custom template: {e}") from e


class FormatFactory:
    def __init__(self, config: CitationConfig | None = None):
        self._config = config or CitationConfig()
        self._registry: dict[str, CitationFormatter] = {}

    def _defaults(self) -> dict[str, CitationFormatter]:
        defaults = {
            CitationFormat.NUMERIC.value: NumericCitationFormatter(self._config),
            CitationFormat.IEEE.value: IEEECitationFormatter(self._config),
            CitationFormat.APA.value: APACitationFormatter(self._config),
            CitationFormat.MLA.value: MLACitationFormatter(self._config),
            CitationFormat.MARKDOWN.value: MarkdownCitationFormatter(self._config),
            CitationFormat.JSON.value: JSONCitationFormatter(self._config),
            CitationFormat.CUSTOM.value: CustomCitationFormatter(self._config),
        }
        return defaults

    def register(self, name: str, formatter: CitationFormatter) -> None:
        self._registry[name] = formatter

    def names(self) -> list[str]:
        return list(self._defaults()) + [n for n in self._registry if n not in self._defaults()]

    def create(self, name: str) -> CitationFormatter:
        if name in self._registry:
            return self._registry[name]
        defaults = self._defaults()
        if name in defaults:
            return defaults[name]
        raise UnknownCitationFormatError(name)

    def is_supported(self, name: str) -> bool:
        return name in self.names()
