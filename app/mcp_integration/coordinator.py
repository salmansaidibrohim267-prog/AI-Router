from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from .config import MCPIntegrationConfig
from .exceptions import (
    MCPCitationResolverError,
    MCPIntegrationCoordinatorError,
    MCPRetrieverError,
)
from .logging import MCPIntegrationLogger
from .models import MCPRAGIntegrationResult, MCPRetrievalResult
from .statistics import MCPIntegrationMetricsTracker

GeneratorFn = Callable[[str, str, list[MCPRetrievalResult]], Awaitable[str]]


class MCPIntegrationCoordinator:
    def __init__(
        self,
        client: Any,
        config: MCPIntegrationConfig | None = None,
        logger: MCPIntegrationLogger | None = None,
        metrics: MCPIntegrationMetricsTracker | None = None,
        retriever: Any | None = None,
        memory_adapter: Any | None = None,
        citation_resolver: Any | None = None,
    ):
        from .citations import MCPCitationResolver
        from .memory_adapter import MCPMemoryAdapter
        from .retriever import MCPRetriever

        self._client = client
        self._config = config or MCPIntegrationConfig()
        self._logger = logger or MCPIntegrationLogger()
        self._metrics = metrics or MCPIntegrationMetricsTracker(self._config)
        self._retriever = retriever or MCPRetriever(
            client=self._client,
            config=self._config,
            logger=self._logger,
            metrics=self._metrics,
        )
        self._memory = memory_adapter or MCPMemoryAdapter(
            client=self._client,
            config=self._config,
            logger=self._logger,
            metrics=self._metrics,
        )
        self._citations = citation_resolver or MCPCitationResolver(
            client=self._client,
            config=self._config,
            logger=self._logger,
            metrics=self._metrics,
        )

    @property
    def retriever(self) -> Any:
        return self._retriever

    @property
    def memory(self) -> Any:
        return self._memory

    @property
    def citations(self) -> Any:
        return self._citations

    def _build_context(
        self,
        chunks: list[MCPRetrievalResult],
        memory_chunks: list[dict[str, Any]],
        budget: int,
    ) -> str:
        sections: list[str] = []
        used = 0
        separator = "\n\n---\n\n"
        for chunk in chunks:
            text = chunk.content.strip()
            if not text:
                continue
            item = f"[Source: {chunk.id or chunk.metadata.get('uri', 'unknown')}]\n{text}"
            if used + len(item) > budget:
                break
            sections.append(item)
            used += len(item)
        for chunk in memory_chunks:
            text = chunk.get("content", "").strip()
            if not text:
                continue
            item = f"[Memory: {chunk.get('metadata', {}).get('category', 'general')}]\n{text}"
            if used + len(item) > budget:
                break
            sections.append(item)
            used += len(item)
        return separator.join(sections)

    async def _generate_answer(
        self,
        generator: GeneratorFn | None,
        query: str,
        context: str,
        chunks: list[MCPRetrievalResult],
    ) -> str:
        if generator is None:
            raise MCPIntegrationCoordinatorError(
                "No answer generator configured; pass a generator callable to answer()"
            )
        return await generator(query, context, chunks)

    async def answer(
        self,
        query: str,
        scope: dict[str, str] | None = None,
        top_k: int = 10,
        generator: GeneratorFn | None = None,
    ) -> MCPRAGIntegrationResult:
        start = time.perf_counter()
        chunks: list[MCPRetrievalResult] = []
        memories: list[dict[str, Any]] = []
        try:
            try:
                chunks = await self._retriever.search_async(query, top_k)
            except MCPRetrieverError:
                if not self._config.allow_resource_fallback:
                    raise
                self._logger.log_event(
                    "retrieval_fallback",
                    query=query,
                    tool=self._config.retriever_tool,
                )
                chunks = await self._retriever.search_resources_async(query, top_k)

            if self._config.include_memory_in_rag:
                memories = await self._memory.retrieve(scope=scope, top_k=self._config.memory_top_k)

            memory_chunks = self._memory.to_chunks(memories)
            context = self._build_context(chunks, memory_chunks, self._config.context_token_budget)
            answer = await self._generate_answer(generator, query, context, chunks)

            citation_result: dict[str, Any] | None = None
            if self._config.citation_enabled and chunks:
                try:
                    citation_result = await self._citations.cite_async(answer, chunks, self._config.citation_format)
                except MCPCitationResolverError as exc:
                    self._logger.log_event(
                        "citation_skipped",
                        query=query,
                        reason=str(exc),
                    )

            if self._config.auto_store_turns:
                await self._memory.store(
                    f"Q: {query}\nA: {answer}",
                    scope=scope,
                    memory_type="conversation",
                    category="qa",
                )

            latency_ms = self._metrics.elapsed(start)
            self._metrics.record_answer(latency_ms)
            self._logger.log_event(
                "answer",
                query=query,
                chunks=len(chunks),
                memories=len(memories),
                citations=citation_result is not None,
                latency_ms=latency_ms,
            )
            return MCPRAGIntegrationResult(
                query=query,
                answer=answer,
                chunks=chunks,
                memories=memories,
                citation_result=citation_result,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            self._metrics.record_error()
            self._logger.log_event("answer_failed", query=query, error=str(exc))
            latency_ms = self._metrics.elapsed(start)
            return MCPRAGIntegrationResult(
                query=query,
                chunks=chunks,
                memories=memories,
                latency_ms=latency_ms,
                error=str(exc),
            )

    async def store_memory(
        self,
        content: str,
        scope: dict[str, str] | None = None,
        memory_type: str = "short_term",
        category: str = "general",
    ) -> dict[str, Any]:
        return await self._memory.store(content, scope=scope, memory_type=memory_type, category=category)

    async def retrieve_memories(
        self, query: str = "", scope: dict[str, str] | None = None, top_k: int = 5
    ) -> list[dict[str, Any]]:
        return await self._memory.search(query, scope=scope, top_k=top_k)

    async def delete_memory(self, item_id: str) -> bool:
        return await self._memory.delete(item_id)

    def get_metrics(self) -> dict[str, Any]:
        return self._metrics.get_metrics().to_dict()

    async def close(self) -> None:
        if hasattr(self._client, "disconnect"):
            await self._client.disconnect()
