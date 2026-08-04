# API — Examples

Ready-to-copy examples. `BASE=http://localhost:8000`, `KEY=test-key`.

## 1. Chat completion (OpenAI-routed)

```bash
curl $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d @examples/requests/openai.json
```

```json
{
  "model": "openai/gpt-4o-mini",
  "messages": [{"role": "user", "content": "Hi"}],
  "temperature": 0.3
}
```

## 2. Streaming (SSE)

```bash
curl -N $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model": "anthropic/claude-3.5-sonnet", "stream": true,
       "messages": [{"role":"user","content":"Count to 3"}]}'
```

## 3. RAG — ingest then search

```bash
# upload a document
curl -X POST $BASE/knowledge/documents/upload \
  -H "Authorization: Bearer $KEY" \
  -F "file=@examples/datasets/sample-knowledge.md"

# hybrid/semantic search
curl -s $BASE/vector/search \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d @examples/requests/vector-search.json
```

## 4. MCP tool call (SDK / streamable HTTP)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {"name": "calculator", "arguments": {"expression": "6*7"}}
}
```

## 5. Enable a plugin

```bash
curl -X POST "$BASE/plugins/enable?name=logging" \
  -H "Authorization: Bearer $KEY"
```

## 6. Admin & ops

```bash
GET  $BASE/version
GET  $BASE/health
GET  $BASE/metrics
GET  $BASE/stats/errors
POST $BASE/stats/reset
```

## Request files

All JSON bodies are in [`examples/requests/`](../../examples/requests/).
Postman and Insomnia collections are in `postman/` and `insomnia/`.