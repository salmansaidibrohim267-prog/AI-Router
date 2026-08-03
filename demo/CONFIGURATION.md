# Demo — Configuration

The demo reads configuration from `config/` (checked into the repository)
plus environment overrides in `.env`. No application changes are required.

## Providers

`config/providers.yaml` defines the provider registry with priorities:

| Provider | Priority | Key (env) |
| --- | --- | --- |
| OpenRouter | 10 | `OPENROUTER_API_KEY` |
| Ollama (local) | 20 | none |
| OpenAI | 30 | `OPENAI_API_KEY` |
| Anthropic | 40 | `ANTHROPIC_API_KEY` |
| Google | 50 | `GOOGLE_API_KEY` |
| Mistral | 60 | `MISTRAL_API_KEY` |

The demo works with any single provider key. Example for the demo `.env`:

```bash
OPENROUTER_API_KEY=sk-or-...      # one is enough
```

## Models

`config/models.yaml` and `config/models_registry.yaml` register model
aliases and capabilities. The default demo model is `gpt-4o-mini`
(fallback: `llama3.2` via Ollama).

## Plugins

`config/plugins.yaml` + `plugins/<name>/` (each with `plugin.py` and
`manifest.yaml`). The `guardrails`, `logging`, `cache` and `translation`
plugins ship in the repository and are auto-discovered at startup.
Enable/disable at runtime:

```bash
curl -X POST http://localhost:8000/plugins/enable -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d '{"plugin": "logging"}'
```

## RAG / Knowledge

RAG defaults come from `app/rag/config.py` and can be overridden via
`RAG_*` environment variables (see `ENVIRONMENT.md`). The default vector
storage is in-process; production deployments configure a persistent
backend.

## Reconfiguring at runtime

```bash
curl -X POST http://localhost:8000/reload-config -H "Authorization: Bearer $KEY"
```

Reloads providers, models, plugins and distribution configuration without a
restart. Check `GET /config` to confirm the applied state.
