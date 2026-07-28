from typing import AsyncIterator

from app.models import (
    ChatRequest,
    ChatResponse,
    ChatChoice,
    Message,
    MessageRole,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingData,
    HealthCheckResponse,
    ModelInfo,
    ProviderStatus,
    StreamChunk,
    StreamChoice,
    Usage,
)
from app.providers.base import BaseProvider


class CustomTestProvider(BaseProvider):
    name = "custom_test"
    display_name = "Custom Test Provider"

    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            id="custom-test-id",
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role=MessageRole.ASSISTANT, content="Hello from custom provider!"),
                    finish_reason="stop",
                )
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(
            id="custom-test-id",
            model=request.model,
            choices=[StreamChoice(index=0, delta={"content": "Hello "}, finish_reason=None)],
        )
        yield StreamChunk(
            id="custom-test-id",
            model=request.model,
            choices=[StreamChoice(index=0, delta={"content": "from custom provider!"}, finish_reason="stop")],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(
            data=[EmbeddingData(embedding=[0.1, 0.2, 0.3], index=0)],
            model=request.model,
            usage=Usage(prompt_tokens=5, completion_tokens=0, total_tokens=5),
        )

    async def health_check(self) -> HealthCheckResponse:
        return HealthCheckResponse(
            status=ProviderStatus.HEALTHY,
            provider=self.name,
            latency_ms=5.0,
        )

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                id="custom-model-v1",
                provider=self.name,
                owned_by=self.name,
                created=1700000000,
            )
        ]
