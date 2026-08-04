# Architecture — Components

Depth view of the main components and their boundaries.

## API layer (`app/api.py`)

The FastAPI application. Owns every HTTP route, middleware and exception
handler.

- **Middleware:** audit logging, auth enforcement, tenancy context,
  rate limiting, request size guard.
- **Route groups:** chat/completions, embeddings, agents, orchestration,
  knowledge (collections, documents, chunks, embed), vector search,
  plugins, stats, costs, distribution, capabilities, tokens, benchmark,
  runtime, tasks, analytics, cache, dashboard, config.
- **Lifecycle:** graceful shutdown, startup validation
  (`validate_environment()`), build metadata (`/version`).

## Router (`app/router.py`, `app/routing.py`, `app/classifier.py`)

- Classifier: task classification from prompt when model is implicit.
- Routing engine: provider filtering → scoring → selection → failover.
- Traffic distribution: weighted routing, circuit breakers, reputation.

## Provider adapters (`app/providers/`)

One client class per provider implementing a common call interface
(completions, embeddings, streaming). Used by routing and RAG embedding.

## RAG stack

| Component | Module | Role |
| --- | --- | --- |
| Ingestion | `app/knowledge/` | Documents, collections, tags, upload/import |
| Chunking | `app/knowledge/chunking*` | Fixed/semantic chunk strategies |
| Embedding | `app/knowledge/embedding*` | Provider-based or local embeddings |
| Vector store | `app/knowledge/vector*` | Memory/Qdrant/Chroma/pgvector/Redis backends |
| Retrieval | `app/retrieval/` | Hybrid & semantic search |
| Reranking | `app/reranker/` | Cross-encoder & ensemble rerankers |
| RAG orchestration | `app/rag/` | Context building, citations, evaluation |

## MCP SDK (`app/mcp/`)

Protocol types, client, discovery, sessions, transports (streamable HTTP),
statistics and auth. Used by applications to talk to MCP servers; the
gateway itself is MCP-capable via the same primitives.

## Plugin system (`app/plugin/`, `app/plugins/`)

Signed, versioned plugins with request/response hooks, manifest handling,
hot reload, and an event stream (`/plugins/events`).

## Distributed runtime

| Component | Module | Role |
| --- | --- | --- |
| Workers | `app/worker.py`, `app/tasks/` | Execute queued jobs |
| Scheduler | `app/scheduler.py` | Due-task dispatch, cron-like |
| Leader election | `app/distributed/` | HA coordination |
| Event bus | `app/event_bus.py` | Internal pub/sub |
| Queue | `app/tasks/queue.py` | Redis-backed queue + DLQ |

## Platform services

- **Security** (`app/security/`): key management (KMS/HSM adapters), secrets
  backends, zero-trust, threat detection, audit chains, privacy.
- **Billing** (`app/billing/`): usage metering, quotas, invoices, plans.
- **Tenancy** (`app/tenancy/`): tenant isolation, context, middleware.
- **Admin** (`app/admin/`): settings, feature flags, health, alerts.

## Observability

- **Metrics** (`app/metrics.py`, `app/stats.py`): request/error/latency,
  token usage, provider stats.
- **SLOs** (`app/observability/`): error budgets, burn-rate alerts.
- **Logging** (`app/logger.py`): structured logs with secret masking.
- **Tracing:** OpenTelemetry exporter (`OTEL_*` env).

## Data stores

| Store | Purpose | Backends |
| --- | --- | --- |
| Redis | Queue, cache, leader election, vector (optional) | `redis://` |
| SQLite | Local metadata (migrations, knowledge DB) | file |
| Vector | Embedding storage | memory / Qdrant / Chroma / pgvector / Redis |
| Secrets | API keys | env / Vault / K8s / AWS / Azure / GCP |