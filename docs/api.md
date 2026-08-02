# HTTP API

The AI Router gateway exposes a REST API. All endpoints return JSON.

## Endpoints

### `GET /health`
Liveness probe. Returns service health for load balancers and orchestrators.

### `GET /ready`
Readiness probe. Indicates whether the router can accept traffic.

### `GET /version`
Build metadata: version, build date, git commit, Python version.

### `POST /v1/chat`
Chat completions with automatic provider routing.

```json
{
  "model": "gpt-4o-mini",
  "messages": [{"role": "user", "content": "Hello"}],
  "temperature": 0.7
}
```

Response mirrors the provider's chat completion shape plus routing metadata
(`provider_used`, `latency_ms`).

### `POST /v1/embeddings`
Embedding generation with the same routing behavior.

## Error responses

All errors use a consistent shape:

```json
{
  "error": {"code": "PROVIDER_UNAVAILABLE", "message": "all providers failed"}
}
```

| Code | Meaning |
| --- | --- |
| `INVALID_REQUEST` | Malformed payload |
| `UNAUTHORIZED` | Missing/invalid API key |
| `PROVIDER_UNAVAILABLE` | No healthy provider available |
| `RATE_LIMITED` | Router or provider rate limit |
| `TIMEOUT` | Provider call exceeded timeout |

## Conventions

- JSON request/response bodies, `Content-Type: application/json`.
- Errors carry machine-readable `code` plus human `message`.
- Latency and provider are echoed in chat responses for observability.
