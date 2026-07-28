"""Base provider interface for AI providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from app.models import (
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResponse,
    ModelInfo,
    StreamChunk,
    StreamChoice,
)


class BaseProvider(ABC):
    """Abstract base class for all AI providers."""

    name: str = "base"
    """Unique provider identifier."""

    display_name: str = "Base Provider"
    """Human-readable provider name."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs,
    ):
        """Initialize provider.

        Args:
            api_key: API key for authentication.
            base_url: Base URL for API.
            timeout: Request timeout in seconds.
            max_retries: Maximum number of retries.
            **kwargs: Additional provider-specific configuration.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Send a chat completion request.

        Args:
            request: Chat request with messages and parameters.

        Returns:
            Chat response from the provider.

        Raises:
            ProviderError: If the provider returns an error.
        """
        ...

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion response.

        Default fallback: call chat() and yield a single chunk.
        Providers that support native streaming should override this.

        Args:
            request: Chat request with messages and parameters.

        Yields:
            Stream chunks from the provider.

        Raises:
            ProviderError: If the provider returns an error.
        """
        response = await self.chat(request)
        yield StreamChunk(
            id=response.id,
            model=response.model,
            choices=[
                StreamChoice(
                    index=0,
                    delta={"content": response.choices[0].message.content if response.choices else ""},
                    finish_reason=response.choices[0].finish_reason if response.choices else "stop",
                )
            ],
        )
        yield StreamChunk(
            id=response.id,
            model=response.model,
            choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
            usage=response.usage,
        )

    @abstractmethod
    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings for input texts.

        Args:
            request: Embedding request with texts and model.

        Returns:
            Embedding response with vectors.

        Raises:
            ProviderError: If the provider returns an error.
        """
        ...

    @abstractmethod
    async def health_check(self) -> HealthCheckResponse:
        """Check provider health status.

        Returns:
            Health check response with status and details.

        Raises:
            ProviderError: If health check fails.
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List available models from the provider.

        Returns:
            List of model information.

        Raises:
            ProviderError: If listing models fails.
        """
        ...

    async def close(self) -> None:
        """Close provider connections and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"