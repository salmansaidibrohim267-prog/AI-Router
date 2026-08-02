# Architecture

AI Router is a production-ready AI gateway: it fronts multiple LLM providers,
routes requests intelligently, tracks usage, enforces security, and ships with
a complete deployment and observability stack.

## High-level view

```
                        ┌────────────────────────────┐
   Clients ──► HTTP ──► │  API layer (FastAPI)        │
                        │  /v1/chat, /v1/embeddings   │
                        └────────────┬───────────────┘
                                     │
                        ┌────────────▼───────────────┐
                        │  Router & policies          │
                        │  traffic distribution       │
                        │  fallback / failover        │
                        └────────────┬───────────────┘
                                     │
        ┌───────────────┬────────────┴──────┬────────────────┐
        ▼               ▼                   ▼                ▼
   OpenAI / Anthropic / Google / OpenRouter / Ollama / local models
```

## Subsystems

| Package | Responsibility |
| --- | --- |
| `app/` core | Routing, scoring, traffic distribution, fallback, caching |
| `app/security/` | Encryption (AESGCM, KMS/HSM), audit chain, secret store, signing |
| `app/release/` | SemVer, RCs, changelog, HMAC signing, GitHub/registry publishing |
| `app/migrations/` | Versioned schema migrations (memory/SQLite), rollback, dry-run |
| `app/observability/` | SLO/SLI tracking, error budgets, burn rates, alert rules, Grafana dashboards |
| `app/deploy/` | Quality gates, smoke tests, rollback tests, verification, GitOps validation |
| `benchmarks/suites/` | Throughput, latency, memory, CPU, concurrency, failover, RAG quality |

## Data flow

1. **Ingress** — Traefik terminates TLS and rate-limits.
2. **Routing** — the router scores providers by health, latency, cost and
   policy; `traffic_distribution` applies weighted routing and failover.
3. **Execution** — provider calls run with timeouts and retries; fallbacks
   engage on provider failure.
4. **Observability** — Prometheus metrics, Loki logs, OpenTelemetry traces;
   SLIs feed SLOs and burn-rate alerts.
5. **Release** — CI derives the next version, generates the changelog, signs
   the artifact manifest and publishes to GitHub/registry; ArgoCD rolls it out.

## Design principles

- **Twelve-factor** — config from environment, stateless processes, logs to
  stdout, disposability.
- **Immutable infrastructure** — pinned image tags (`v1.0.0-rc.1`), never
  `latest` in production.
- **Fail-safe** — quality gates block bad releases; smoke, rollback and
  verification tests run before traffic is accepted; GitOps self-heals drift.
- **Signed releases** — artifact manifests are HMAC-SHA256 signed; verifiers
  reject tampered payloads.
- **SLO-driven alerting** — alerts fire on burn rate, not raw thresholds.
