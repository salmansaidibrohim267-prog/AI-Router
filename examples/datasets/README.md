# Sample Datasets

Small, self-contained datasets for exercising the knowledge/RAG and vector
endpoints without external data.

| File | Purpose |
| --- | --- |
| `sample-knowledge.md` | A short, factual document about AI Router itself — ideal for `POST /knowledge/documents/upload` and retrieval demos |

## Usage

```bash
# Ingest the sample document
curl -s -X POST http://localhost:8000/knowledge/documents/upload \
  -H "Authorization: Bearer test-key" \
  -F "file=@sample-knowledge.md" | python3 -m json.tool

# Query it
curl -s -X POST http://localhost:8000/vector/search \
  -H "Authorization: Bearer test-key" -H "Content-Type: application/json" \
  -d '{"collection": "default", "query": "circuit breaker", "top_k": 3}'
```

The document stays in sync with the product; regenerate or extend it when
the product changes.
