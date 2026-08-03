from __future__ import annotations

import json

from app.knowledge.ingestion.config import IngestionConfig
from app.knowledge.ingestion.models import LoadedDocument

try:
    from lxml import etree

    HAS_LXML = True
except ImportError:
    HAS_LXML = False

try:
    import charset_normalizer  # noqa: F401 - availability gate

    HAS_CHARSET = True
except ImportError:
    HAS_CHARSET = False


class IngestionValidationError(ValueError):
    pass


class FileTooLargeError(IngestionValidationError):
    def __init__(self, size: int, max_size: int):
        self.size = size
        self.max_size = max_size
        super().__init__(f"File too large: {size} bytes (max {max_size} bytes)")


class UnsupportedFormatError(IngestionValidationError):
    def __init__(self, extension: str, mime_type: str, supported: list[str]):
        self.extension = extension
        self.mime_type = mime_type
        self.supported = supported
        super().__init__(f"Unsupported format: extension={extension}, mime_type={mime_type}")


class CorruptedFileError(IngestionValidationError):
    def __init__(self, message: str = "File appears to be corrupted"):
        self.message = message
        super().__init__(message)


class DocumentValidator:
    def __init__(self, config: IngestionConfig | None = None):
        self._config = config or IngestionConfig()

    async def validate(self, document: LoadedDocument) -> LoadedDocument:
        self._validate_size(document)
        self._validate_extension(document)
        self._validate_mime_type(document)
        self._validate_content(document)
        return document

    def _validate_size(self, document: LoadedDocument) -> None:
        if document.size > self._config.document_max_size:
            raise FileTooLargeError(document.size, self._config.document_max_size)
        if document.size == 0:
            raise CorruptedFileError("File is empty")

    def _validate_extension(self, document: LoadedDocument) -> None:
        ext = document.extension.lower()
        allowed = self._config.supported_document_types
        if ext not in allowed:
            raise UnsupportedFormatError(ext, document.mime_type, allowed)

    def _validate_mime_type(self, document: LoadedDocument) -> None:
        allowed = self._config.supported_mime_types
        if document.mime_type not in allowed:
            raise UnsupportedFormatError(document.extension, document.mime_type, allowed)

    def _validate_content(self, document: LoadedDocument) -> None:
        if not document.content:
            raise CorruptedFileError("File content is empty")

        if document.extension == ".pdf":
            if not document.content.startswith(b"%PDF"):
                raise CorruptedFileError("File does not appear to be a valid PDF")

        elif document.extension == ".json":
            try:
                raw = document.content.decode(document.encoding, errors="replace")
                json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise CorruptedFileError(f"Invalid JSON: {e}") from e

        elif document.extension in (".html", ".htm"):
            if HAS_LXML:
                try:
                    etree.fromstring(
                        document.content.decode(document.encoding, errors="replace").encode("utf-8"),
                        etree.HTMLParser(),
                    )
                except Exception as e:
                    raise CorruptedFileError(f"Invalid HTML: {e}") from e

    @property
    def config(self) -> IngestionConfig:
        return self._config
