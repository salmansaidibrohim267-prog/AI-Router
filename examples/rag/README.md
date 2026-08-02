# RAG

Retrieval-augmented generation: the `RAGPipeline` handles query analysis,
retrieval, reranking, context assembly, citation scoring and fallback.

> Document ingestion happens through the gateway API
> (`POST /v1/knowledge/ingest`). This example runs the retrieval + generation
> side of the pipeline directly from Python.

## Run

```bash
# from the repository root
PYTHONPATH=. python examples/rag/main.py
```

Set `RAG_QUERY` (see `.env.example`) and make sure the configured
`RAG_LLM_PROVIDER` API key is available (e.g. `OPENAI_API_KEY`).

## Expected output

```
answer: AI Router is a gateway and orchestration platform that routes every
request to the best model, provider and infrastructure...

provider: openai  model: gpt-4o-mini
confidence: 0.94  cache_hit: False
retrieval: 42.1ms  llm: 812.3ms  total: 860.5ms
tokens: {'prompt_tokens': 412, 'completion_tokens': 89, 'total_tokens': 501}

3 context chunks used
source: 3f2a...  from: docs/architecture.md  score=0.87
```
