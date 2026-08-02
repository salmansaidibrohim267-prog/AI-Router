# Observability

Metrics, logs, traces, SLOs and alerting for AI Router.

## Stack

| Component | Role |
| --- | --- |
| Prometheus | Metrics collection (30d retention) |
| Grafana | Dashboards (provisioned from `grafana/`) |
| Loki + Promtail | Log aggregation |
| OpenTelemetry Collector | Traces and metrics export |

## Metrics

Application metrics follow `ai_router_*` naming:

- `ai_router_requests_total` — request volume
- `ai_router_errors_total` — provider/error volume
- `ai_router_latency_seconds_bucket` — latency histogram
- `ai_router_success_total` — successful requests

The default Grafana dashboard renders request rate, error rate, p95 latency,
success ratio, memory and CPU (PromQL in `DashboardGenerator._default_panels`).

## SLOs and SLIs

`app/observability/slo.py`:

- `SloDefinition(name, target, window_seconds)` — e.g. 99.9% availability.
- `SliCollector` aggregates good/bad outcomes per SLO, rolls windows and caps
  history at 5000 points.
- Snapshots expose `success_ratio`, `error_rate`,
  `error_budget_remaining()` and `burn_rate()`.

```python
collector.record_good("api")
collector.record_bad("api")
collector.burn_rate("api")   # actual error rate / allowed error rate
```

## Alerting

`app/observability/alerts.py`:

- Rules use conditions (`burn_rate:api>0.5`) or custom evaluators.
- `BurnRateAlertBuilder` emits warning (burn ≥ 0.5×) and critical (≥ 2×) rules
  — budget-relative, per Google SRE practice.
- `for_seconds` suppresses noise until the condition persists.
- Handlers receive incidents; failures are swallowed, never crash the engine.

## Dashboards

`DashboardGenerator.generate("ai-router")` produces a Grafana dashboard JSON
with six panels; dashboards are provisioned from `grafana/dashboards`.

## Configuration (`OBS_*`)

| Variable | Default |
| --- | --- |
| `OBS_WINDOW_SECONDS` | `2592000` (30d) |
| `OBS_DEFAULT_SLO` | `99.9` |
| `OBS_BURN_ALERT_THRESHOLD` | `0.5` |
| `OBS_PAGE_THRESHOLD` | `2.0` |
| `OBS_ALERTS_ENABLED` | `true` |
| `OBS_METRICS_ENABLED` | `true` |
| `OBS_TRACES_ENABLED` | `true` |

## SLO example

99.9% over 30 days = 0.1% error budget. At 10 000 requests/day the budget is
~300 failures/month. A single 2× burn-rate hour pages on-call; sustained
0.5× burn warns.
