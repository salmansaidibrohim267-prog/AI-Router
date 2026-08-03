from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class IngestionConfig:
    document_max_size: int = 10 * 1024 * 1024
    supported_document_types: list[str] = field(
        default_factory=lambda: [
            ".txt",
            ".md",
            ".mdx",
            ".pdf",
            ".html",
            ".htm",
            ".json",
        ]
    )
    supported_mime_types: list[str] = field(
        default_factory=lambda: [
            "text/plain",
            "text/markdown",
            "application/pdf",
            "text/html",
            "application/json",
        ]
    )
    allow_duplicate_document: bool = False
    default_language: str = "en"
    max_filename_length: int = 255

    @classmethod
    def from_env(cls) -> IngestionConfig:
        return cls(
            document_max_size=int(os.getenv("DOCUMENT_MAX_SIZE", str(10 * 1024 * 1024))),
            allow_duplicate_document=os.getenv("ALLOW_DUPLICATE_DOCUMENT", "0") == "1",
            default_language=os.getenv("DEFAULT_LANGUAGE", "en"),
        )
