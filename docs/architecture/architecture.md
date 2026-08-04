# Architecture

AI Router is a layered, event-driven AI gateway. This document describes the
core subsystems, their responsibilities, and how they compose into a single
runnable `python -m app.main` process.

## Subsystems at a glance

```text
                         ┌────────────────────────────┐
                         │   API & Gateway (FastAPI)  │
                         │  auth · tenancy · rate     │
                         │  limit · middleware · audit│
                         └────────────┬───────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
      ┌───────────────┐      ┌────────────────┐      ┌────────────────┐
      │  Classifier   │      │  Routing Engine│      │  Plugin Layer  │
      │  task → model │      │  provider      │      │  request/      │
      │               │      │  scoring, da,  │      │  response hooks│
      │               │      │  failover      │      │  lifecycle     │
      └──────┬────────┘      └───┬────────────┘      └───────┬────────┘
             │                   │                           │
             ▼                   ▼                           ▼
      ┌───────────────────────────────────────────────────────────────┐
      │                     Provider Adapters                         │
      │  OpenAI · Anthropic · Google · Ollama · OpenRouter · Mistral  │
      └───────────────────────────────────────────────────────────────┘
```

Layered below the request path sit the supporting subsystems:

- **RAG stack** (`app/knowledge/`, `app/rag/`, `app/retrieval/`,
  `app/reranker/`): ingestion, chunking, embedding, vector store, hybrid
  search, reranking and citation generation.
- **MCP** (`app/mcp/`): Model Context Protocol client SDK with discovery,
  sessions, transports and tool-call routing.
- **Distributed runtime** (`app/distributed/`, `app/tasks/`,
  `app/scheduler.py`, `app/worker.py`): worker pool, leader election,
  queueing and scheduling over Redis.
- **Platform services** (`app/security/`, `app/billing/`, `app/tenancy/`,
  `app/admin/`): auth, secret management, KMS/HSM, metering, tenants,
  admin console and compliance.
- **Observability** (`app/metrics.py`, `app/stats.py`, `app/observability/`):
  metrics, events, SLOs, burn-rate alerting and distributed tracing.

## Request lifecycle

```text
1. HTTP request → API layer
2. Middleware: authentication → tenancy resolution → rate limiting → audit
3. Route dispatch to /v1/chat/completions (or agents, embeddings, RAG, …)
4. Classifier resolves task type if not explicit
5. Routing engine:
   a. filter enabled + healthy providers
   b. score by task match, priority, cost, reputation
   c. select primary provider
   d. on failure → circuit breaker → fallback candidate → retry/backoff
6. Plugin hooks run (pre-request / post-request)
7. Provider adapter executes the call (non-streaming or SSE stream)
8. Response normalized, metered (billing), logged (audit), emitted (metrics)
9. Streaming responses pass through with token-level metrics
```

## Key design principles

- **Single surface, many providers** — client code never imports an SDK.
- **Adapters behind interfaces** — providers, vector stores, secret stores
  and vaults are swappable implementations.
- **Graceful degradation** — missing keys, unhealthy providers and rate
  limits degrade one request, never the gateway.
- **Everything plugged in** — plugins sit between routing and providers.
- **Designed for failure** — health checks, circuit breakers, retries,
  DLQs and leader failover are default behaviors.

## References

- [Sequence diagrams](sequence.md)
- [Component depth](components.md)
- [Folder structure](folder-structure.md)