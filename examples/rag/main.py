"""RAG — retrieval-augmented generation with citations and confidence scoring.

Run from the repository root:

    PYTHONPATH=. python examples/rag/main.py
"""

import asyncio
import os

from app.rag.config import RAGConfig
from app.rag.models import RAGRequest
from app.rag.pipeline import RAGPipeline

QUERY = os.getenv("RAG_QUERY", "What does the AI Router do?")


async def main() -> None:
    config = RAGConfig.from_env()
    pipeline = RAGPipeline(config=config)

    request = RAGRequest(
        query=QUERY,
        retrieval_top_k=config.retrieval_top_k,
        rerank_top_k=config.rerank_top_k,
    )

    response = await pipeline.generate(request)

    print(f"answer: {response.answer}\n")
    print(f"provider: {response.provider}  model: {response.model}")
    print(f"confidence: {response.confidence:.2f}  cache_hit: {response.cache_hit}")
    print(f"retrieval: {response.retrieval_latency_ms:.1f}ms  "
          f"llm: {response.llm_latency_ms:.1f}ms  total: {response.total_latency_ms:.1f}ms")
    print(f"tokens: {response.token_usage}")

    if response.context and response.context.chunks:
        print(f"\n{len(response.context.chunks)} context chunks used")
    for source in response.sources[:3]:
        print(f"source: {source.get('chunk_id')}  from: {source.get('source', 'n/a')}  "
              f"score={source.get('score', 'n/a')}")

    if response.fallback_used:
        print("\nnote: fallback strategy was applied (low confidence or provider issue)")


if __name__ == "__main__":
    asyncio.run(main())
