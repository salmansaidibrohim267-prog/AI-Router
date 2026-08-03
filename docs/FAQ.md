# FAQ

Frequently asked questions. Short answers; full context lives in the linked
guides and in the README's FAQ section.

## General

**What is AI Router?**
An open-source gateway that routes requests to the best LLM provider/model,
with RAG, MCP, plugins, security, and observability built in. See the
[README](../README.md).

**Which providers are supported?**
OpenAI, Anthropic (Claude), Google (Gemini), Ollama, OpenRouter, Mistral,
Groq, Azure. Direct clients are in `examples/providers/`.

**Is it free?**
MIT-licensed open source. You pay only your own provider API costs.

## Setup

**The gateway starts but `/ready` returns 503.**
No healthy provider. Set a real provider key (`.env` or environment
variable), confirm `config/providers.yaml`, then `POST /reload-config`.

**What is the default API key?**
The demo default is `test-key`; change it for anything public. Auth is
documented in `docs/security.md`.

**Do I need Redis?**
No — only for the distributed profile (`DISTRIBUTED_MODE=1`).

## API

**Is it OpenAI-compatible?**
`/v1/chat/completions` is OpenAI-compatible, including SSE streaming.
See `docs/api.md`.

**How do I find which provider served my request?**
Look up the `X-Request-ID` header: `GET /logs/{request_id}`.

**What error shape does the API use?**
`{"error": ..., "detail": ...}` with standard HTTP status codes
(400/401/403/404/413/429/502/503/504/500).

## Routing

**How does routing decide?**
Scoring across capability match, cost, latency, reliability, and load, with
per-optimization weights. See the README's routing section and
`docs/architecture.md`.

**What happens when a provider fails?**
Circuit breaker opens (default after 5 failures), retries with jitter apply,
and fallback routes to the next provider. `GET /health/providers` shows state.

## RAG / Knowledge

**Where are documents stored?**
Default backend is local; production options include Chroma and other
supported vector backends (`KNOWLEDGE_STORAGE_BACKEND`).

**How do I ingest a document?**
`POST /knowledge/documents/upload` (multipart) or the import endpoint.
See `demo/API_EXAMPLES.md`.

## Deployment

**Docker, Kubernetes, or Helm?**
All supported. See `docs/deployment.md` and `deployment/`.

**Can it scale horizontally?**
Yes — the distributed profile adds Redis-backed workers and scheduling.
See the README deployment section.

## Security

**How are API keys stored?**
Via the secret store with AES-256-GCM envelope encryption; adapters for
env, Vault, Kubernetes, and cloud KMS. See `docs/security.md`.

**Where do I report a vulnerability?**
Privately via GitHub Security Advisory or the email in [SECURITY.md](../SECURITY.md).

## Contributing

**How do I contribute?**
See [CONTRIBUTING.md](../CONTRIBUTING.md) and `docs/contributing.md`.

**Do examples exist?**
Yes — `examples/` covers simple chat, RAG, providers, plugins, and MCP.
