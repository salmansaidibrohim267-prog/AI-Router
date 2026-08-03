"""Google Gemini provider implementation."""

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


class GoogleProvider(BaseProvider):
    """Google Gemini API provider."""

    name = "google"
    display_name = "Google Gemini"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **kwargs,
    ):
        super().__init__(api_key, base_url, timeout, max_retries, **kwargs)
        self.base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"
        self._headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
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

    def _convert_messages(self, messages: list) -> list[dict]:
        """Convert messages to Gemini format."""
        converted = []
        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            converted.append({"role": role, "parts": [{"text": msg.content}]})
        return converted

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
        payload = {
            "contents": self._convert_messages(request.messages),
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "topP": request.top_p,
                "stopSequences": (
                    request.stop if isinstance(request.stop, list) else [request.stop] if request.stop else None
                ),  # noqa: E501
            },
        }

        model_name = request.model.replace("google/", "").replace("gemini-", "gemini-")
        response = await self._request("POST", f"/models/{model_name}:generateContent", json=payload)
        response.raise_for_status()
        data = response.json()

        content = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                content += part.get("text", "")

        usage = Usage(
            prompt_tokens=data.get("usageMetadata", {}).get("promptTokenCount", 0),
            completion_tokens=data.get("usageMetadata", {}).get("candidatesTokenCount", 0),
            total_tokens=data.get("usageMetadata", {}).get("totalTokenCount", 0),
        )

        return ChatResponse(
            id="",
            model=request.model,
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content=content),
                    finish_reason=data.get("candidates", [{}])[0].get("finishReason"),
                )
            ],
            usage=usage,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[StreamChunk]:
        """Stream chat completion."""
        payload = {
            "contents": self._convert_messages(request.messages),
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
                "topP": request.top_p,
            },
        }

        model_name = request.model.replace("google/", "").replace("gemini-", "gemini-")
        client = await self._get_client()
        async with client.stream("POST", f"/models/{model_name}:streamGenerateContent", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    for candidate in data.get("candidates", []):
                        for part in candidate.get("content", {}).get("parts", []):
                            if "text" in part:
                                yield StreamChunk(
                                    id="",
                                    model=request.model,
                                    choices=[
                                        StreamChoice(
                                            index=0,
                                            delta={"content": part["text"]},
                                        )
                                    ],
                                )
                except json.JSONDecodeError:
                    continue

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings."""
        inputs = request.input if isinstance(request.input, list) else [request.input]
        model_name = request.model.replace("google/", "").replace("gemini-", "gemini-")

        all_embeddings = []
        for i, text in enumerate(inputs):
            payload = {"content": {"parts": [{"text": text}]}}
            response = await self._request("POST", f"/models/{model_name}:embedContent", json=payload)
            response.raise_for_status()
            data = response.json()
            all_embeddings.append(EmbeddingData(embedding=data.get("embedding", {}).get("values", []), index=i))

        return EmbeddingResponse(
            data=all_embeddings,
            model=request.model,
            usage=Usage(),
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
                details={"models_count": len(response.json().get("models", []))},
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
        for m in data.get("models", []):
            models.append(
                ModelInfo(
                    id=m.get("name", "").replace("models/", ""),
                    created=0,
                    owned_by="google",
                    provider=self.name,
                    display_name=m.get("displayName"),
                    description=m.get("description"),
                    max_tokens=m.get("outputTokenLimit"),
                    context_window=m.get("inputTokenLimit"),
                    supports_streaming="streamGenerateContent" in m.get("supportedGenerationMethods", []),
                    supports_embeddings="embedContent" in m.get("supportedGenerationMethods", []),
                )
            )
        return models
