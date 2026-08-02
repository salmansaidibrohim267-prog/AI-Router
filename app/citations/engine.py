from __future__ import annotations

import time
from typing import Any

from app.citations.attribution import (
    AttributionStrategy,
    EmbeddingAttributionStrategy,
    SentenceAttributionMapper,
    TokenOverlapAttributionStrategy,
)
from app.citations.builder import CitationResultBuilder
from app.citations.config import CitationConfig
from app.citations.exceptions import (
    CitationError,
    CitationGenerationError,
    CitationValidationError,
    UnknownCitationFormatError,
)
from app.citations.formats import (
    CitationFormatter,
    FormatFactory,
)
from app.citations.logging import CitationLogger
from app.citations.models import (
    Citation,
    CitationFormat,
    CitationRequest,
    CitationResult,
    CitationSource,
    ValidationResult,
)
from app.citations.resolver import SourceResolver
from app.citations.scoring import CitationScorer
from app.citations.statistics import CitationMetricsTracker
from app.citations.validator import CitationValidator


class CitationEngine:
    """Production-grade citation engine for the AI Router Knowledge Layer.

    Composes source resolution, sentence-level attribution, confidence scoring,
    formatting strategies, and validation via dependency injection.
    """

    def __init__(
        self,
        config: CitationConfig | None = None,
        resolver: SourceResolver | None = None,
        attribution: AttributionStrategy | None = None,
        mapper: SentenceAttributionMapper | None = None,
        scorer: CitationScorer | None = None,
        validator: CitationValidator | None = None,
        formatter_factory: FormatFactory | None = None,
        logger: CitationLogger | None = None,
        metrics: CitationMetricsTracker | None = None,
        embedder: Any | None = None,
    ):
        self._config = config or CitationConfig()
        self._resolver = resolver or SourceResolver(self._config)
        if attribution is None:
            attribution = (
                EmbeddingAttributionStrategy(embedder)
                if embedder is not None
                else TokenOverlapAttributionStrategy()
            )
        self._attribution = attribution
        self._mapper = mapper or SentenceAttributionMapper(
            attribution,
            threshold=self._config.attribution_threshold,
            max_sources_per_sentence=self._config.max_sources_per_citation,
            max_chars=self._config.sentence_max_chars,
        )
        self._scorer = scorer or CitationScorer(self._config)
        self._validator = validator or CitationValidator(self._config)
        self._formatter_factory = formatter_factory or FormatFactory(self._config)
        self._logger = logger or CitationLogger()
        self._metrics = metrics or CitationMetricsTracker()

    # ---------------------------------------------------------------- helpers

    def _normalize_format(self, fmt: CitationFormat | str | None) -> CitationFormat:
        if fmt is None:
            fmt = self._config.default_format
        if isinstance(fmt, CitationFormat):
            return fmt
        if isinstance(fmt, str) and fmt in (f.value for f in CitationFormat):
            return CitationFormat(fmt)
        if isinstance(fmt, str):
            raise UnknownCitationFormatError(fmt)
        raise CitationGenerationError(f"Invalid citation format: {fmt!r}")

    def _get_formatter(self, fmt: CitationFormat) -> CitationFormatter:
        return self._formatter_factory.create(fmt.value)

    # ---------------------------------------------------------------- generate

    def generate(
        self,
        text: str = "",
        sources: list[Any] | None = None,
        query: str = "",
        fmt: CitationFormat | str | None = None,
        request: CitationRequest | None = None,
        **options: Any,
    ) -> CitationResult:
        req = request
        if req is None:
            req = CitationRequest(
                text=text,
                sources=sources or [],
                query=query,
                format=self._normalize_format(fmt),
                options=options,
            )
        return self._generate_impl(req, async_mode=False)

    async def generate_async(
        self,
        text: str = "",
        sources: list[Any] | None = None,
        query: str = "",
        fmt: CitationFormat | str | None = None,
        request: CitationRequest | None = None,
        **options: Any,
    ) -> CitationResult:
        req = request
        if req is None:
            req = CitationRequest(
                text=text,
                sources=sources or [],
                query=query,
                format=self._normalize_format(fmt),
                options=options,
            )
        return await self._generate_impl_async(req)

    async def batch_generate(
        self,
        requests: list[CitationRequest],
    ) -> list[CitationResult]:
        t0 = time.perf_counter()
        try:
            results = [await self._generate_impl_async(r) for r in requests]
            self._metrics.record_batch(
                items=len(requests),
                citations=sum(len(r.citations) for r in results),
            )
            return results
        except Exception as e:
            self._metrics.record_error()
            self._logger.log_error(e, context="batch_generate")
            raise CitationGenerationError(f"Batch citation generation failed: {e}") from e

    def _generate_impl(
        self,
        request: CitationRequest,
        async_mode: bool = False,
    ) -> CitationResult:
        t0 = time.perf_counter()
        try:
            if not request.text or not request.text.strip():
                raise CitationValidationError("Generated text must not be empty")
            fmt = self._normalize_format(request.format)

            raw_sources = list(request.sources)
            if request.resolve and self._config.resolve_on_generate:
                resolved = self._resolver.resolve(raw_sources)
            else:
                resolved = [s for s in raw_sources if isinstance(s, CitationSource)]

            mappings = self._mapper.map(request.text, resolved)
            result = self._assemble(request.text, fmt, resolved, mappings, request)
            if request.validate and self._config.validate_on_generate:
                validation = self._validator.validate_result(result)
                result.errors.extend(validation.errors)
                result.warnings.extend(validation.warnings)
            self._record_success(result, t0, async_mode=async_mode)
            return result
        except CitationError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            self._logger.log_error(e, context="generate")
            raise CitationGenerationError(f"Citation generation failed: {e}") from e

    async def _generate_impl_async(self, request: CitationRequest) -> CitationResult:
        t0 = time.perf_counter()
        try:
            if not request.text or not request.text.strip():
                raise CitationValidationError("Generated text must not be empty")
            fmt = self._normalize_format(request.format)

            raw_sources = list(request.sources)
            if request.resolve and self._config.resolve_on_generate:
                resolved = await self._resolver.resolve_async(raw_sources)
            else:
                resolved = [s for s in raw_sources if isinstance(s, CitationSource)]

            mappings = await self._mapper.map_async(request.text, resolved)
            result = self._assemble(request.text, fmt, resolved, mappings, request)
            if request.validate and self._config.validate_on_generate:
                validation = await self._validator.validate_async(result)
                result.errors.extend(validation.errors)
                result.warnings.extend(validation.warnings)
            self._record_success(result, t0, async_mode=True)
            return result
        except CitationError:
            self._metrics.record_error()
            raise
        except Exception as e:
            self._metrics.record_error()
            self._logger.log_error(e, context="generate_async")
            raise CitationGenerationError(f"Citation generation failed: {e}") from e

    def _assemble(
        self,
        text: str,
        fmt: CitationFormat,
        sources: list[CitationSource],
        mappings: list[Any],
        request: CitationRequest,
    ) -> CitationResult:
        builder = CitationResultBuilder(text, fmt).with_sources(sources)
        citation_count = 0
        for mapping in mappings:
            attribution = mapping.attribution_score
            source_scores = {
                sid: self._scorer.score(source, mapping.scores.get(sid, 0.0))
                for source in sources
                for sid in mapping.source_ids
                if source.source_id == sid
            }
            confidence = self._scorer.aggregate(list(source_scores.values()))
            citation_count += 1
            citation = Citation(
                citation_id=f"c{citation_count}",
                sentence=mapping.sentence,
                source_ids=list(mapping.source_ids),
                confidence=confidence,
                format=fmt,
            )
            for source in sources:
                if source.source_id in mapping.source_ids:
                    source.attribution_score = max(
                        source.attribution_score, mapping.scores.get(source.source_id, 0.0)
                    )
            builder.add_citation(citation)
            builder.add_mapping(mapping)

        formatter = self._get_formatter(fmt)
        partial = builder.build()
        confidence = self._scorer.score_result(partial.citations, sources)
        builder.with_confidence(confidence)
        full = builder.build()
        rendered = formatter.render_inline(full)
        references = formatter.render_references(full)

        builder.with_rendered(rendered).with_references(references)
        return builder.build()

    def _record_success(
        self,
        result: CitationResult,
        t0: float,
        async_mode: bool = False,
    ) -> None:
        latency = (time.perf_counter() - t0) * 1000
        if async_mode:
            self._metrics.record_async_generation(
                len(result.citations), len(result.sources), latency
            )
        else:
            self._metrics.record_generation(
                len(result.citations), len(result.sources), latency
            )
        if self._config.log_events:
            self._logger.log_event("generate", result, latency_ms=round(latency, 4))

    # ---------------------------------------------------------------- validate

    def validate(
        self,
        result: CitationResult,
    ) -> ValidationResult:
        self._metrics.record_validation()
        return self._validator.validate_result(result)

    async def validate_async(
        self,
        result: CitationResult,
    ) -> ValidationResult:
        self._metrics.record_validation()
        return await self._validator.validate_async(result)

    # ---------------------------------------------------------------- resolve

    def resolve(
        self,
        raw_sources: list[Any],
    ) -> list[CitationSource]:
        resolved = self._resolver.resolve(raw_sources)
        self._metrics.record_resolution(len(resolved))
        return resolved

    async def resolve_async(
        self,
        raw_sources: list[Any],
    ) -> list[CitationSource]:
        resolved = await self._resolver.resolve_async(raw_sources)
        self._metrics.record_resolution(len(resolved))
        return resolved

    # ---------------------------------------------------------------- format

    def format(
        self,
        result: CitationResult,
        style: CitationFormat | str | None = None,
    ) -> str:
        self._metrics.record_format()
        try:
            if style is None:
                fmt = result.format
                name = fmt.value if isinstance(fmt, CitationFormat) else str(fmt)
                formatter = self._formatter_factory.create(name)
            elif isinstance(style, CitationFormat):
                formatter = self._get_formatter(style)
            elif isinstance(style, str) and style in (f.value for f in CitationFormat):
                formatter = self._get_formatter(CitationFormat(style))
            else:
                formatter = self._formatter_factory.create(style)
            rendered = formatter.render(result)
        except UnknownCitationFormatError:
            raise
        except Exception as e:
            self._metrics.record_error()
            raise CitationGenerationError(f"Citation formatting failed: {e}") from e
        return rendered

    def register_format(self, name: str, formatter: CitationFormatter) -> None:
        self._formatter_factory.register(name, formatter)

    def get_metrics(self) -> Any:
        return self._metrics.get_metrics()
