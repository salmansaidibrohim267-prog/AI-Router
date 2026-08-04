# Providers

AI Router ships with adapters for the most common LLM providers. Providers
are configured declaratively in `config/providers.yaml` and can be enabled,
weighted and health-checked at runtime without code changes.

## Supported providers

| Provider | Default base URL | Auth | Enabled by default |
| --- | --- | --- | --- |
| **OpenRouter** | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | ✅ |
| **Ollama** (local) | `http://localhost:11434` | none | ✅ |
| **OpenAI** | `https://api.openai.com/v1` | `OPENAI_API_KEY` | (enable in YAML) |
| **Anthropic** | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | (enable in YAML) |
| **Google / Gemini** | `https://generativelanguage.googleapis.com` | `GOOGLE_API_KEY` | (enable in YAML) |
| **Mistral** | `https://api.mistral.ai` | `MISTRAL_API_KEY` | (enable in YAML) |
| **Groq** | `https://api.groq.com` | `GROQ_API_KEY` | (enable in YAML) |

Custom providers can be added through `POST /providers/custom`.

## Configuration reference

Each entry in `config/providers.yaml` supports:

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | Unique provider id used in model names (`<name>/<model>`) |
| `display_name` | string | Human-readable name |
| `api_key_env` | string | Env var holding the API key (`null` for no auth) |
| `base_url` | string | Provider endpoint |
| `timeout` | float | Request timeout in seconds |
| `max_retries` | int | Retry attempts before failing |
| `enabled` | bool | Whether routing may select this provider |
| `priority` | int | Lower = preferred when scoring is equal |
| `models` | list | Available model identifiers for this provider |

```yaml
providers:
  - name: openai
    display_name: "OpenAI"
    api_key_env: "OPENAI_API_KEY"
    base_url: "https://api.openai.com/v1"
    timeout: 60.0
    max_retries: 3
    enabled: true
    priority: 30
    models:
      - "gpt-4o"
      - "gpt-4o-mini"
```

## Model naming

A request always targets a fully-qualified model: `<provider>/<model>`.

```text
openai/gpt-4o-mini          ollama/llama3.1:8b
anthropic/claude-3.5-sonnet google/gemini-2.5-pro
```

`GET /models` lists available models and `GET /models/{task}` returns the
models bound to a task (see `config/models.yaml`).

## Task-based defaults

`config/models.yaml` maps tasks to default models:

| Task | Default model |
| --- | --- |
| `chat` | `google/gemini-2.5-flash-lite` |
| `coding` | `anthropic/claude-sonnet-4` |
| `architecture` | `openai/gpt-5.5` |
| `analysis` | `google/gemini-2.5-pro` |

## Routing & failover

Providers are selected by the routing engine based on task match, health,
priority and cost. When a provider fails, the router falls back to the next
healthy candidate automatically.

See [`docs/api/providers.md`](api/providers.md) for the provider API
reference and `docs/architecture/sequence.md` for the failover flow.