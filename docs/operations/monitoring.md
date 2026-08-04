# Operations — Monitoring

AI Router exposes Prometheus metrics, structured logs, SLO/error-budget
alerting and OpenTelemetry tracing.

## Endpoints

| Endpoint | Content |
| --- | --- |
| `GET /metrics` | Prometheus metrics |
| `GET /health` | Liveness + provider health |
| `GET /ready` | Readiness (config loaded, provider available) |
| `GET /stats` | Request/error/latency statistics |
| `GET /stats/providers` | Per-provider stats |
| `GET /runtime/events` | Runtime event stream |
| `GET /version` | Build metadata |

## Stack (docker-compose `production` profile)

- **Prometheus** — scrape `/metrics` (`prometheus/prometheus.yml`)
- **Grafana** — dashboards (`grafana/dashboards/`)
- **Loki + Promtail** — log aggregation (`loki/`, `promtail/`)
- **OpenTelemetry Collector** — traces (`otel/`)

```bash
docker compose --profile production up -d
```

Dashboards: overview, providers, latency, errors, tokens, SLOs.

## SLOs & alerting

`app/observability/` computes SLOs, error budgets and burn-rate alerts from
request metrics. Alert rules reference `prometheus/` alert definitions.

## OpenTelemetry

```bash
OTEL_ENABLED=1
OTEL_EXPORTER_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_SERVICE_NAME=ai-router
```

## Key metrics (conceptual)

- `requests_total`, `requests_duration_seconds`
- `errors_total` (by provider/status)
- `tokens_total` (input/output)
- `provider_health`, `circuit_breaker_state`
- `queue_depth`, `worker_utilization`

See [`docs/observability.md`](../observability.md) for the deep dive.