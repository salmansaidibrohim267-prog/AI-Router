from __future__ import annotations

from typing import Any

from app.citations.config import CitationConfig
from app.citations.models import (
    CitationFormat,
    CitationResult,
    CitationSource,
    ValidationResult,
)


class CitationValidator:
    def __init__(self, config: CitationConfig | None = None):
        self._config = config or CitationConfig()

    def _known_ids(self, sources: list[CitationSource]) -> set[str]:
        return {s.source_id for s in sources}

    def validate_citation_source_ids(
        self,
        source_ids: list[str],
        known_ids: set[str],
        sentence: str,
    ) -> list[str]:
        errors: list[str] = []
        if not source_ids:
            errors.append(f"No supporting sources for sentence: {sentence[:80]!r}")
        for sid in source_ids:
            if sid not in known_ids:
                errors.append(
                    f"Citation references unknown source {sid!r} (sentence {sentence[:40]!r})"
                )
        return errors

    def validate_result(
        self,
        result: CitationResult,
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        known = self._known_ids(result.sources)

        if not result.sources:
            errors.append("No sources provided for citation")
        if not result.citations:
            errors.append("No citations were generated")

        for citation in result.citations:
            errors.extend(
                self.validate_citation_source_ids(
                    citation.source_ids, known, citation.sentence
                )
            )
            if citation.confidence < self._config.confidence_threshold:
                errors.append(
                    f"Citation {citation.citation_id} confidence "
                    f"{citation.confidence:.3f} below threshold "
                    f"{self._config.confidence_threshold}"
                )

        unattributed = [
            m for m in result.mappings if not m.source_ids
        ]
        low_attribution = [
            m for m in result.mappings
            if m.source_ids and m.attribution_score < self._config.attribution_threshold
        ]
        if unattributed:
            warnings.append(
                f"{len(unattributed)} sentence(s) without supporting sources "
                "(potential hallucination)"
            )
        if low_attribution:
            warnings.append(
                f"{len(low_attribution)} sentence(s) with weak attribution scores"
            )

        if result.format != CitationFormat.JSON and result.citations and not result.rendered:
            warnings.append("Rendered text is empty")

        return ValidationResult(
            valid=not errors,
            errors=errors,
            warnings=warnings,
            confidence=result.confidence,
            checked_citations=len(result.citations),
            checked_sources=len(result.sources),
        )

    def validate(self, result: CitationResult) -> ValidationResult:
        return self.validate_result(result)

    async def validate_async(self, result: CitationResult) -> ValidationResult:
        return self.validate_result(result)

    def validate_sources(self, sources: list[CitationSource]) -> list[str]:
        errors: list[str] = []
        for source in sources:
            if not source.source_id:
                errors.append("Source is missing a source_id")
            if not source.content:
                errors.append(f"Source {source.source_id!r} has no content")
        return errors
