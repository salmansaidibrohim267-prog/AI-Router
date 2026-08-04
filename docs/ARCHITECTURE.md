# Architecture

> Deep dive: [`docs/architecture/architecture.md`](architecture/architecture.md)

AI Router is a modular, layered AI gateway. A single HTTP surface
(`app/api.py`, FastAPI) exposes routing, RAG, MCP, plugins, billing, admin
and observability while the core stays provider-agnostic.

## High-level layers

| Layer | Modules | Responsibility |
| --- | --- | --- |
| **API / Gateway** | `app/api.py`, `app/gateway/` | HTTP surface, auth, rate limiting, middleware |
| **Routing** | `app/router.py`, `app/routing.py`, `app/classifier.py` | Task classification, provider scoring, traffic distribution, failover |
| **AI Services** | `app/rag/`, `app/knowledge/`, `app/reranker/`, `app/retrieval/`, `app/mcp/` | RAG pipeline, knowledge base, vector search, MCP SDK |
| **Providers** | `app/providers/` | OpenAI, Anthropic, Google, Ollama, OpenRouter clients |
| **Platform** | `app/security/`, `app/billing/`, `app/tenancy/`, `app/admin/` | Security, billing, multi-tenancy, administration |
| **Distributed** | `app/distributed/`, `app/tasks/`, `app/scheduler.py` | Worker pool, leader election, queues, scheduling |
| **Observability** | `app/observability/`, `app/metrics.py`, `app/stats.py` | Metrics, SLOs, audit logging, telemetry |

## Request flow (simplified)

```text
Client
  │  POST /v1/chat/completions
  ▼
API layer ── auth ── rate limit ── tenancy ── audit
  │
  ▼
Classifier ──→ Routing engine ──→ Provider A (OpenAI)
                     │              Provider B (Anthropic)   ← health checks,
                     │              Provider C (Ollama)        circuit breakers,
                     ▼                                       fallback & failover
               Response selection & stream passthrough
```

## Design principles

- **Provider-agnostic core** — every provider is a client adapter behind a
  common interface; adding one is configuration, not code.
- **Everything is pluggable** — plugins (`app/plugin/`) hook into the request
  lifecycle without touching core code.
- **Failover by default** — health checks, circuit breakers and retry/backoff
  are built into the routing engine.
- **Observable by design** — every subsystem emits metrics and audit events;
  SLOs and error budgets are first-class (`docs/observability.md`).
- **Testable** — each subsystem ships with injectable transports/clients and
  a focused test suite (97%+ coverage).

## Sequence diagrams

- [Sequence diagrams](architecture/sequence.md)
- [Component breakdown](architecture/components.md)
- [Folder structure](architecture/folder-structure.md)
