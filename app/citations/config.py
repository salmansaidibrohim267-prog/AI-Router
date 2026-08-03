from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class CitationConfig:
    default_format: str = "numeric"
    attribution_threshold: float = 0.25
    confidence_threshold: float = 0.35
    retrieval_weight: float = 0.4
    rerank_weight: float = 0.35
    attribution_weight: float = 0.25
    max_sources_per_citation: int = 3
    sentence_max_chars: int = 400
    validate_on_generate: bool = True
    resolve_on_generate: bool = True
    dedupe_sources: bool = True
    reference_section_title: str = "References"
    custom_template: str = '{author}. "{title}." {url}'
    json_indent: int = 2
    log_events: bool = True
    track_metrics: bool = True
    supported_formats: tuple[str, ...] = (
        "numeric",
        "ieee",
        "apa",
        "mla",
        "markdown",
        "json",
        "custom",
    )

    @classmethod
    def from_env(cls) -> CitationConfig:
        return cls(
            default_format=os.getenv("CITATION_DEFAULT_FORMAT", "numeric"),
            attribution_threshold=float(os.getenv("CITATION_ATTRIBUTION_THRESHOLD", "0.25")),
            confidence_threshold=float(os.getenv("CITATION_CONFIDENCE_THRESHOLD", "0.35")),
            retrieval_weight=float(os.getenv("CITATION_RETRIEVAL_WEIGHT", "0.4")),
            rerank_weight=float(os.getenv("CITATION_RERANK_WEIGHT", "0.35")),
            attribution_weight=float(os.getenv("CITATION_ATTRIBUTION_WEIGHT", "0.25")),
            max_sources_per_citation=int(os.getenv("CITATION_MAX_SOURCES", "3")),
            sentence_max_chars=int(os.getenv("CITATION_SENTENCE_MAX_CHARS", "400")),
            validate_on_generate=os.getenv("CITATION_VALIDATE_ON_GENERATE", "1") == "1",
            resolve_on_generate=os.getenv("CITATION_RESOLVE_ON_GENERATE", "1") == "1",
            dedupe_sources=os.getenv("CITATION_DEDUPE_SOURCES", "1") == "1",
            reference_section_title=os.getenv("CITATION_REFERENCE_TITLE", "References"),
            custom_template=os.getenv("CITATION_CUSTOM_TEMPLATE", '{author}. "{title}." {url}'),
            json_indent=int(os.getenv("CITATION_JSON_INDENT", "2")),
            log_events=os.getenv("CITATION_LOG_EVENTS", "1") == "1",
            track_metrics=os.getenv("CITATION_TRACK_METRICS", "1") == "1",
        )
