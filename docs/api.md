# HTTP API

The AI Router gateway exposes a REST API. All endpoints return JSON. The
interactive OpenAPI docs are available at `/docs` (Swagger UI) and `/redoc`.

## Endpoints

### `GET /health`
Liveness probe. Returns service status plus a per-provider summary.

### `GET /ready`
Readiness probe. Returns `200 {"status": "ok", ...}` only when the config has
been loaded and at least one provider is available (HEALTHY or DEGRADED);
returns `503 {"status": "unavailable", ...}` otherwise. Wire this to k8s
`readinessProbe` and load-balancer health checks.

### `GET /health/providers`
Per-provider health snapshot.

### `GET /health/providers/{provider_name}`
Health details for a single provider.

### `GET /version`
Build metadata: version, build date, git commit, Python version.

### `GET /metrics`
Prometheus metrics endpoint.

### `POST /v1/chat/completions`
OpenAI-compatible chat completions with automatic provider routing and
optional SSE streaming (`"stream": true`).

```json
{
  "model": "gpt-4o-mini",
  "messages": [{"role": "user", "content": "Hello"}],
  "temperature": 0.7
}
```

Response mirrors the provider's chat completion shape: `id`, `object`,
`created`, `model`, `choices` (with `message.content` / `delta.content` for
streaming) and `usage`. The chosen provider and timing are observable via the
`/stats` endpoints, `/logs`, and the `X-Request-ID` header (echoed back on
every response, matching `GET /logs/{request_id}`).

### `POST /v1/embeddings`
OpenAI-compatible embedding generation with the same routing behavior.

### `POST /v1/orchestrate` · `/v1/agents` · `/v1/workflow` · `/v1/consensus` · `/v1/debate`
Multi-agent orchestration endpoints (planner, agents, workflows, consensus,
debate).

### `GET /providers` · `/models` · `/models/{task}` · `/capabilities`
Provider and model discovery.

### `GET /stats` · `/logs` · `/costs` · `/tokens` · `/benchmark`
Observability: statistics, request logs, costs, token usage, benchmarks.

## Error responses

All errors use a consistent shape with an HTTP status code:

```json
{
  "error": "Provider call failed",
  "detail": {"code": "...", "message": "..."}
}
```

| HTTP | Condition |
| --- | --- |
| `400` | Malformed payload / validation failure |
| `401` | Missing or invalid API key |
| `403` | Valid key, insufficient scope |
| `404` | Unknown provider, model or task |
| `413` | Request body too large |
| `429` | Rate limit exceeded (includes `Retry-After` header) |
| `502` | All providers failed / upstream error |
| `503` | No healthy provider available |
| `504` | Provider timeout |
| `500` | Internal error (details never leak internals) |

Gateway-internal error codes use snake_case strings (e.g.
`rate_limit_exceeded`, `quota_exceeded`) attached to gateway exceptions.

## Conventions

- JSON request/response bodies, `Content-Type: application/json`.
- Errors carry a human-readable `error` plus `detail`.
- Every response echoes `X-Request-ID` for end-to-end traceability.
