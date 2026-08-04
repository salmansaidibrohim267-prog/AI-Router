# Sample Requests & Responses

Ready-to-use request bodies and expected responses for the main endpoints.
Copy the JSON files into Postman, Insomnia, or any HTTP client.

| File | Endpoint | Purpose |
| --- | --- | --- |
| `chat.json` | `POST /v1/chat/completions` | Standard chat completion |
| `openai.json` | `POST /v1/chat/completions` | OpenAI-routed request |
| `anthropic.json` | `POST /v1/chat/completions` | Anthropic-routed request |
| `ollama.json` | `POST /v1/chat/completions` | Local Ollama-routed request |
| `stream.json` | `POST /v1/chat/completions` | SSE streaming chat |
| `rag-upload.sh` | `POST /knowledge/documents/upload` | Ingest a document (multipart) |
| `vector-search.json` | `POST /vector/search` | Vector search (RAG retrieval) |
| `mcp.json` | MCP streamable-HTTP transport | JSON-RPC `tools/call` (MCP SDK) |
| `plugin.json` | `POST /plugins/enable` | Enable a plugin by name (`name=` param) |
| `plugin-toggle.json` | `POST /plugins/enable` | Toggle a plugin |
| `responses.md` | — | Expected response shapes |

All requests use `{{baseUrl}}` (`http://localhost:8000`) and the bearer
token `{{apiKey}}` (default `test-key`). See `postman/environment.json`.

## Quick start with curl

```bash
BASE=http://localhost:8000 KEY=test-key
curl -s $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d @examples/requests/chat.json
```

Sample responses for each request are documented in `responses.md`
(provider-dependent values are marked).
