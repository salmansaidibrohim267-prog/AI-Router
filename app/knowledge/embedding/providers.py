from __future__ import annotations

import hashlib
from typing import Any, Protocol

import numpy as np

from app.knowledge.embedding.config import EmbeddingConfig
from app.knowledge.embedding.models import EmbeddingResult

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str], **kwargs: Any) -> list[EmbeddingResult]: ...

    @property
    def provider_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...


class _BaseProvider:
    def __init__(self, config: EmbeddingConfig | None = None):
        self._config = config or EmbeddingConfig()

    @property
    def provider_name(self) -> str:
        return "base"

    @property
    def dimensions(self) -> int:
        return self._config.dimensions


class OpenAIEmbeddingAdapter(_BaseProvider):
    def __init__(
        self,
        api_key: str = "",
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
        config: EmbeddingConfig | None = None,
    ):
        super().__init__(config)
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    @property
    def provider_name(self) -> str:
        return "openai"

    async def embed(self, texts: list[str], **kwargs: Any) -> list[EmbeddingResult]:
        if not HAS_HTTPX:
            raise RuntimeError("httpx is required for OpenAI embeddings")

        if not self._api_key:
            raise ValueError("OpenAI API key is required")

        data = {"input": texts, "model": self._model}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        timeout_val = kwargs.get("timeout", self._config.timeout)
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            resp = await client.post(
                f"{self._base_url}/embeddings",
                json=data,
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()

        results: list[EmbeddingResult] = []
        for item in body.get("data", []):
            vector = item.get("embedding", [])
            results.append(
                EmbeddingResult(
                    vector=vector,
                    model=self._model,
                    provider=self.provider_name,
                    dimensions=len(vector),
                    token_count=body.get("usage", {}).get("total_tokens", 0) // len(texts),
                )
            )
        return results


class OllamaEmbeddingAdapter(_BaseProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        config: EmbeddingConfig | None = None,
    ):
        super().__init__(config)
        self._base_url = base_url
        self._model = model

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def embed(self, texts: list[str], **kwargs: Any) -> list[EmbeddingResult]:
        if not HAS_HTTPX:
            raise RuntimeError("httpx is required for Ollama embeddings")

        timeout_val = kwargs.get("timeout", self._config.timeout)
        results: list[EmbeddingResult] = []

        async with httpx.AsyncClient(timeout=timeout_val) as client:
            for text in texts:
                data = {"model": self._model, "prompt": text}
                resp = await client.post(
                    f"{self._base_url}/api/embeddings",
                    json=data,
                )
                resp.raise_for_status()
                body = resp.json()
                vector = body.get("embedding", [])
                results.append(
                    EmbeddingResult(
                        vector=vector,
                        model=self._model,
                        provider=self.provider_name,
                        dimensions=len(vector),
                    )
                )
        return results


class LocalEmbeddingAdapter(_BaseProvider):
    def __init__(
        self,
        dimensions: int = 384,
        config: EmbeddingConfig | None = None,
    ):
        c = config or EmbeddingConfig()
        c.dimensions = dimensions
        super().__init__(c)

    @property
    def provider_name(self) -> str:
        return "local"

    async def embed(self, texts: list[str], **kwargs: Any) -> list[EmbeddingResult]:
        results: list[EmbeddingResult] = []
        for text in texts:
            vector = self._embed_text(text, self._config.dimensions)
            results.append(
                EmbeddingResult(
                    vector=vector,
                    model="local",
                    provider=self.provider_name,
                    dimensions=self._config.dimensions,
                    token_count=len(text.split()),
                )
            )
        return results

    def _embed_text(self, text: str, dims: int) -> list[float]:
        if not text:
            return [0.0] * dims

        seed_bytes = hashlib.md5(text.encode("utf-8")).digest()
        seed = int.from_bytes(seed_bytes[:4], "big")
        rng = np.random.RandomState(seed)
        vec = rng.randn(dims).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


try:
    from sentence_transformers import SentenceTransformer

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


class SentenceTransformersAdapter(_BaseProvider):
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        config: EmbeddingConfig | None = None,
    ):
        super().__init__(config)
        self._model_name = model_name
        self._model = None

    @property
    def provider_name(self) -> str:
        return "sentence_transformers"

    async def embed(self, texts: list[str], **kwargs: Any) -> list[EmbeddingResult]:
        if not HAS_SENTENCE_TRANSFORMERS:
            raise RuntimeError("sentence_transformers is required. Install with: pip install sentence-transformers")
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)

        embeddings = self._model.encode(texts, show_progress_bar=False)
        results: list[EmbeddingResult] = []
        for vec in embeddings:
            vector = vec.tolist()
            results.append(
                EmbeddingResult(
                    vector=vector,
                    model=self._model_name,
                    provider=self.provider_name,
                    dimensions=len(vector),
                    token_count=len(texts[0].split()) if texts else 0,
                )
            )
        return results


_PROVIDER_MAP: dict[str, type] = {
    "openai": OpenAIEmbeddingAdapter,
    "ollama": OllamaEmbeddingAdapter,
    "local": LocalEmbeddingAdapter,
    "sentence_transformers": SentenceTransformersAdapter,
}


def create_embedding_provider(
    name: str = "local",
    config: EmbeddingConfig | None = None,
    **kwargs: Any,
) -> EmbeddingProvider:
    cls = _PROVIDER_MAP.get(name)
    if not cls:
        raise ValueError(f"Unknown embedding provider: {name}")
    return cls(config=config, **kwargs)
