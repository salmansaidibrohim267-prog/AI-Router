from __future__ import annotations


class EmbeddingValidationError(ValueError):
    pass


class EmptyTextError(EmbeddingValidationError):
    def __init__(self) -> None:
        super().__init__("Text cannot be empty")


class TextTooLongError(EmbeddingValidationError):
    def __init__(self, length: int, max_length: int = 8192):
        self.length = length
        self.max_length = max_length
        super().__init__(f"Text too long: {length} chars (max {max_length})")


class ProviderUnavailableError(EmbeddingValidationError):
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"Embedding provider '{provider}' is not available")


class DimensionMismatchError(EmbeddingValidationError):
    def __init__(self, expected: int, got: int):
        self.expected = expected
        self.got = got
        super().__init__(f"Dimension mismatch: expected {expected}, got {got}")


class InvalidResponseError(EmbeddingValidationError):
    def __init__(self, detail: str = "Invalid embedding response"):
        self.detail = detail
        super().__init__(detail)


class EmbeddingValidator:
    MAX_TEXT_LENGTH = 8192

    async def validate_text(self, text: str) -> str:
        if not text or not text.strip():
            raise EmptyTextError()
        if len(text) > self.MAX_TEXT_LENGTH:
            raise TextTooLongError(len(text), self.MAX_TEXT_LENGTH)
        return text.strip()

    async def validate_texts(self, texts: list[str]) -> list[str]:
        if not texts:
            raise EmbeddingValidationError("Text list cannot be empty")
        return [await self.validate_text(t) for t in texts]

    async def validate_result(
        self,
        result: list[float],
        expected_dims: int,
    ) -> list[float]:
        if not result:
            raise InvalidResponseError("Empty embedding vector")
        if len(result) != expected_dims:
            raise DimensionMismatchError(expected_dims, len(result))
        return result
