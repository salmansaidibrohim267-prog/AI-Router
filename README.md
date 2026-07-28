# AI-Router Gateway

FastAPI-based intelligent AI model router with automatic task classification, provider management, health monitoring, circuit breaker, smart routing, streaming, benchmarking, and comprehensive observability (Prometheus + Grafana + Loki).

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI App  │────▶│  Classifier   │     │  Prometheus  │
└─────────────┘     │  (api.py)     │     │  (NLP/Keyword)│     │  :9090      │
                    │               │     └──────┬───────┘     └──────▲──────┘
                    │  /v1/chat     │            │                    │
                    │  /v1/embed    │     ┌──────▼───────┐           │ scrape
                    │  /health      │     │  AI Router    │           │
                    │  /models      │     │  (router.py)  │     ┌─────┴──────┐
                    │  /metrics     │     └──────┬───────┘     │  Grafana    │
                    │  /providers   │            │             │  :3000      │
                    │  /benchmark   │     ┌──────▼────────┐    └─────▲──────┘
                    │  /dashboard   │     │ProviderManager│          │
                    │  /costs       │     │ (manager.py)  │    ┌─────┴──────┐
                    │  /logs        │     └───┬───┬───┬───┬┘    │  Loki      │
                    └──────────────┘     ┌────┘   │   │   └──┐  │  :3100     │
                    logs/router.jsonl───▶│ Promtail  │       │  └─────▲──────┘
                                         ▼          ▼       ▼        │
                                    OpenRouter  Ollama  Groq    Gemini
```

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

## Configuration

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

## License

MIT
