# Configuration

AI Router is configured through YAML files in `config/` and environment
variables. Configuration is loaded once at startup and can be hot-reloaded
via `POST /reload-config`.

## Configuration files

| File | Purpose |
| --- | --- |
| `config/providers.yaml` | Provider connections, keys, models, priorities |
| `config/models.yaml` | Task → model defaults and supported tasks |
| `config/models_registry.yaml` | Model registry entries (capabilities, pricing) |
| `config/orchestrator.yaml` | Multi-agent orchestration settings |
| `config/plugins.yaml` | Plugin enablement and settings |

Mount the directory read-only in containers:

```yaml
volumes:
  - ./config:/app/config:ro
```

Set `CONFIG_DIR` to override the location (default `/app/config`).

## Environment variables

The complete reference lives in `.env.example`. The most important groups:

### Providers

| Variable | Description |
| --- | --- |
| `OPENROUTER_API_KEY` | OpenRouter key |
| `OPENAI_API_KEY` | OpenAI key |
| `ANTHROPIC_API_KEY` | Anthropic key |
| `GOOGLE_API_KEY` | Google / Gemini key |
| `MISTRAL_API_KEY` / `GROQ_API_KEY` | Mistral / Groq keys |

### Server

| Variable | Default | Description |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `info` | Log level |
| `ALLOWED_HOSTS` | `*` | Host allow-list |
| `CORS_ORIGINS` | `*` | CORS allow-list |
| `MAX_REQUEST_SIZE_BYTES` | `10485760` | Max request size |

### Rate limiting

| Variable | Default | Description |
| --- | --- | --- |
| `RATE_LIMIT_REQUESTS` | `100` | Max requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Window in seconds |

### Distributed mode

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_URL` | — | Redis connection string |
| `DISTRIBUTED_MODE` | `0` | Set to `1` to enable worker pool |
| `WORKER_COUNT` | `2` | Worker processes |
| `WORKER_CONCURRENCY` | `5` | Concurrent jobs per worker |
| `SCHEDULER_MODE` | `0` | Enable scheduler |
| `EVENT_BUS_ENABLED` | `1` | Event bus |

### Knowledge / RAG

`KNOWLEDGE_*`, `CHUNK_*`, `EMBEDDING_*`, `VECTOR_*`, `RERANKER_*` groups
configure the RAG pipeline (see `.env.example` for the full list).

### Observability

| Variable | Default | Description |
| --- | --- | --- |
| `OTEL_ENABLED` | `0` | OpenTelemetry tracing |
| `OTEL_EXPORTER_ENDPOINT` | — | Collector endpoint |
| `OTEL_SERVICE_NAME` | `ai-router` | Trace service name |

## Secrets

API keys can come from:

1. Environment variables (recommended for containers)
2. Docker secrets (`/run/secrets/<NAME>`)
3. The secret store backend (`app/security/secrets.py`): Vault, Kubernetes,
   AWS, Azure or GCP — see `docs/security.md`

## Hot reload

After editing any file in `config/`:

```bash
curl -X POST http://localhost:8000/reload-config
```

`GET /config` returns the active configuration (masked).
