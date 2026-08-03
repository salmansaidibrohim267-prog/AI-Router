"""Anthropic provider implementation."""

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


class AnthropicProvider(BaseProvider):
    """Anthropic API provider."""

    name = "anthropic"
    display_name = "Anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs,
    ):
        super().__init__(api_key, base_url, timeout, max_retries, **kwargs)
        self.base_url = base_url or "https://api.anthropic.com/v1"
        self._headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
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

    def _convert_messages(self, messages: list) -> list:
        """Convert messages to Anthropic format."""
        system = None
        converted = []
        for msg in messages:
            if msg.role == "system":
                system = msg.content
            else:
                converted.append({"role": msg.role, "content": msg.content})
        return system, converted

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Send chat completion request."""
        system, messages = self._convert_messages(request.messages)

        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stop_sequences": (
                request.stop if isinstance(request.stop, list) else [request.stop] if request.stop else None
            ),  # noqa: E501
        }
        if system:
            payload["system"] = system

        response = await self._request("POST", "/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")

        usage = Usage(
            prompt_tokens=data.get("usage", {}).get("input_tokens", 0),
            completion_tokens=data.get("usage", {}).get("output_tokens", 0),
            total_tokens=data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0),
        )

        return ChatResponse(
            id=data.get("id", ""),
            model=data.get("model", request.model),
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content=content),
                    finish_reason=data.get("stop_reason"),
                )
            ],
            usage=usage,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream chat completion."""
        system, messages = self._convert_messages(request.messages)

        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 4096,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "stream": True,
        }
        if system:
            payload["system"] = system

        client = await self._get_client()
        async with client.stream("POST", "/messages", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield StreamChunk(
                                    id=data.get("message_id", ""),
                                    model=request.model,
                                    choices=[
                                        StreamChoice(
                                            index=0,
                                            delta={"content": delta.get("text", "")},
                                        )
                                    ],
                                )
                    except json.JSONDecodeError:
                        continue

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings (not supported by Anthropic)."""
        raise ProviderError(
            "Embeddings not supported by Anthropic",
            provider=self.name,
            code="NOT_SUPPORTED",
            status_code=400,
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
                    created=0,
                    owned_by="anthropic",
                    provider=self.name,
                    display_name=m.get("display_name", m.get("id")),
                    description=m.get("description"),
                    max_tokens=m.get("context_window"),
                    context_window=m.get("context_window"),
                    supports_streaming=True,
                    supports_embeddings=False,
                )
            )
        return models
