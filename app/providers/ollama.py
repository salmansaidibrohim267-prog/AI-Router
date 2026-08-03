"""Ollama provider implementation."""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import httpx

from app.exceptions import (
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.models import (
    ChatChoice,
    ChatRequest,
    ChatResponse,
    EmbeddingData,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResponse,
    Message,
    ModelInfo,
    ProviderStatus,
    StreamChoice,
    StreamChunk,
    Usage,
)
from app.providers.base import BaseProvider


class OllamaProvider(BaseProvider):
    """Ollama local LLM provider."""

    name = "ollama"
    display_name = "Ollama"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
        **kwargs,
    ):
        super().__init__(api_key, base_url, timeout, max_retries, **kwargs)
        self.base_url = base_url or "http://localhost:11434"
        self._headers = {"Content-Type": "application/json"}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """Make HTTP request with retries."""
        client = await self._get_client()
        last_error = None

        for _ in range(self.max_retries):
            try:
                response = await client.request(method, path, **kwargs)
                return response
            except httpx.TimeoutException:
                last_error = ProviderTimeoutError(
                    f"Request timeout after {self.timeout}s",
                    provider=self.name,
                    timeout=self.timeout,
                )
            except httpx.ConnectError as e:
                last_error = ProviderUnavailableError(
                    f"Connection failed: {e}",
                    provider=self.name,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    raise ProviderRateLimitError(
                        "Rate limit exceeded",
                        provider=self.name,
                    ) from e
                raise

        raise last_error or ProviderError(
            "Request failed after retries",
            provider=self.name,
        )

    def _convert_messages(self, messages: list) -> list[dict]:
        """Convert messages to Ollama format."""
        return [
            {"role": msg.role.value if hasattr(msg.role, "value") else msg.role, "content": msg.content}
            for msg in messages
        ]

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Send chat completion request."""
        payload = {
            "model": request.model,
            "messages": self._convert_messages(request.messages),
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "top_p": request.top_p,
            },
        }

        response = await self._request("POST", "/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        message = data.get("message", {})
        return ChatResponse(
            id=data.get("id", ""),
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(
                        role=message.get("role", "assistant"),
                        content=message.get("content", ""),
                    ),
                    finish_reason=data.get("done_reason"),
                )
            ],
            usage=Usage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            ),
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream chat completion."""
        payload = {
            "model": request.model,
            "messages": self._convert_messages(request.messages),
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "top_p": request.top_p,
            },
        }

        client = await self._get_client()
        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("done"):
                        break
                    message = data.get("message", {})
                    yield StreamChunk(
                        id=data.get("id", ""),
                        model=request.model,
                        choices=[
                            StreamChoice(
                                index=0,
                                delta={"content": message.get("content", "")},
                                finish_reason=data.get("done_reason"),
                            )
                        ],
                    )
                except json.JSONDecodeError:
                    continue

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings."""
        inputs = request.input if isinstance(request.input, list) else [request.input]
        embeddings = []

        for i, text in enumerate(inputs):
            payload = {"model": request.model, "prompt": text}
            response = await self._request("POST", "/api/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            embeddings.append(EmbeddingData(embedding=data.get("embedding", []), index=i))

        return EmbeddingResponse(
            data=embeddings,
            model=request.model,
            usage=Usage(prompt_tokens=sum(len(e.embedding) for e in embeddings)),
        )

    async def health_check(self) -> HealthCheckResponse:
        """Check provider health."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get("/api/tags", timeout=10.0)
            response.raise_for_status()
            latency = (time.perf_counter() - start) * 1000

            models = response.json().get("models", [])
            return HealthCheckResponse(
                status=ProviderStatus.HEALTHY,
                provider=self.name,
                latency_ms=latency,
                details={"models_count": len(models)},
            )
        except httpx.TimeoutException:
            return HealthCheckResponse(
                status=ProviderStatus.UNHEALTHY,
                provider=self.name,
                error="Health check timeout",
            )
        except httpx.ConnectError:
            return HealthCheckResponse(
                status=ProviderStatus.UNHEALTHY,
                provider=self.name,
                error="Cannot connect to Ollama",
            )
        except Exception as e:
            return HealthCheckResponse(
                status=ProviderStatus.UNHEALTHY,
                provider=self.name,
                error=str(e),
            )

    async def list_models(self) -> list[ModelInfo]:
        """List available models."""
        client = await self._get_client()
        response = await client.get("/api/tags")
        response.raise_for_status()
        data = response.json()

        models = []
        for m in data.get("models", []):
            models.append(
                ModelInfo(
                    id=m.get("name", ""),
                    created=0,
                    owned_by="ollama",
                    provider=self.name,
                    display_name=m.get("name"),
                    description=f"Size: {m.get('size', 0)} bytes",
                    max_tokens=4096,
                    context_window=4096,
                    supports_streaming=True,
                    supports_embeddings=False,
                )
            )
        return models
