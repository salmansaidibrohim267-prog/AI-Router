"""Groq provider implementation."""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import httpx

from app.exceptions import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.models import (
    ChatChoice,
    ChatRequest,
    ChatResponse,
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


class GroqProvider(BaseProvider):
    """Groq API provider."""

    name = "groq"
    display_name = "Groq"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        **kwargs,
    ):
        super().__init__(api_key, base_url, timeout, max_retries, **kwargs)
        self.base_url = base_url or "https://api.groq.com/openai/v1"
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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
                    retry_after = int(e.response.headers.get("Retry-After", 60))
                    raise ProviderRateLimitError(
                        "Rate limit exceeded",
                        provider=self.name,
                        retry_after=retry_after,
                    ) from e
                elif e.response.status_code == 401:
                    raise ProviderAuthError(
                        "Invalid API key",
                        provider=self.name,
                    ) from e
                raise

        raise last_error or ProviderError(
            "Request failed after retries",
            provider=self.name,
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Send chat completion request."""
        payload = request.model_dump(exclude_none=True)
        response = await self._request("POST", "/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        usage = None
        if "usage" in data:
            usage = Usage(**data["usage"])

        choices = []
        for i, choice in enumerate(data.get("choices", [])):
            msg = choice.get("message", {})
            choices.append(
                ChatChoice(
                    index=i,
                    message=Message(role=msg.get("role", "assistant"), content=msg.get("content", "")),
                    finish_reason=choice.get("finish_reason"),
                )
            )

        return ChatResponse(
            id=data.get("id", ""),
            model=data.get("model", request.model),
            choices=choices,
            usage=usage,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream chat completion."""
        payload = request.model_dump(exclude_none=True)
        payload["stream"] = True

        client = await self._get_client()
        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        chunk = StreamChunk(
                            id=data.get("id", ""),
                            model=data.get("model", request.model),
                            choices=[
                                StreamChoice(
                                    index=c.get("index", 0),
                                    delta=c.get("delta", {}),
                                    finish_reason=c.get("finish_reason"),
                                )
                                for c in data.get("choices", [])
                            ],
                        )
                        yield chunk
                    except json.JSONDecodeError:
                        continue

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings."""
        # Groq doesn't support embeddings yet
        raise ProviderError(
            "Embeddings not supported by Groq",
            provider=self.name,
            code="NOT_SUPPORTED",
            status_code=501,
        )

    async def health_check(self) -> HealthCheckResponse:
        """Check provider health."""
        start = time.perf_counter()
        try:
            client = await self._get_client()
            response = await client.get("/models", timeout=10.0)
            response.raise_for_status()
            latency = (time.perf_counter() - start) * 1000

            return HealthCheckResponse(
                status=ProviderStatus.HEALTHY,
                provider=self.name,
                latency_ms=latency,
                details={"models_count": len(response.json().get("data", []))},
            )
        except httpx.TimeoutException:
            return HealthCheckResponse(
                status=ProviderStatus.UNHEALTHY,
                provider=self.name,
                error="Health check timeout",
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
        response = await client.get("/models")
        response.raise_for_status()
        data = response.json()

        models = []
        for m in data.get("data", []):
            models.append(
                ModelInfo(
                    id=m.get("id", ""),
                    created=m.get("created", 0),
                    owned_by=m.get("owned_by", "groq"),
                    provider=self.name,
                    display_name=m.get("id"),
                    max_tokens=m.get("context_window"),
                    context_window=m.get("context_window"),
                    supports_streaming=True,
                    supports_embeddings=False,
                )
            )
        return models
