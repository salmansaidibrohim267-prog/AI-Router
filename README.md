# AI-Router Gateway

FastAPI-based intelligent AI model router with automatic task classification, provider management, health monitoring, circuit breaker, smart routing, streaming, benchmarking, comprehensive observability (Prometheus + Grafana + Loki), and an **AI Orchestration Engine** for multi-agent workflows, consensus, debate, and reflection.

## Architecture

```
┌───────────────────────────────────────────────────────┐
│                    Client                              │
└──────────┬────────────────────────────────────────────┘
           │
┌──────────▼────────────────────────────────────────────┐
│           Orchestration Engine (app/orchestration/)     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │ Planner   │  │  Agents  │  │ Consensus│  │ Debate │ │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘  └───┬────┘ │
│        │            │              │             │      │
│  ┌─────▼────────────▼──────────────▼─────────────▼────┐ │
│  │              Execution Engine                       │ │
│  │  Sequential · Parallel · Workflow · Reflection     │ │
│  └──────────────────────┬─────────────────────────────┘ │
└─────────────────────────┼───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│               AI Router (router.py)                      │
│     ┌──────────────┐     ┌──────────────┐               │
│     │  Classifier   │     │  Router      │               │
│     │  (NLP/Keyword)│     │  (routing,   │               │
│     └──────┬───────┘     │   retry, CB) │               │
│            │             └──────┬───────┘               │
│     ┌──────▼────────────────────▼──────────────────┐    │
│     │           ProviderManager                     │    │
│     └───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬───┬──┘    │
└─────────┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───┼───────┘
          │   │   │   │   │   │   │   │   │   │   │
          ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼
     OpenRouter · OpenAI · Anthropic · Google · Mistral · Groq · Ollama

## Features

| # | Feature | Status |
|---|---------|--------|
| 1 | Provider Health Monitoring (30s interval, online/offline/latency) | Done |
| 2 | Circuit Breaker (5 failures → 60s cooldown → auto-recovery) | Done |
| 3 | Smart Routing (latency, availability, failure rate, cost, preference) | Done |
| 4 | Streaming (SSE, OpenAI-compatible `/v1/chat/completions`) | Done |
| 5 | Embedding (`POST /v1/embeddings`) | Done |
| 6 | Model Discovery (`GET /models` aggregates all providers) | Done |
| 7 | Prometheus Metrics (`/metrics`: 16 metric types: requests, latency, tokens, cost, circuit breaker, fallback, cache, rate limit) | Done |
| 8 | Structured JSON Logging (request_id, provider, model, latency, tokens, cost) | Done |
| 9 | Token Accounting (prompt/completion/total tokens, cost estimation) | Done |
| 10 | Dashboard API (`GET /dashboard` unified status) | Done |
| 11 | Config Watcher (auto-reload on models.yaml change) | Done |
| 12 | Async Providers (httpx.AsyncClient, fully async) | Done |
| 13 | Retry with Exponential Backoff (1s, 2s, 4s → fallback) | Done |
| 14 | Tests (303+ tests, 76%+ coverage) | Done |
| 15 | Docker (multi-stage, non-root user, OCI labels, build args, resource limits, ulimits, logging) | Done |
| 16 | CI/CD (GitHub Actions: lint, format, pytest, coverage, docker build, compose validation, security scan, audit) | Done |
| 17 | Documentation (README, architecture, endpoints, observability, production deployment guide) | Done |
| 18 | Performance (SOLID, minimized duplication) | Done |
| 19 | CLI Benchmark (`python -m benchmarks.cli` + `GET /benchmark`) | Done |
| 20 | Docker Compose Profiles (`dev`, `monitoring`, `production`, `minimal`) | Done |
| 21 | Docker Secrets (`/run/secrets/` with `.env` fallback) | Done |
| 22 | Production Scripts (backup, restore, prune, healthcheck, verify, deploy, rollback, update, status, validate) | Done |
| 23 | Enhanced Health Checks (per-provider status, cache, memory, CPU, uptime, build info, degraded mode) | Done |
| 24 | Security (CORS config, trusted hosts, request size limits, security headers, sensitive log masking) | Done |
| 25 | Versioning (`/version` endpoint with git commit, build date, Python version) | Done |
| 20 | Production Deployment (Traefik integration, graceful shutdown, startup validation, /config endpoint) | Done |
| 21 | Health Checks (per-provider status, dependency checks, degraded detection) | Done |
| 20 | Grafana Dashboards (overview + provider details, ready-to-import) | Done |
| 21 | Loki + Promtail (log aggregation pipeline) | Done |
| 22 | Prometheus Alerting Rules (error rate, provider down, high latency, circuit breaker) | Done |
| 23 | Orchestration Engine (Planner, Agents, Executor) | Done |
| 24 | Reflection (auto-evaluate + retry on low scores) | Done |
| 25 | Consensus Mode (majority vote, weighted score, first success, best latency) | Done |
| 26 | Debate Mode (two providers argue, reviewer picks winner) | Done |
| 27 | Tool Pipeline (search, calculator, database, http) | Done |
| 28 | Workflow Engine (IF/ELSE/FOR/PARALLEL/WAIT/RETRY/TIMEOUT/MERGE) | Done |
| 29 | Streaming through Orchestration (SSE via /v1/orchestrate) | Done |
| 30 | Orchestration Metrics (9 Prometheus metrics) | Done |
| 31 | Tests (1111+ tests, orchestration coverage expanded) | Done |

## Folder Structure

```
AI-Router/
├── app/
│   ├── __init__.py
│   ├── api.py              # FastAPI application & endpoints
│   ├── main.py             # Entry point (uvicorn runner)
│   ├── router.py           # AI Router: routing, retry, circuit breaker, fallback
│   ├── config.py           # Config loader with hot-reload & validation
│   ├── classifier.py       # Task classifier (coding, chat, analysis, architecture)
│   ├── logger.py           # Structured JSON logging (file + stdout)
│   ├── stats.py            # Statistics tracking (provider, model, task)
│   ├── metrics.py          # Prometheus metrics (16 metric types)
│   ├── models.py           # Pydantic models (requests, responses, configs)
│   ├── cache.py            # TTL cache with LRU eviction
│   ├── costs.py            # Token accounting & cost estimation
│   ├── exceptions.py       # Custom exception hierarchy (15+ classes)
│   ├── rate_limit.py       # Rate limiter (sliding window + token bucket)
│   ├── orchestration/        # AI Orchestration Engine (Stage 6)
│   │   ├── __init__.py       # Public API exports
│   │   ├── orchestrator.py   # Main orchestrator (plans, executes, reflects)
│   │   ├── planner.py        # Plan creation (single/multi/parallel)
│   │   ├── agents.py         # Agent system (6 agents + registry)
│   │   ├── executor.py       # Execution engine (sequential/parallel/workflow)
│   │   ├── reflection.py     # Self-evaluation + auto-retry
│   │   ├── consensus.py      # Multi-provider consensus + voting
│   │   ├── debate.py         # Two-provider debate with reviewer
│   │   ├── tools.py          # Tool pipeline (search, calc, db, http)
│   │   ├── workflow.py       # Workflow builder (IF/ELSE/FOR/PARALLEL/etc)
│   │   ├── memory.py         # Execution memory context
│   │   ├── metrics.py        # Orchestration Prometheus metrics
│   │   └── models.py         # Orchestration Pydantic models
│   └── providers/
│       ├── __init__.py
│       ├── base.py         # Abstract base provider (5 abstract methods)
│       ├── manager.py      # Provider manager: health, circuit breaker, discovery
│       ├── openrouter.py   # OpenRouter provider
│       ├── ollama.py       # Ollama local provider
│       ├── openai.py       # OpenAI provider
│       ├── anthropic.py    # Anthropic provider
│       ├── google.py       # Google Gemini provider
│       ├── mistral.py      # Mistral AI provider
│       └── groq.py         # Groq provider
├── benchmarks/
│   ├── __init__.py
│   ├── runner.py           # Benchmark engine (latency, throughput, p95, p99)
│   └── cli.py              # CLI benchmark runner
├── config/
│   ├── models.yaml         # Task routing config
│   └── providers.yaml      # Provider definitions
├── tests/
│   ├── test_*.py           # 16 test files, 303 tests
├── grafana/
│   ├── dashboards/
│   │   ├── ai-router-overview.json    # Main overview dashboard
│   │   └── ai-router-providers.json   # Provider details dashboard
│   └── provisioning/
│       ├── datasources/datasources.yml
│       └── dashboards/dashboards.yml
├── prometheus/
│   ├── prometheus.yml      # Scrape config
│   └── alerts.yml          # Alerting rules
├── loki/
│   └── loki-config.yml     # Log aggregation config
├── promtail/
│   └── promtail-config.yml # Log shipping config
├── logs/                   # JSON log output
├── .env                    # API keys (gitignored)
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Quick Start

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys

# Run
python -m app.main
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Root info |
| GET | `/health` | Health check |
| GET | `/health/providers` | All providers health |
| GET | `/health/providers/{name}` | Specific provider health |
| GET | `/providers` | List providers with realtime status |
| GET | `/providers/{name}/models` | List provider models |
| GET | `/models` | Model discovery (aggregated) |
| GET | `/models/{task}` | Models for task |
| POST | `/v1/chat/completions` | Chat completion (OpenAI-compatible, SSE streaming) |
| POST | `/v1/embeddings` | Generate embeddings |
| GET | `/stats` | Router statistics summary |
| GET | `/stats/providers` | Per-provider stats |
| GET | `/stats/providers/{name}` | Specific provider stats |
| GET | `/stats/models/{provider}/{model}` | Model stats |
| GET | `/stats/tasks` | Task usage stats |
| GET | `/stats/errors` | Error stats |
| POST | `/stats/reset` | Reset statistics |
| GET | `/metrics` | Prometheus metrics |
| GET | `/config` | Current configuration |
| POST | `/reload-config` | Hot-reload config |
| GET | `/logs` | Recent logs |
| GET | `/logs/{request_id}` | Log by request ID |
| DELETE | `/logs` | Clear logs |
| GET | `/cache/stats` | Cache statistics |
| POST | `/cache/clear` | Clear cache |
| GET | `/dashboard` | Unified dashboard |
| GET | `/costs` | Token usage & costs |
| GET | `/costs/{provider}` | Provider-specific costs |
| GET | `/benchmark` | Run benchmark (query: model, num_requests, concurrency, stream) |
| POST | `/v1/orchestrate` | Orchestrate multi-agent workflow (streaming with `stream: true`) |
| POST | `/v1/agents` | Execute agents on a prompt |
| POST | `/v1/workflow` | Execute a defined workflow |
| POST | `/v1/consensus` | Run consensus across providers |
| POST | `/v1/debate` | Run debate between two providers |

## Orchestration Engine

The orchestration layer (`app/orchestration/`) sits above the router and enables multi-agent workflows, reflection, consensus, debate, and streaming.

### Execution Flow

```
User Request
     │
     ▼
  Orchestrator  ──►  Planner  ──►  ExecutionPlan
     │                                   │
     │                              ExecutionEngine
     │                             /     │      \
     │                         Agent A  Agent B  Agent C
     │                            │        │        │
     │                         Router  Router   Router
     │                            │        │        │
     │                         Provider Provider Provider
     │
     ├── Reflection ──► evaluate scores ──► retry if below threshold
     ├── Consensus  ──► query N providers ──► pick best
     └── Debate     ──► provider A vs B ──► reviewer picks winner
```

### POST /v1/orchestrate

Execute any orchestration mode. Returns JSON or SSE stream.

```bash
# Single agent streaming
curl -X POST http://localhost:8000/v1/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write a poem","mode":"single","stream":true}'

# Multi-agent sequential
curl -X POST http://localhost:8000/v1/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build a REST API","agents":["architect","coder","reviewer"],"mode":"multi"}'

# With reflection
curl -X POST http://localhost:8000/v1/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write production code","agents":["coder"],"reflection":true}'
```

### POST /v1/consensus

Query multiple providers, return best answer.

```bash
curl -X POST http://localhost:8000/v1/consensus \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Capital of France?","providers":["openai","anthropic","google"],"strategy":"majority_vote"}'
```

Strategies: `majority_vote`, `weighted_score`, `highest_confidence`, `first_success`, `best_latency`.

### POST /v1/debate

Two providers argue, reviewer picks winner.

```bash
curl -X POST http://localhost:8000/v1/debate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Is AGI possible by 2030?","provider_a":"openai","provider_b":"anthropic"}'
```

### POST /v1/workflow

Multi-step workflow with control flow nodes: `task`, `if`, `else`, `for`, `parallel`, `wait`, `retry`, `timeout`, `merge`.

```bash
curl -X POST http://localhost:8000/v1/workflow \
  -H "Content-Type: application/json" \
  -d '{"id":"wf","steps":[{"id":"s1","type":"task","agent":"chat","prompt":"Hello"},{"id":"s2","type":"wait","prompt":"0.5"},{"id":"s3","type":"merge","merge_strategy":"concat"}]}'
```

### Orchestrator Configuration (`config/orchestrator.yaml`)

```yaml
orchestrator:
  enabled: true
  default_mode: single
planner:
  enabled: true
  agent_map:
    coding: coder  architecture: architect
    analysis: analyst  review: reviewer
reflection:
  enabled: false
  threshold: 0.7
  max_retries: 2
consensus:
  enabled: false
  default_strategy: majority_vote
debate:
  enabled: false

```

### Orchestration Metrics (Prometheus)

| Metric | Type | Description |
|--------|------|-------------|
| `orchestrator_requests_total` | Counter | Requests by mode |
| `orchestrator_planner_latency_seconds` | Histogram | Planner latency |
| `orchestrator_execution_latency_seconds` | Histogram | Execution latency |
| `orchestrator_agent_latency_seconds` | Histogram | Per-agent latency |
| `orchestrator_reflection_retry_total` | Counter | Reflection retries |
| `orchestrator_consensus_count_total` | Counter | Consensus executions |
| `orchestrator_debate_count_total` | Counter | Debate executions |
| `orchestrator_workflow_count_total` | Counter | Workflow executions |
| `orchestrator_active_requests` | Gauge | Active requests |

## Enterprise Orchestration Platform

The platform extends the orchestration engine with conversation memory, tool calling, DAG workflows, task queues, budget management, context compression, human approval, and distributed workers.

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Orchestration Platform                         │
│                                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │ Conversation │  │  Tool        │  │  Workflow DAG            │ │
│  │ Memory       │  │  Registry    │  │  Topological Sort        │ │
│  │ (app/memory/)│  │  (app/tools/)│  │  Cycle Detection         │ │
│  └──────┬──────┘  └──────┬───────┘  └────────┬────────────────┘ │
│         │                │                     │                  │
│  ┌──────▼────────────────▼─────────────────────▼────────────────┐ │
│  │                    Task Queue (app/tasks/)                     │ │
│  │  Storage ── Worker Pool ── Scheduler ── Timeline ── Graph     │ │
│  └─────────────────────────────┬─────────────────────────────────┘ │
│                                │                                   │
│  ┌─────────────────────────────▼─────────────────────────────────┐ │
│  │              Orchestrator (app/orchestration/)                  │ │
│  │  Budget ── Context Compression ── Approval ── Persistence     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

### Conversation Memory (`app/memory/`)

Session-based conversation memory with short-term and long-term storage, automatic summarization, TTL, pruning, and token budgeting.

```python
from app.memory import ConversationMemory

memory = ConversationMemory()
session_id = memory.create_session({"user": "alice"})
memory.add_message(session_id, "user", "Hello")
history = memory.get_history(session_id)
```

**Storage backends:** SQLite (default), Redis, Filesystem — hot-swappable via `MEMORY_BACKEND` env var.

### Tool Registry (`app/tools/`)

Plugin-like tool system with permission management, timeout, validation, and metrics.

**Built-in tools:** `python`, `shell`, `http`, `git`, `filesystem`, `search`, `calculator`

```python
from app.tools import ToolRegistry, ToolExecutor

registry = ToolRegistry()
executor = ToolExecutor(registry)
result = await executor.execute("calculator", "2 + 2")
```

### Workflow DAG (`app/orchestration/dag.py`)

DAG-based workflow execution with topological sort, cycle detection, and parallel branch support. Use `depends_on` to define edges.

```python
from app.orchestration.dag import WorkflowDAG

dag = WorkflowDAG(steps)
levels = dag.topological_sort()  # [[s1], [s2, s3], [s4]]
viz = dag.to_visualization_data()
```

### Task Queue (`app/tasks/`)

Background orchestration with queuing, worker pool, and scheduler.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tasks` | POST | Create a task |
| `/tasks/orchestrate` | POST | Submit orchestration as task |
| `/tasks` | GET | List tasks (filter by state/type) |
| `/tasks/{id}` | GET | Get task details |
| `/tasks/{id}` | DELETE | Delete task |
| `/tasks/{id}/cancel` | POST | Cancel task |
| `/tasks/{id}/graph` | GET | Execution graph + timeline |
| `/tasks/queue/depth` | GET | Queue depth by state |

### Execution Timeline

Every orchestration records timeline events automatically:

```json
[
  {"event": "orchestration_started", "timestamp": ...},
  {"event": "plan_created", "steps": 3, "timestamp": ...},
  {"event": "agent_coder_completed", "agent": "coder", "tokens": 150, "timestamp": ...},
  {"event": "orchestration_completed", "latency_ms": 1234, "timestamp": ...}
]
```

### Execution Graph

Exposed via `GET /tasks/{id}/graph` as JSON with nodes, edges, metadata, status, duration, and cost.

### Budget Manager (`app/orchestration/budget.py`)

Track total/prompt/completion tokens, cost, remaining budget, with automatic downgrade suggestions.

| Limit | Config Key | Default |
|-------|-----------|---------|
| Max cost | `max_cost` | $10.00 |
| Max tokens | `max_tokens` | 1,000,000 |
| Max latency | `max_latency_ms` | 60,000ms |

**Automatic downgrade chain:** GPT → Claude → Gemma → Qwen → Ollama

### Context Compression (`app/orchestration/compression.py`)

When context exceeds model limit: summarize older messages, compress, continue — never silently truncate. Records compression statistics (ratio, count).

### Human Approval (`app/orchestration/approval.py`)

Workflow checkpoints that pause execution pending human approval.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/approval/checkpoints` | POST | Create checkpoint |
| `/approval/checkpoints/{id}/approve` | POST | Approve |
| `/approval/checkpoints/{id}/reject` | POST | Reject |
| `/approval/pending` | GET | List pending |
| `/approval/checkpoints` | GET | List all |

### Persistent Sessions (`app/orchestration/persistence.py`)

Sessions survive restart via configurable backends: SQLite, Redis, or Filesystem. Set `MEMORY_BACKEND=redis` or `MEMORY_BACKEND=file`.

### Distributed Workers (`app/orchestration/worker_pool.py`)

Configurable worker pool that processes tasks from the queue.

```python
from app.orchestration import WorkerPool

pool = WorkerPool(queue, orchestrator, worker_count=3)
await pool.start()
```

### New Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `orchestrator_task_queue_depth` | Gauge | Queue depth by state |
| `orchestrator_worker_utilization` | Gauge | Worker utilization |
| `orchestrator_task_duration_seconds` | Histogram | Task execution duration |
| `orchestrator_memory_usage_bytes` | Gauge | Memory store usage |
| `orchestrator_compression_ratio` | Gauge | Context compression ratio |
| `orchestrator_budget_remaining` | Gauge | Remaining budget in USD |
| `orchestrator_budget_tokens_remaining` | Gauge | Remaining token budget |
| `orchestrator_approval_waiting_total` | Gauge | Pending approval count |
| `orchestrator_execution_graph_count` | Gauge | Execution graphs generated |
| `orchestrator_tool_call_total` | Counter | Tool call count |
| `orchestrator_compression_count_total` | Counter | Compression count |

### Configuration

Add to `config/orchestrator.yaml`:

```yaml
memory:
  backend: sqlite  # sqlite | redis | file
  session_ttl: 3600
  max_token_budget: 8000
  message_ttl: 7200

budget:
  max_cost: 10.0
  max_tokens: 1000000
  max_latency_ms: 60000

compression:
  enabled: true
  max_context_tokens: 8000
  compression_ratio: 0.5

tools:
  enabled: true
  python: { enabled: true }
  shell: { enabled: false }
  http: { enabled: true }
  git: { enabled: false }
  filesystem: { enabled: false }
  search: { enabled: true }
  calculator: { enabled: true }

workers:
  count: 3
  max_concurrent: 5
  poll_interval: 1.0
```

### Task Routing (`config/models.yaml`)

```yaml
chat:
  primary:
    provider: ollama
    model: qwen2.5-coder:7b
  fallback:
    - provider: ollama
      model: llama3.2:latest
```

### Provider Config (`config/providers.yaml`)

```yaml
providers:
  - name: openrouter
    display_name: "OpenRouter"
    api_key_env: "OPENROUTER_API_KEY"
    base_url: "https://openrouter.ai/api/v1"
    timeout: 60.0
    max_retries: 3
    enabled: true
    priority: 10
```

## Routing Logic

The router ranks providers using a composite score:

1. **Health status** (+100 healthy, -1000 unhealthy)
2. **Model score** (from config scoring)
3. **Latency** (lower is better)
4. **Failure rate** (-500 * failure_rate penalty)
5. **Cost** (lower cost = higher score)
6. **User preference** (+200 boost)

## Circuit Breaker

- **Closed**: Normal operation
- **Open**: After 5 consecutive failures → provider disabled for 60s
- **Half-Open**: After timeout → test with one request
- **Closed**: After 3 successful half-open requests

## Testing

```bash
pytest tests/ -v --cov=app
```

## Streaming (SSE)

OpenAI-compatible streaming with `stream=true`:

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Count to 5"}],"stream":true}'
```

Response format:
```
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"1"}}]}
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"2"}}]}
data: {"id":"...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

Features: timeout handling, graceful cancellation, provider fallback, per-chunk metadata.

## Benchmark

### CLI
```bash
python -m benchmarks.cli \
  --model gpt-4o-mini \
  --num-requests 50 \
  --concurrency 10 \
  --stream \
  --output results.json
```

### API
```bash
curl "http://localhost:8000/benchmark?model=gpt-4o-mini&num_requests=20&concurrency=5&stream=false"
```

Returns: average_latency_ms, p95, p99, throughput (req/s), success_rate, errors, fallback_count.

## Docker

### Build (Multi-stage)
```bash
docker build -t ai-router:latest .
```

The multi-stage Dockerfile uses a builder stage for pip install and a minimal runtime stage with a non-root user. The final image is ~180 MB.

### Standalone
```bash
docker run -p 8000:8000 --env-file .env \
  -v ./config:/app/config:ro \
  ai-router:latest
```

### Full Stack
```bash
docker-compose up -d
```

### Multi-Service Architecture

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| ai-router | local | 8000 | API, metrics, health |
| prometheus | prom/prometheus:v2.53.0 | 9090 | Metric scraping & storage |
| grafana | grafana/grafana:11.1.0 | 3000 | Dashboards (auto-provisioned) |
| loki | grafana/loki:3.1.0 | 3100 | Log aggregation |
| promtail | grafana/promtail:3.1.0 | — | Ships logs to Loki |
| ollama | ollama/ollama:0.3.12 | 11434 (localhost) | Local LLM inference |

All images are pinned to specific versions for reproducible deployments.

## Production Deployment

### Prerequisites
- Docker Engine 24+
- Docker Compose v2.20+
- (Optional) Traefik reverse proxy for HTTPS
- (Optional) Redis 7+ for distributed caching and rate limiting (not required for single-instance)

### 1. Environment Setup

Create `.env` from `.env.example` and set at least one API key:

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 2. Docker Compose Profiles

The project supports four profiles:

| Profile | Services Included | Use Case |
|---------|------------------|----------|
| `minimal` | ai-router | API only, no dependencies |
| `dev` | ai-router, ollama | Development with local LLM |
| `monitoring` | ai-router, prometheus, grafana, loki, promtail | Monitoring stack only |
| `production` | all services | Full production stack |

```bash
# Start only the API (no monitoring)
docker compose --profile minimal up -d

# Start full production stack
docker compose --profile production up -d
```

### 3. Docker Secrets

API keys can be provided via Docker Secrets (`/run/secrets/`) or `.env` file:

```bash
# Using Docker Secrets (swarm or compose secrets)
echo "sk-..." | docker secret create openai_api_key -

# The app checks /run/secrets/<NAME> first, falls back to env vars
```

In docker-compose.yml, mount secrets as files or use `secrets:` block. The app
reads from `/run/secrets/` directory automatically. See `app/secrets.py`.

### 4. Resource Limits

The docker-compose.yml includes CPU and memory limits:

| Service | CPU Limit | Memory Limit | ulimit (nofile) |
|---------|-----------|-------------|-----------------|
| ai-router | 1.0 core | 512 MB | 1024/2048 |
| prometheus | — | 1 GB | — |
| grafana | — | 256 MB | — |
| loki | — | 512 MB | — |
| promtail | — | 128 MB | — |
| ollama | 2.0 cores | 8 GB | — |

Logging is configured with json-file driver (10 MB per file, 3 files rotation).

### 5. Traefik Integration (HTTPS)

The ai-router service is annotated with Traefik Docker provider labels:

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.ai-router.rule=Host(`ai-router.example.com`)"
  - "traefik.http.routers.ai-router.entrypoints=websecure"
  - "traefik.http.routers.ai-router.tls=true"
  - "traefik.http.routers.ai-router.tls.certresolver=letsencrypt"
```

For file-based Traefik configuration, see `traefik/ai-router-dynamic.yml`.

### 6. Start the Stack

```bash
docker compose --profile production up -d
docker compose logs -f ai-router
```

Verify:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/config
curl http://localhost:8000/version
```

### 7. Production Scripts

The `scripts/` directory provides automation scripts:

| Script | Purpose |
|--------|---------|
| `scripts/deploy.sh` | Build, validate, deploy with health verification |
| `scripts/rollback.sh` | Roll back to previous image tag |
| `scripts/update.sh` | Git pull, rebuild, redeploy |
| `scripts/backup.sh` | Timestamped backup of config, volumes, logs |
| `scripts/restore.sh` | Restore from a backup directory |
| `scripts/prune.sh` | Remove backups older than N days |
| `scripts/healthcheck.sh` | Check API health with optional `--wait` |
| `scripts/status.sh` | Full status report (containers, resources, health) |
| `scripts/validate.sh` | Validate configuration, dependencies, Docker |
| `scripts/verify.sh` | Post-deployment verification |

```bash
# Deploy
./scripts/deploy.sh production

# Backup
./scripts/backup.sh

# Health check
./scripts/healthcheck.sh --wait
```

### 8. Zero-Downtime Deployment

```bash
./scripts/deploy.sh production
```

Or manually:

```bash
docker build -t ai-router:latest .
docker compose --profile production up -d --no-deps --scale ai-router=2 ai-router
# Wait for health check
./scripts/healthcheck.sh --wait
docker compose --profile production up -d --no-deps --scale ai-router=1 ai-router
```

### 9. Backup

```bash
# Full backup (config, volumes, logs)
./scripts/backup.sh ./backups

# Or manually:
# Grafana dashboards (provisioned, backed up in git)
git add grafana/dashboards/

# Prometheus data (volume backup)
docker run --rm -v prometheus_data:/data -v $(pwd)/backups:/backup \
  alpine tar czf /backup/prometheus-$(date +%Y%m%d).tar.gz -C /data .

# Logs
tar czf backups/logs-$(date +%Y%m%d).tar.gz logs/

# Restore
./scripts/restore.sh backups/20250101_120000
```

### 10. Upgrade

```bash
./scripts/update.sh production
```

Or manually:

```bash
git pull
docker compose --profile production pull
docker build -t ai-router:latest .
docker compose --profile production up -d
./scripts/healthcheck.sh --wait
```

### 11. Rollback

```bash
./scripts/rollback.sh previous
```

Or manually:

```bash
docker tag ai-router:previous ai-router:latest
docker compose --profile production up -d ai-router
```

### 12. Disaster Recovery

1. **Config corruption**: Restore config from backup: `./scripts/restore.sh <backup>`
2. **Volume loss**: Prometheus/Grafana/Loki data in named volumes; restore from backup
3. **Image corruption**: `docker build -t ai-router:latest .` or pull from registry
4. **Full rebuild**: `docker compose down -v && docker compose --profile production up -d`

### 13. Monitoring

- **Metrics**: `http://localhost:9090` (Prometheus)
- **Dashboards**: `http://localhost:3000` (Grafana, admin/admin)
- **Logs**: `http://localhost:3100/ready` (Loki readiness)
- **Health**: `GET /health` (includes per-provider status, memory, CPU, uptime)
- **Config**: `GET /config` (runtime configuration view)
- **Version**: `GET /version` (build metadata)
- **Prometheus Metrics**: `GET /metrics`

## Observability Stack

### Prometheus Metrics

All 16 metric types are available at `GET /metrics`:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ai_router_request_total` | Counter | provider, model, task | Total requests |
| `ai_router_request_success` | Counter | provider, model | Successful requests |
| `ai_router_request_failed` | Counter | provider, model, error_type | Failed requests |
| `ai_router_provider_latency_seconds` | Histogram | provider, model | Request latency histogram |
| `ai_router_provider_requests_total` | Counter | provider | Total requests per provider |
| `ai_router_provider_failure_total` | Counter | provider, error_type | Provider failures |
| `ai_router_cache_hit` | Counter | cache_name | Cache hits |
| `ai_router_cache_miss` | Counter | cache_name | Cache misses |
| `ai_router_provider_health` | Gauge | provider | 1=healthy, 0=unhealthy |
| `ai_router_provider_latency_ms` | Gauge | provider | Current provider latency (ms) |
| `ai_router_uptime_seconds` | Gauge | — | Router uptime |
| `ai_router_tokens_total` | Counter | provider, model, type | Token consumption (prompt/completion) |
| `ai_router_cost_usd_total` | Counter | provider, model | Cost in USD |
| `ai_router_circuit_breaker_state` | Gauge | provider | 0=closed, 1=half-open, 2=open |
| `ai_router_fallback_total` | Counter | provider, model, from_provider | Fallback events |
| `ai_router_rate_limit_total` | Counter | — | Rate-limited requests |
| `ai_router_active_requests` | Gauge | — | In-flight requests |

### Grafana Dashboards

Two ready-to-import dashboards in `grafana/dashboards/`:

1. **AI Router - Production Overview** (`ai-router-overview.json`):
   - Request rate, success rate, active requests, uptime
   - Latency percentiles (p50/p95/p99)
   - Provider health and latency
   - Error rate by provider and error type
   - Token consumption and cost by provider
   - Circuit breaker state and fallback rate
   - Cache hit/miss rate
   - Request rate by task
   - Live log stream from Loki

2. **AI Router - Provider Details** (`ai-router-providers.json`):
   - Per-provider request rate, failures, latency percentiles
   - Cost and token rate by provider
   - Circuit breaker state timeline
   - Provider health timeline
   - Fallback events by provider pair

### Loki + Promtail

Logs are written as JSON lines to `logs/router.jsonl`. Promtail ships them to Loki:

```yaml
# Pipeline stages: JSON parse → timestamp extract → label injection
# Fields: timestamp, level, provider, model, task, latency_ms, success, error, tokens
```

### Prometheus Alerting Rules (`prometheus/alerts.yml`)

| Alert | Condition | Severity |
|-------|-----------|----------|
| HighErrorRate | > 10% errors over 5m | Warning |
| ProviderDown | Health == 0 for 1m | Critical |
| HighLatency | P95 > 5s for 3m | Warning |
| CircuitBreakerOpen | State == 2 for 1m | Critical |
| HighCostSpend | > $10/hour for 5m | Warning |
| RateLimitThreshold | > 10/s rate limited for 2m | Warning |
| FallbackStorm | > 20/s fallbacks for 3m | Warning |
| NoHealthyProviders | All providers unhealthy | Critical |

### Running the Full Stack

```bash
docker-compose up -d
```

| Service | Port | Credentials | Purpose |
|---------|------|-------------|---------|
| ai-router | 8000 | — | API, metrics, health |
| prometheus | 9090 | — | Metric scraping & storage |
| grafana | 3000 | admin / admin | Dashboards (auto-provisioned) |
| loki | 3100 | — | Log aggregation |
| promtail | — | — | Ships logs to Loki |

Grafana dashboards auto-provision on startup. Open http://localhost:3000 (admin/admin).

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| OPENROUTER_API_KEY | No | — | OpenRouter API key (also via Docker Secret) |
| OPENAI_API_KEY | No | — | OpenAI API key (also via Docker Secret) |
| ANTHROPIC_API_KEY | No | — | Anthropic API key (also via Docker Secret) |
| GOOGLE_API_KEY | No | — | Google Gemini API key (also via Docker Secret) |
| MISTRAL_API_KEY | No | — | Mistral API key (also via Docker Secret) |
| GROQ_API_KEY | No | — | Groq API key (also via Docker Secret) |
| HOST | No | 0.0.0.0 | Server bind address |
| PORT | No | 8000 | Server port |
| LOG_LEVEL | No | info | Uvicorn log level (debug/info/warning/error) |
| RATE_LIMIT_REQUESTS | No | 100 | Max requests per window |
| RATE_LIMIT_WINDOW | No | 60 | Rate limit window (seconds) |
| CORS_ORIGINS | No | * | Comma-separated allowed CORS origins |
| ALLOWED_HOSTS | No | * | Comma-separated allowed Host headers |
| MAX_REQUEST_SIZE_BYTES | No | 10485760 | Maximum request body size (10 MB) |
| REDIS_URL | No | — | Redis URL for distributed caching (optional) |
| BUILD_DATE | No | — | Docker build timestamp (set at build time) |
| GIT_COMMIT | No | — | Git commit hash (set at build time) |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API root with links |
| GET | `/version` | Build metadata (version, git commit, build date) |
| GET | `/health` | Application health (providers, memory, CPU, uptime, cache) |
| GET | `/health/providers` | Per-provider health details |
| GET | `/health/providers/{name}` | Single provider health |
| GET | `/config` | Runtime configuration |
| POST | `/reload-config` | Hot-reload configuration from files |
| GET | `/metrics` | Prometheus metrics |
| GET | `/providers` | Provider list with health status |
| GET | `/providers/{name}/models` | Models for a specific provider |
| GET | `/models` | All available models |
| GET | `/models/{task}` | Models for a specific task |
| POST | `/v1/chat/completions` | Chat completion (OpenAI-compatible, with streaming) |
| POST | `/v1/embeddings` | Text embeddings |
| GET | `/stats` | Router statistics summary |
| GET | `/stats/providers` | Per-provider statistics |
| GET | `/stats/providers/{name}` | Single provider statistics |
| GET | `/stats/models/{provider}/{model}` | Model statistics |
| GET | `/stats/tasks` | Per-task request counts |
| GET | `/stats/errors` | Error type counts |
| POST | `/stats/reset` | Reset statistics |
| GET | `/logs` | Recent request logs |
| GET | `/logs/{request_id}` | Log by request ID |
| DELETE | `/logs` | Clear logs |
| GET | `/dashboard` | Unified status dashboard |
| GET | `/costs` | Token costs summary |
| GET | `/costs/{provider}` | Costs for a specific provider |
| GET | `/cache/stats` | Cache hit/miss statistics |
| POST | `/cache/clear` | Clear cache |
| GET | `/benchmark` | Run benchmark |
| POST | `/v1/orchestrate` | Orchestrate multi-agent workflow (streaming with `stream: true`) |
| POST | `/v1/agents` | Execute agents on a prompt |
| POST | `/v1/workflow` | Execute a defined workflow |
| POST | `/v1/consensus` | Run consensus across providers |
| POST | `/v1/debate` | Run debate between two providers |
| POST | `/knowledge/collections` | Create a knowledge collection |
| GET | `/knowledge/collections` | List collections |
| GET | `/knowledge/collections/{id}` | Get collection details |
| PUT | `/knowledge/collections/{id}` | Update collection |
| DELETE | `/knowledge/collections/{id}` | Delete collection |
| POST | `/knowledge/documents` | Create a document |
| GET | `/knowledge/documents` | List/search documents |
| GET | `/knowledge/documents/{id}` | Get document |
| PUT | `/knowledge/documents/{id}` | Update document |
| DELETE | `/knowledge/documents/{id}` | Delete document |
| GET | `/knowledge/statistics` | Knowledge statistics |
| POST | `/knowledge/documents/{id}/tags` | Add tags to document |
| DELETE | `/knowledge/documents/{id}/tags` | Remove tags from document |
| POST | `/knowledge/documents/upload` | Upload a document file |
| POST | `/knowledge/documents/import` | Import a document from filesystem |
| GET | `/knowledge/documents/{id}/metadata` | Get document metadata |
| POST | `/knowledge/chunk` | Chunk a document and save chunks |
| POST | `/knowledge/chunk/preview` | Preview chunks without saving |
| GET | `/knowledge/chunks/{document_id}` | List chunks for a document |
| GET | `/knowledge/chunks/{document_id}/{chunk_id}` | Get a specific chunk |
| DELETE | `/knowledge/chunks/{chunk_id}` | Delete chunks |
| POST | `/knowledge/embed` | Embed a single text |
| POST | `/knowledge/embed/batch` | Embed multiple texts |
| GET | `/knowledge/embedding/stats` | Embedding statistics |
| DELETE | `/knowledge/embedding/cache` | Clear embedding cache |

## Knowledge Foundation (Stage 9)

### Knowledge Collections & Documents

The knowledge module provides a structured document storage system with:

- **Collections**: Group documents into logical collections
- **Documents**: Store content with metadata, tags, and version tracking
- **Chunks**: Fine-grained content segments (for future RAG)
- **Backends**: InMemory (testing) or SQLite (production)

### Document Ingestion Pipeline (Stage 9.2)

```
Source → Loader → Parser → Cleaner → Metadata Extractor → Language Detector → Duplicate Checker → KnowledgeDocument
```

**Supported formats**: `.txt`, `.md`/`.mdx`, `.pdf`, `.html`/`.htm`, `.json`

**Pipeline stages**:
- **Loader**: Reads file content from disk or bytes
- **Parser**: Converts raw content to clean text (plain text, markdown, PDF text extraction, HTML stripping, JSON flattening)
- **Cleaner**: Normalizes newlines, trims whitespace, removes control chars, normalizes Unicode, strips BOM
- **Metadata Extractor**: Extracts filename, extension, MIME type, size, SHA-256 checksum, encoding, file timestamps
- **Language Detector**: Heuristic detection supporting English, French, German, Spanish, Portuguese, Dutch, Chinese, Japanese, Korean, Russian, Arabic, Hebrew, Hindi, Thai, Greek
- **Duplicate Detector**: SHA-256 content fingerprinting with configurable reject/allow behavior
- **Validator**: Enforces max file size, supported formats, MIME types, content integrity (PDF header, JSON syntax, HTML well-formedness)

**Configuration** (`.env`):
```
DOCUMENT_MAX_SIZE=10485760
SUPPORTED_DOCUMENT_TYPES=.txt,.md,.mdx,.pdf,.html,.htm,.json
ALLOW_DUPLICATE_DOCUMENT=0
DEFAULT_LANGUAGE=en
```

### Advanced Chunking Engine (Stage 9.3)

```
KnowledgeDocument → Preprocessor → ChunkStrategy → ChunkValidator → MetadataBuilder → KnowledgeChunk[]
```

**5 chunking strategies**:
| Strategy | Split By | Overlap | Use Case |
|----------|----------|---------|----------|
| Fixed Size | Character count | Configurable | General purpose |
| Recursive | Heading → Paragraph → Sentence → Word | Configurable | Markdown documents |
| Paragraph | Paragraph breaks | Configurable | Prose articles |
| Sentence | Sentence boundaries | Configurable | NLP pipelines |
| Sliding Window | Fixed window + stride | Via stride | Streaming overlap |

**Heading Awareness** (Recursive strategy):
- Detects `# Heading` / `## Subheading` / `### Detail` in Markdown
- Stores full section path in chunk metadata: `["Introduction", "Installation", "Docker"]`
- Falls back to paragraph → sentence → word when content still exceeds max size

**Token Estimation**:
- Abstraction: `TokenEstimator(Protocol)` with `estimate(text) → int`
- Default: `HeuristicTokenEstimator` (4 chars/token for ASCII, 2 for non-ASCII)
- Pluggable — inject custom estimator via DI

**Chunk Metadata**:
```
{
  "document_id": "...", "document_title": "...",
  "section": ["Intro", "Sub"], "page_number": 3,
  "language": "en", "source": "...", "tags": [...], "version": 1
}
```

**Chunk fields**: `id`, `document_id`, `collection_id`, `content`, `chunk_index`, `start_offset`, `end_offset`, `token_estimate`, `character_count`, `metadata`, `created_at`

**Configuration** (`.env`):
```
CHUNK_STRATEGY=fixed
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
MIN_CHUNK_SIZE=100
MAX_CHUNK_SIZE=2000
TOKEN_ESTIMATOR=heuristic
```

**API**:
- `POST /knowledge/chunk` — Chunk and save
- `POST /knowledge/chunk/preview` — Preview with optional strategy override
- `GET /knowledge/chunks/{document_id}` — List chunks
- `GET /knowledge/chunks/{document_id}/{chunk_id}` — Get single chunk
- `DELETE /knowledge/chunks/{chunk_id}` — Delete chunks

### Embedding Layer (Stage 9.4)

```
KnowledgeChunk → EmbeddingService → EmbeddingProvider → [Cache] → EmbeddingResult
```

**Provider Abstraction** (`EmbeddingProvider` Protocol):
| Provider | Description | Dependencies |
|----------|-------------|-------------|
| `local` | Deterministic numpy-based embeddings (MD5-seeded, normalized) | numpy |
| `openai` | OpenAI Embeddings API via httpx | httpx, `OPENAI_API_KEY` |
| `ollama` | Ollama embeddings via HTTP API | httpx, Ollama server |

**Features**:
- **Batch processing**: Configurable batch size, automatic splitting, partial failure handling
- **Retry**: Exponential backoff (0.5s → 1s → 2s ..., max 10s), configurable max retry, only recoverable errors
- **Timeout**: Per-request timeout via `asyncio.wait_for`
- **Cache**: InMemory with configurable TTL, content-addressed via SHA-256, hit/miss tracking
- **Validation**: Empty text, text too long, dimension mismatch, empty response
- **Statistics**: Total embeddings, tokens, latency, batch sizes, provider usage, cache hit rate

**Configuration** (`.env`):
```
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BATCH_SIZE=16
EMBEDDING_TIMEOUT=60
EMBEDDING_MAX_RETRY=3
EMBEDDING_CACHE_ENABLED=1
EMBEDDING_CACHE_TTL=3600
```

**API**:
- `POST /knowledge/embed` — Embed single text
- `POST /knowledge/embed/batch` — Embed batch of texts
- `GET /knowledge/embedding/stats` — Embedding service statistics
- `DELETE /knowledge/embedding/cache` — Clear cache

### Architecture

```
app/knowledge/
├── __init__.py
├── models.py           # KnowledgeCollection, KnowledgeDocument, KnowledgeChunk, KnowledgeMetadata
├── repository.py       # KnowledgeRepository (protocol), InMemory, SQLite, factory
├── service.py          # KnowledgeService CRUD operations
├── validation.py       # Collection name, document title, tag validation
├── ingestion/
│   ├── __init__.py
│   ├── config.py       # IngestionConfig
│   ├── models.py       # IngestionResult, IngestionStage, LoadedDocument
│   ├── loaders.py      # TextLoader, MarkdownLoader, PDFLoader, HTMLLoader, JSONLoader
│   ├── parsers.py      # PlainTextParser, MarkdownParser, PDFParser, HTMLParser, JSONParser
│   ├── cleaner.py      # TextCleaner (BOM, newlines, whitespace, control chars, Unicode)
│   ├── metadata.py     # MetadataExtractor (filename, size, checksum, timestamps)
│   ├── language.py     # HeuristicLanguageDetector (Unicode ranges + stopword-based)
│   ├── deduplication.py # DuplicateDetector (SHA-256 fingerprinting)
│   ├── validation.py   # DocumentValidator (size, format, MIME, content integrity)
│   └── pipeline.py     # IngestionPipeline (orchestrates all stages)
└── chunking/
    ├── __init__.py
    ├── config.py       # ChunkingConfig
    ├── models.py       # ChunkingResult, ChunkPreview
    ├── tokenizer.py    # TokenEstimator, HeuristicTokenEstimator
    ├── strategies.py   # 5 strategies + factory
    ├── validator.py    # ChunkValidator
    ├── metadata.py     # ChunkMetadataBuilder
    ├── statistics.py   # ChunkStatistics
    └── pipeline.py     # ChunkingPipeline
└── embedding/
    ├── __init__.py
    ├── config.py       # EmbeddingConfig
    ├── models.py       # EmbeddingRecord, EmbeddingResult
    ├── providers.py    # EmbeddingProvider protocol + OpenAI, Ollama, Local adapters
    ├── cache.py        # InMemoryEmbeddingCache
    ├── batch.py        # BatchProcessor with retry & timeout
    ├── validation.py   # EmbeddingValidator
    ├── statistics.py   # EmbeddingStatistics
    └── service.py      # EmbeddingService orchestrator
```
```

## License

MIT
