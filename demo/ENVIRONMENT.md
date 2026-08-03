# Demo — Environment Variables

Environment variables read by the application (verified against the code).
All values shown are the demo defaults.

## Provider credentials (at least one required)

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | — | OpenRouter routing (priority 10) |
| `OPENAI_API_KEY` | — | OpenAI provider |
| `ANTHROPIC_API_KEY` | — | Anthropic provider |
| `GOOGLE_API_KEY` | — | Google provider |
| `MISTRAL_API_KEY` | — | Mistral provider |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama |

## Gateway

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |
| `MAX_REQUEST_SIZE_BYTES` | (default) | Request size limit |
| `REDIS_URL` | — | Redis URL for distributed mode |
| `DISTRIBUTED_MODE` | `0` | Enable distributed workers (`1`) |

## Security

| Variable | Default | Purpose |
| --- | --- | --- |
| `SEC_ZERO_TRUST_ENFORCE` | `0` | Zero-trust enforcement mode |
| `SEC_AUDIT_ENABLED` | `1` | HMAC audit chain |
| `SEC_AUDIT_RETENTION_DAYS` | `365` | Audit retention |

## RAG / Knowledge

| Variable | Default | Purpose |
| --- | --- | --- |
| `RAG_LLM_PROVIDER` | `openai` | RAG generation provider |
| `RAG_LLM_MODEL` | `gpt-4o-mini` | RAG generation model |
| `RAG_RETRIEVAL_TOP_K` | `10` | Retrieve top-K |
| `RAG_RERANK_TOP_K` | `5` | Rerank top-K |
| `RAG_CONTEXT_TOKEN_BUDGET` | `2048` | Context budget |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `200` | Ingestion chunking |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | (default) | Embedding source |
| `KNOWLEDGE_STORAGE_BACKEND` | (default) | Vector store backend |
| `KNOWLEDGE_DATABASE_PATH` | (default) | Local knowledge DB path |

## MCP

| Variable | Default | Purpose |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio` | Transport: `stdio`/`http`/`sse`/`websocket` |
| `MCP_URL` | — | MCP server URL for HTTP transports |
| `MCP_AUTH_TYPE` | `none` | `none`/`bearer`/`api-key`/`oauth2` |
| `MCP_BEARER_TOKEN` | — | Bearer token for authenticated servers |

## Observability

| Variable | Default | Purpose |
| --- | --- | --- |
| `OTEL_ENABLED` | `0` | OpenTelemetry export |
| `OTEL_EXPORTER_ENDPOINT` | — | OTLP collector endpoint |
| `OTEL_SERVICE_NAME` | `ai-router` | Service name in traces |

## Release tooling (REL_*) / Migrations (MIG_*) / Deploy (DEP_*)

Used by the release, migration and deploy subsystems. Demo deployments do
not need to change them; see `docs/` for each subsystem.

## .env.example

The repository `.env.example` mirrors the variables above. Copy it with
`cp .env.example .env`, fill in one provider key, and start the demo.
