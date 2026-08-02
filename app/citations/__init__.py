from app.citations.config import CitationConfig
from app.citations.engine import CitationEngine
from app.citations.models import (
    Citation,
    CitationFormat,
    CitationMapping,
    CitationMetrics,
    CitationRequest,
    CitationResult,
    CitationSource,
    ValidationResult,
)


def create_citation_engine(
    config: CitationConfig | None = None,
    **kwargs,
) -> CitationEngine:
    if config is None:
        config = CitationConfig.from_env()
    return CitationEngine(config=config, **kwargs)


__all__ = [
    "CitationConfig",
    "CitationEngine",
    "CitationSource",
    "Citation",
    "CitationMapping",
    "CitationFormat",
    "CitationRequest",
    "CitationResult",
    "CitationMetrics",
    "ValidationResult",
    "create_citation_engine",
]
