from __future__ import annotations

from app.citations.models import CitationMetrics


class CitationMetricsTracker:
    def __init__(self):
        self._metrics = CitationMetrics()

    def record_generation(self, citations: int = 0, sources: int = 0, latency_ms: float = 0.0) -> None:
        self._metrics.total_generations += 1
        self._metrics.total_citations += citations
        self._metrics.total_sources += sources
        self._metrics.total_latency_ms += latency_ms

    def record_async_generation(self, citations: int = 0, sources: int = 0, latency_ms: float = 0.0) -> None:
        self.record_generation(citations, sources, latency_ms)
        self._metrics.total_async_generations += 1

    def record_batch(self, items: int, citations: int = 0) -> None:
        self._metrics.total_batch_items += items
        self._metrics.total_citations += citations

    def record_validation(self) -> None:
        self._metrics.total_validations += 1

    def record_resolution(self, sources: int = 0) -> None:
        self._metrics.total_resolutions += 1
        self._metrics.total_sources += sources

    def record_format(self) -> None:
        self._metrics.total_formats += 1

    def record_error(self) -> None:
        self._metrics.total_errors += 1

    def get_metrics(self) -> CitationMetrics:
        return self._metrics
