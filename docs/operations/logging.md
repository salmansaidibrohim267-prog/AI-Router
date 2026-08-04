# Operations — Logging

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `LOG_FORMAT` | JSON | Structured output |
| `LOGS_DIR` | `./logs` | Local file location |

In containers, mount `./logs:/app/logs` (json-file driver, 10m rotation).

## Features

- **Structured JSON logs** via `app/logger.py`
- **Secret masking** — keys, tokens, passwords sanitized by
  `SENSITIVE_FIELDS`
- **Audit trail** — security events logged immutably (`app/security/`)
- **Distributed correlation** — request IDs across worker/job lifecycle

## Centralized logs (Loki)

With the `production` profile, Promtail tails `/app/logs` into Loki:

```bash
docker compose --profile production up -d promtail loki
# query in Grafana Explore → datasource Loki → {job="promtail"}
```

## Manual

```bash
docker compose logs -f ai-router
docker compose logs --tail=200 ai-router
```

## Best practice

- Never log API keys; rely on built-in masking
- Keep `LOG_LEVEL=debug` short-lived for investigations
- Grep for `"level":"error"` (JSON) before contacting support

See [`docs/observability.md`](../observability.md) for SLO/tracing details.