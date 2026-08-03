# Expected Responses

Verified response shapes for the sample requests. Values marked
`<provider-dependent>` vary by provider/model/state.

## `POST /v1/chat/completions` (chat.json)

```json
{
  "id": "<request id>",
  "object": "chat.completion",
  "created": 1770000000,
  "model": "<provider>/<model>",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "<provider-dependent>"},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 12, "completion_tokens": 18, "total_tokens": 30}
}
```

Every response carries the `X-Request-ID` header — use it with
`GET /logs/{request_id}`.

## `POST /v1/chat/completions` (stream.json, SSE)

```
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"An AI"},"finish_reason":null}]}
...
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

## `POST /knowledge/documents/upload` (rag-upload.sh)

```json
{
  "document_id": "<uuid>",
  "status": "processing",
  "chunks": "<provider-dependent>"
}
```

Check progress with `GET /knowledge/documents/{document_id}` and summary
with `GET /knowledge/statistics`.

## `POST /vector/search` (vector-search.json)

```json
{
  "results": [
    {"chunk_id": "<uuid>", "score": 0.87, "content": "...", "source": "...", "metadata": {}}
  ],
  "total": 1
}
```

## `POST /plugins/enable` (plugin-toggle.json)

```json
{
  "plugin": "logging",
  "enabled": true
}
```

Confirm with `GET /plugins`.

## Error shape

All errors use `{"error": "...", "detail": "..."}` with standard HTTP status
codes (400, 401, 403, 404, 413, 429, 502, 503, 504, 500).
