# API — Providers

Provider-facing API surface: health, capabilities, models and custom
providers.

## Provider health

```bash
curl $BASE/health/providers                    # all providers snapshot
curl $BASE/health/providers/openai             # single provider detail
```

Health statuses: `healthy`, `degraded`, `unhealthy`. Used by the routing
engine for failover.

## Capabilities

```bash
GET /capabilities                       # all
GET /capabilities/{provider_name}       # one provider
GET /capabilities/{provider_name}/{model}
```

## Models

```bash
GET /models                 # all available models (auto-generated)
GET /models/{task}          # models for a task
GET /providers/{name}/models
```

## Custom providers

Register a custom provider at runtime:

```bash
POST /providers/custom
{
  "name": "my-llm",
  "base_url": "https://llm.example.com/v1",
  "api_key_env": "MY_LLM_KEY",
  "models": ["my-llm/chat"]
}
```

## Provider configuration

Persistent provider config lives in `config/providers.yaml`. Reload without
restart:

```bash
POST /reload-config
```

Each provider supports model lists, keys, timeouts, retries, `enabled`,
and `priority`. Full reference: [`../PROVIDERS.md`](../PROVIDERS.md).