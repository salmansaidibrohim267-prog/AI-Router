# Sample Requests & Responses

Ready-to-use request bodies and expected responses for the main endpoints.
Copy the JSON files into Postman, Insomnia, or any HTTP client.

| File | Endpoint | Purpose |
| --- | --- | --- |
| `chat.json` | `POST /v1/chat/completions` | Standard chat completion |
| `stream.json` | `POST /v1/chat/completions` | SSE streaming chat |
| `rag-upload.sh` | `POST /knowledge/documents/upload` | Ingest a document (multipart) |
| `vector-search.json` | `POST /vector/search` | Vector search |
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
