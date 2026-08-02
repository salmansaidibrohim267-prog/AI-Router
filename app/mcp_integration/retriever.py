from __future__ import annotations

import time
from typing import Any

from .config import MCPIntegrationConfig
from .exceptions import MCPRetrieverError
from .logging import MCPIntegrationLogger
from .models import MCPRetrievalResult
from .statistics import MCPIntegrationMetricsTracker


class MCPRetriever:
    def __init__(
        self,
        client: Any,
        config: MCPIntegrationConfig | None = None,
        logger: MCPIntegrationLogger | None = None,
        metrics: MCPIntegrationMetricsTracker | None = None,
    ):
        self._client = client
        self._config = config or MCPIntegrationConfig()
        self._logger = logger or MCPIntegrationLogger()
        self._metrics = metrics or MCPIntegrationMetricsTracker(self._config)
        self._cached_resources: list[dict[str, Any]] = []

    @property
    def config(self) -> MCPIntegrationConfig:
        return self._config

    async def _ensure_connected(self) -> None:
        if not getattr(self._client, "connected", False):
            if hasattr(self._client, "connect"):
                await self._client.connect()
            else:
                raise MCPRetrieverError("MCP client is not connected")

    def _parse_content(self, result: Any) -> list[MCPRetrievalResult]:
        parsed: list[MCPRetrievalResult] = []
        structured = getattr(result, "structured_content", None)
        if isinstance(structured, dict):
            items = structured.get("results") or structured.get("chunks") or structured.get("items")
            if isinstance(items, list):
                parsed.extend(self._parse_structured_items(items))
        content = getattr(result, "content", None)
        if not content:
            return parsed
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if text is None:
                    text = block.get("content")
                if isinstance(text, str):
                    parsed.append(
                        MCPRetrievalResult(
                            id=block.get("id", block.get("chunk_id", "")),
                            content=text,
                            score=float(
                                block.get("score", block.get("rerank_score", 0.5))
                            ),
                            metadata=block.get("metadata", {}),
                        )
                    )
            elif isinstance(block, str):
                parsed.append(MCPRetrievalResult(id="", content=block, score=0.5))
        return parsed

    def _parse_structured_items(
        self, items: list[Any]
    ) -> list[MCPRetrievalResult]:
        parsed: list[MCPRetrievalResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = item.get("content", item.get("text"))
            if not isinstance(content, str):
                continue
            parsed.append(
                MCPRetrievalResult(
                    id=str(item.get("id", item.get("chunk_id", ""))),
                    content=content,
                    score=float(item.get("score", item.get("rerank_score", 0.5))),
                    metadata=item.get("metadata", {}),
                )
            )
        return parsed

    async def search_async(self, query: str, top_k: int = 10) -> list[MCPRetrievalResult]:
        start = time.perf_counter()
        try:
            await self._ensure_connected()
            self._metrics.record_tool_call()
            result = await self._client.call_tool(
                self._config.retriever_tool,
                {
                    self._config.retrieval_param_name: query,
                    self._config.retrieval_limit_param: top_k,
                },
                timeout=self._config.timeout,
            )
        except MCPRetrieverError:
            raise
        except Exception as exc:
            self._metrics.record_error()
            raise MCPRetrieverError(f"MCP retrieval failed: {exc}") from exc
        if getattr(result, "is_error", False):
            self._metrics.record_error()
            raise MCPRetrieverError(
                f"Retriever tool {self._config.retriever_tool!r} returned an error"
            )
        results = self._parse_content(result)[:top_k]
        self._metrics.record_retrieval(self._metrics.elapsed(start))
        self._logger.log_event(
            "retrieval",
            query=query,
            top_k=top_k,
            results=len(results),
            tool=self._config.retriever_tool,
        )
        return results

    async def search_resources_async(
        self, query: str, top_k: int = 10
    ) -> list[MCPRetrievalResult]:
        start = time.perf_counter()
        try:
            await self._ensure_connected()
            resources = await self._client.list_resources()
        except Exception as exc:
            self._metrics.record_error()
            raise MCPRetrieverError(f"MCP resource listing failed: {exc}") from exc
        scored: list[MCPRetrievalResult] = []
        prefix = self._config.resource_prefix
        for resource in resources:
            uri = getattr(resource, "uri", None)
            if prefix and not str(uri or "").startswith(prefix):
                continue
            try:
                self._metrics.record_resource_read()
                content = await self._client.read_resource(uri)
            except Exception:
                continue
            text = getattr(content, "text", None)
            if not isinstance(text, str) or not text.strip():
                continue
            score = self._score_text(query, text)
            scored.append(
                MCPRetrievalResult(
                    id=str(uri),
                    content=text,
                    score=score,
                    metadata={"uri": str(uri), "mime_type": getattr(content, "mime_type", "")},
                )
            )
        scored.sort(key=lambda r: r.score, reverse=True)
        results = scored[:top_k]
        self._metrics.record_retrieval(self._metrics.elapsed(start))
        self._logger.log_event(
            "resource_retrieval",
            query=query,
            top_k=top_k,
            results=len(results),
            scanned=len(scored),
        )
        return results

    def _score_text(self, query: str, text: str) -> float:
        query_tokens = {t for t in query.lower().split() if len(t) > 1}
        if not query_tokens:
            return 0.0
        text_lower = text.lower()
        hits = sum(1 for t in query_tokens if t in text_lower)
        return round(hits / len(query_tokens), 4)

    def cache_resources(self, resources: list[dict[str, Any]]) -> None:
        self._cached_resources = list(resources)

    def search(self, query: str, top_k: int = 10) -> list[MCPRetrievalResult]:
        if not self._cached_resources:
            raise MCPRetrieverError(
                "Sync search requires cached resources; call cache_resources first"
            )
        scored: list[MCPRetrievalResult] = []
        for resource in self._cached_resources:
            text = resource.get("content", "")
            if not text:
                continue
            score = self._score_text(query, text)
            scored.append(
                MCPRetrievalResult(
                    id=str(resource.get("id", "")),
                    content=text,
                    score=score,
                    metadata=resource.get("metadata", {}),
                )
            )
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]
