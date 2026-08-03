from __future__ import annotations

from typing import Any

from app.rag.config import RAGConfig
from app.rag.exceptions import RAGRetrievalError
from app.rag.models import RetrievedChunk
from app.reranker.models import RerankerInput


class RetrievalOrchestrator:
    def __init__(
        self,
        config: RAGConfig | None = None,
        hybrid_retriever: Any | None = None,
        reranker: Any | None = None,
    ):
        self._config = config or RAGConfig()
        self._hybrid = hybrid_retriever
        self._reranker = reranker

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        rerank_top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        top_k = top_k or self._config.retrieval_top_k
        rerank_top_k = rerank_top_k or self._config.rerank_top_k

        if self._hybrid is None:
            raise RAGRetrievalError("Hybrid retriever not configured")

        try:
            results = await self._hybrid.search_async(
                query=query,
                top_k=top_k,
            )
        except Exception as e:
            raise RAGRetrievalError(f"Hybrid search failed: {e}") from e

        if not results:
            return []

        chunks = [
            RetrievedChunk(
                chunk_id=str(r.id),
                content=r.content,
                score=r.score,
                source=r.metadata.get("source", ""),
                metadata=r.metadata,
            )
            for r in results
        ]

        if self._reranker and rerank_top_k > 0:
            try:
                reranker_input = RerankerInput(
                    query=query,
                    candidates=[{"id": c.chunk_id, "content": c.content, "score": c.score} for c in chunks],
                )
                reranked = await self._reranker.rerank_async(reranker_input)
                seen_ids: set[str] = set()
                final_chunks: list[RetrievedChunk] = []
                for r in reranked.results:
                    if r.id not in seen_ids:
                        seen_ids.add(r.id)
                        final_chunks.append(
                            RetrievedChunk(
                                chunk_id=r.id,
                                content=r.content,
                                score=r.score,
                                rerank_score=r.score,
                                source="",
                                metadata={},
                            )
                        )
                chunk_map = {c.chunk_id: c for c in chunks}
                for c in final_chunks:
                    if c.chunk_id in chunk_map:
                        orig = chunk_map[c.chunk_id]
                        c.content = orig.content
                        c.score = orig.score
                        c.source = orig.source
                        c.metadata = orig.metadata
                chunks = final_chunks
            except Exception:
                pass

        return chunks[:rerank_top_k]

    async def retrieve_sync_fallback(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        if self._hybrid is None:
            raise RAGRetrievalError("Hybrid retriever not configured")
        try:
            results = self._hybrid.search(
                query=query,
                top_k=top_k,
            )
        except Exception as e:
            raise RAGRetrievalError(f"Sync hybrid search failed: {e}") from e
        return [
            RetrievedChunk(
                chunk_id=str(r.id),
                content=r.content,
                score=r.score,
                source=r.metadata.get("source", ""),
                metadata=r.metadata,
            )
            for r in results
        ]
