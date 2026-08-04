# API — Routing

The routing API lets clients pick models explicitly, or let the engine
classify and route automatically.

## Routes

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/v1/chat/completions` | OpenAI-compatible completions with routing |
| `POST` | `/v1/embeddings` | Embedding generation routed by provider |
| `GET` | `/models` | Available models |
| `GET` | `/models/{task}` | Models bound to a task |
| `GET` | `/providers` | Provider list + status |
| `GET` | `/providers/{name}/models` | Models for one provider |
| `GET` | `/distribution` | Traffic distribution configuration |
| `POST` | `/distribution/rebalance` | Rebalance weights |
| `POST` | `/distribution/config` | Update distribution |
| `GET` | `/capabilities` | Capability registry |
| `POST` | `/reload-config` | Reload YAML without restart |

## Explicit routing

```bash
curl $BASE/v1/chat/completions -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "openai/gpt-4o-mini", "messages": [{"role":"user","content":"hi"}]}'
```

Fully-qualified model names are `<provider>/<model>`.

## Automatic routing

Omit the model and the classifier picks a task, which selects a default
model (see `config/models.yaml`):

```bash
curl $BASE/v1/chat/completions -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role":"user","content":"hi"}]}'
```

## Traffic distribution

`GET /distribution` and `POST /distribution/rebalance` adjust how load is
spread across healthy providers. Weighted distribution, failure failover,
and circuit breakers are part of the routing engine
(`app/router.py`, `app/routing.py`).

## Streaming

Include `"stream": true` for SSE:

```bash
curl -N $BASE/v1/chat/completions -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d @examples/requests/stream.json
```

See [`examples.md`](examples.md) for full payloads.