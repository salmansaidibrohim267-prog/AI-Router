from __future__ import annotations

from typing import Any

from app.citations.models import (
    Citation,
    CitationFormat,
    CitationMapping,
    CitationResult,
    CitationSource,
)


class CitationResultBuilder:
    """Fluent builder used by CitationEngine to assemble CitationResult objects."""

    def __init__(self, text: str = "", fmt: CitationFormat | str = CitationFormat.NUMERIC):
        self._text = text
        self._format = CitationFormat(fmt) if isinstance(fmt, str) else fmt
        self._citations: list[Citation] = []
        self._sources: list[CitationSource] = []
        self._mappings: list[CitationMapping] = []
        self._rendered = ""
        self._references = ""
        self._confidence = 0.0
        self._errors: list[str] = []
        self._warnings: list[str] = []

    def with_text(self, text: str) -> CitationResultBuilder:
        self._text = text
        return self

    def with_format(self, fmt: CitationFormat | str) -> CitationResultBuilder:
        self._format = CitationFormat(fmt) if isinstance(fmt, str) else fmt
        return self

    def with_sources(self, sources: list[CitationSource]) -> CitationResultBuilder:
        self._sources = list(sources)
        return self

    def add_source(self, source: CitationSource) -> CitationResultBuilder:
        self._sources.append(source)
        return self

    def with_mappings(self, mappings: list[CitationMapping]) -> CitationResultBuilder:
        self._mappings = list(mappings)
        return self

    def add_mapping(self, mapping: CitationMapping) -> CitationResultBuilder:
        self._mappings.append(mapping)
        return self

    def add_citation(self, citation: Citation) -> CitationResultBuilder:
        self._citations.append(citation)
        return self

    def with_citations(self, citations: list[Citation]) -> CitationResultBuilder:
        self._citations = list(citations)
        return self

    def with_rendered(self, rendered: str) -> CitationResultBuilder:
        self._rendered = rendered
        return self

    def with_references(self, references: str) -> CitationResultBuilder:
        self._references = references
        return self

    def with_confidence(self, confidence: float) -> CitationResultBuilder:
        self._confidence = max(0.0, min(1.0, confidence))
        return self

    def with_errors(self, errors: list[str]) -> CitationResultBuilder:
        self._errors = list(errors)
        return self

    def with_warnings(self, warnings: list[str]) -> CitationResultBuilder:
        self._warnings = list(warnings)
        return self

    def add_error(self, error: str) -> CitationResultBuilder:
        self._errors.append(error)
        return self

    def add_warning(self, warning: str) -> CitationResultBuilder:
        self._warnings.append(warning)
        return self

    def build(self) -> CitationResult:
        return CitationResult(
            text=self._text,
            rendered=self._rendered,
            format=self._format,
            citations=list(self._citations),
            sources=list(self._sources),
            mappings=list(self._mappings),
            confidence=self._confidence,
            references=self._references,
            errors=list(self._errors),
            warnings=list(self._warnings),
        )

    def reset(self) -> CitationResultBuilder:
        self.__init__(self._text, self._format)
        return self
