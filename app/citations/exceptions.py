from __future__ import annotations


class CitationError(Exception):
    pass


class CitationValidationError(CitationError):
    def __init__(self, msg: str = "Citation validation failed"):
        super().__init__(msg)


class CitationResolutionError(CitationError):
    def __init__(self, msg: str = "Citation source resolution failed"):
        super().__init__(msg)


class CitationFormatError(CitationError):
    def __init__(self, msg: str = "Citation formatting failed"):
        super().__init__(msg)


class CitationAttributionError(CitationError):
    def __init__(self, msg: str = "Citation attribution failed"):
        super().__init__(msg)


class CitationScoringError(CitationError):
    def __init__(self, msg: str = "Citation scoring failed"):
        super().__init__(msg)


class CitationGenerationError(CitationError):
    def __init__(self, msg: str = "Citation generation failed"):
        super().__init__(msg)


class UnknownCitationFormatError(CitationFormatError):
    def __init__(self, fmt: str):
        super().__init__(f"Unknown citation format: {fmt}")
