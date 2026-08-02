<div align="center">

# 🤖 AI Router

### Production-grade AI Router platform for building scalable AI applications

**Multi-LLM Routing · RAG · MCP · Plugins · Distributed Architecture · Enterprise**

AI Router is an open-source gateway and orchestration platform that sits between your
application and the world of AI models — intelligently routing every request to the
right model, provider, and infrastructure, while handling security, observability,
scaling, and operations for you.

</div>

<p align="center">

![Version](https://img.shields.io/badge/version-v1.0.0--rc.1-8A2BE2)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-4477%20passed-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-98%25-28A745)
![Docker](https://img.shields.io/badge/docker-ghcr.io%2Fanomalyco%2Fai-router-2496ED?logo=docker&logoColor=white)
![CI](https://img.shields.io/github/actions/workflow/status/anomalyco/ai-router/ci.yml?branch=main&label=CI&logo=github)
![Release](https://img.shields.io/github/v/release/anomalyco/ai-router)
![Stars](https://img.shields.io/github/stars/anomalyco/ai-router?style=social)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)

</p>

<p align="center">
  <a href="#overview">📖 Overview</a> ·
  <a href="#why-choose-ai-router">🏆 Why AI Router</a> ·
  <a href="#key-features">✨ Features</a> ·
  <a href="#feature-matrix">📊 Feature Matrix</a> ·
  <a href="#architecture">🏗️ Architecture</a> ·
  <a href="docs/">📚 Docs</a> ·
  <a href="deployment/">☸️ Deployment</a> ·
  <a href="#whats-next">🚀 Get Started</a>
</p>

---

## 📦 Repository Highlights

| | |
| :--- | :--- |
| ⚡ **Intelligent Multi-LLM Routing** | Automatic task classification, smart provider scoring, weighted traffic distribution, circuit breakers and automatic failover |
| 🧠 **RAG & MCP Ready** | Retrieval-augmented generation and Model Context Protocol surfaces built into the platform core |
| 🧩 **Plugin Platform** | Signed, versioned, hot-reloadable plugins with a marketplace, sandboxing and lifecycle management |
| ☸️ **Cloud Native** | Kubernetes manifests, Helm chart, Terraform, Ansible and GitOps (ArgoCD) out of the box |
| 🔐 **Enterprise Security** | Audit chains, secret store (Vault/K8s/AWS/Azure/GCP), KMS/HSM key management, zero-trust enforcement |
| 📈 **Enterprise Observability** | SLO/SLI with error budgets, burn-rate alerting, Prometheus + Grafana + Loki + OpenTelemetry |
| 🏢 **Distributed Architecture** | Leader election, health monitoring, failover, autoscaling, rolling / blue-green / canary deployments |
| 💳 **Built-in Business Layer** | Usage-based billing, metered quotas, admin console and compliance reports (SOC 2, ISO 27001, GDPR, CCPA) |

> [!TIP]
> **New to AI Router?** Start with the [Overview](#overview) below, then follow the
> **Installation & Quick Start** guide in **Part 2** of this README to go from zero to
> your first routed request in under five minutes.

---

## 📖 Overview

### What is AI Router?

AI Router is a **production-grade, open-source AI gateway platform**. It decouples your
application from individual AI providers by acting as a single, intelligent entry point
for all model traffic — then routes, retries, falls back, meters, secures, observes and
scales every request.

It is not just a reverse proxy. AI Router is a **platform**: it ships with an API
layer, a routing engine, an orchestration engine for multi-agent workflows, a plugin
ecosystem, distributed cluster capabilities, and an enterprise operations layer —
**billing, admin, security, compliance, migrations, releases, and observability**.

### Why AI Router?

> [!IMPORTANT]
> Every LLM integration eventually asks the same questions: *Which provider? What
> happens when it fails? How do we bill per tenant? Who can see what? How do we scale?*
> AI Router was built to answer all of them — once.

### Problems AI Router Solves

| Problem | Traditional Approach | AI Router |
| :--- | :--- | :--- |
| **Provider lock-in** | Hardcoded SDK calls to one vendor | Multi-provider routing with a single API |
| **Downtime & flakiness** | Manual retries, sleep-and-hope | Health checks, circuit breakers, automatic failover |
| **Cost runaway** | Spreadsheets, shock on the invoice | Per-tenant metering, budgets, cost-aware routing |
| **Security sprawl** | Keys in env files, no audit trail | Centralised secret store, immutable audit chain, zero-trust |
| **Observability gaps** | "It worked yesterday" | SLOs, error budgets, burn-rate alerts, dashboards |
| **Scaling anxiety** | Throw more VMs at it | Cluster HA, autoscaling, GitOps-driven deployments |

### Target Audience

- **Platform & Infrastructure Engineers** who want a battle-tested gateway with Kubernetes, Helm, Terraform and GitOps support.
- **Backend / Full-Stack Engineers** building AI features who want one API for many models, with fallback and streaming.
- **AI / ML Engineers** running RAG pipelines, MCP servers and multi-agent orchestration in production.
- **Startups & Enterprises** needing tenant isolation, usage-based billing, audit and compliance.
- **DevOps / SRE teams** that live in dashboards, alerts and runbooks — and expect the same from their AI stack.

### Use Cases

| Use Case | Who | What They Get |
| :--- | :--- | :--- |
| 🏭 **Multi-provider API gateway** | Product teams | One endpoint, best-price routing, automatic failover |
| 📚 **RAG over private knowledge** | AI engineers | Retrieval layer, embeddings and provider routing for grounding |
| 🤝 **MCP tool surfaces** | Agent developers | Model Context Protocol endpoints with tool permissions |
| 🧩 **Plugin marketplaces** | SaaS vendors | Signed, versioned, isolated plugin distribution |
| 🏢 **Enterprise AI platform** | CTO / Platform teams | RBAC, audit chains, compliance reports, tenant billing |
| 🌍 **Global multi-region serving** | SRE teams | Distributed cluster, leader election, DR failover |

---

## 🏆 Why Choose AI Router

### AI Router vs. Traditional AI Integrations

| Capability | Traditional Integration | AI Router |
| :--- | :---: | :---: |
| Single unified API | ❌ | ✅ |
| Multiple providers behind one API | ❌ | ✅ |
| Health checks & circuit breaking | ❌ | ✅ |
| Automatic fallback / failover | ❌ | ✅ |
| Streaming support | ⚠️ per-provider | ✅ unified |
| Cost-aware routing & metering | ❌ | ✅ |
| Per-tenant quotas & billing | ❌ | ✅ |
| Secrets management | ⚠️ manual | ✅ Vault / K8s / AWS / Azure / GCP |
| Immutable audit chain | ❌ | ✅ |
| Zero-trust authorization | ❌ | ✅ |
| Prometheus / Grafana / Loki | ❌ | ✅ |
| SLOs, error budgets, burn rates | ❌ | ✅ |
| Plugin platform & marketplace | ❌ | ✅ |
| Distributed cluster & HA | ❌ | ✅ |
| GitOps / Helm / Terraform | ❌ | ✅ |

### Benefits

- **🚀 Ship faster** — implement a single API contract and let routing, retries and fallbacks be someone else's problem.
- **💰 Cut costs** — route by price and quality, meter usage per tenant, and enforce budgets automatically.
- **🛡️ Stay safe** — secrets never touch application code; every sensitive operation lands in a tamper-evident audit chain.
- **📈 Know everything** — dashboards, SLOs and burn-rate alerts arrive with the platform, not as a migration project.

### Scalability

AI Router scales **horizontally and vertically**:

- **Cluster mode** with leader election and lease-based takeover (Redis / K8s leases) for HA.
- **Autoscaling** driven by CPU, memory, queue length, request rate and token throughput.
- **Autoscaling-aware deployments** — rolling, blue-green and canary rollout strategies with traffic weighting.
- **HorizontalPodAutoscaler** manifests and **PDB** guarantees ship in `deployment/k8s/`.
- Stateless-by-design workers scale out behind a load balancer; state lives in Redis/SQLite.

### Reliability

- **Health monitoring** with SUSPECTED → FAILED state machines and no zombie auto-revives.
- **Circuit breakers** per provider and **weighted traffic distribution** that avoids unhealthy endpoints.
- **Smoke, rollback and verification tests** gate every deployment before traffic is accepted.
- **Quality gates** in CI: coverage ≥ 95%, p95 latency and error-rate thresholds, all tests green.
- **Signed, immutable releases** — artifact manifests are HMAC-signed; tampering breaks verification.
- **Migration tooling** with versioned, reversible schema migrations and dry-runs.

### Extensibility

- 🧩 **Plugins** — install, verify, enable, disable, reload, upgrade, rollback and uninstall at runtime.
- 🔌 **Provider plugins** — drop in a new LLM provider without touching router code.
- 🛠️ **Tool plugins** — calculator, filesystem, HTTP, search and custom tools with permission gating.
- 📦 **Publisher plugins** — extend the release pipeline to any channel.
- 🏗️ **Benchmark suites** — plug in custom suites alongside built-in throughput, latency, memory, CPU, concurrency, failover and RAG quality benchmarks.

> [!NOTE]
> <details>
> <summary><b>Why not roll your own router?</b> (click to expand)</summary>
>
> A hand-rolled integration looks cheap until it isn't: retries without circuit
> breakers amplify outages, keys leak into logs, one `requests.post()` per provider
> grows into a switchboard of bespoke error handling, and "we'll add observability
> later" becomes a six-month project. AI Router delivers the platform in one
> dependency — battle-tested, signed, documented and deployed.
>
> </details>

---

## ✨ Key Features

### 🤖 AI

- **Multi-LLM routing** with automatic task classification and provider scoring.
- **Weighted traffic distribution**, circuit breakers and automatic failover.
- **Streaming** chat completions and embeddings through a unified API.
- **Orchestration engine** — planner, agents, consensus, debate and reflection workflows.
- **Benchmarking built in** — throughput, latency, memory, CPU, concurrency, failover and RAG quality suites.

### 🧠 Knowledge

- **RAG-ready** retrieval and embeddings through the router API.
- **Retrieval quality benchmarking** (precision / recall / F1) in the benchmark suite.
- **Vector-friendly architecture** with Redis-backed distributed state.

### 🏢 Enterprise

- **Usage-based billing** — metering, quotas, invoices, MRR/ARR, coupons and webhooks.
- **Admin console** — settings, users, dashboards, system status and plugin management.
- **Compliance reports** — SOC 2, ISO 27001, GDPR and CCPA readiness views.

### 🔐 Security

- **Secret store** with six backends: environment, Vault, Kubernetes, AWS, Azure and Google.
- **KMS / HSM adapters** with key rotation, revocation and hardware-level wrapping.
- **AES-256-GCM envelope encryption** and field-level ciphering.
- **Immutable, hash-linked audit chain** with pruning that re-links and re-signs.
- **Zero-trust enforcement** — authenticate, authorize, tenant-check, session and evaluate.
- **Threat detection** — brute force, credential stuffing, token replay and anomaly signals.

### 📈 Observability

- **SLO / SLI tracking** with 30-day windows, error budgets and burn rates.
- **Burn-rate alerting** — warnings at 0.5×, pages at 2× budget consumption.
- **Prometheus metrics, Loki logs, OpenTelemetry traces.**
- **Provisioned Grafana dashboards** generated from code.

### ☸️ Cloud Native

- **Kubernetes** manifests, **Helm chart**, **Terraform** (ECS Fargate) and **Ansible** playbooks.
- **GitOps** with ArgoCD — self-healing, immutable tags, drift correction.
- **Twelve-factor** design: config from environment, stateless processes, logs to stdout.
- **Non-root, read-only-rootfs** container hardening with dropped capabilities.

### 🧩 Plugins

- **Plugin lifecycle** — install → verify → enable → disable → reload → upgrade → rollback → uninstall.
- **Signed plugin installs** and a **marketplace** registry.
- **Sandboxing and permission gating** for tool execution.

### 🏗️ Distributed

- **Cluster management** — join, leave, discover, rebalance, leader election.
- **Lease-based leadership** with Redis or Kubernetes coordination.
- **Failover and job rescheduling** across nodes.
- **Disaster recovery** with region promotion and demotion.

---

## 📊 Feature Matrix

| Capability | Category | Tier | Status |
| :--- | :--- | :---: | :---: |
| Multi-LLM routing & classification | AI | Core | ✅ GA |
| Fallback & circuit breaking | AI | Core | ✅ GA |
| Streaming responses | AI | Core | ✅ GA |
| Multi-agent orchestration | AI | Advanced | ✅ GA |
| Benchmark suites (7 kinds) | AI | Developer | ✅ GA |
| RAG retrieval & quality metrics | Knowledge | Advanced | ✅ GA |
| MCP surfaces | Knowledge | Advanced | 🚧 Beta |
| Usage-based billing & quotas | Enterprise | Advanced | ✅ GA |
| Admin console & system status | Enterprise | Advanced | ✅ GA |
| Compliance reports (SOC 2 / ISO 27001 / GDPR / CCPA) | Enterprise | Advanced | ✅ GA |
| Secret store (6 backends) | Security | Core | ✅ GA |
| KMS / HSM key management | Security | Advanced | ✅ GA |
| Immutable audit chain | Security | Advanced | ✅ GA |
| Zero-trust enforcement | Security | Advanced | ✅ GA |
| SLO / SLI with error budgets | Observability | Advanced | ✅ GA |
| Burn-rate alerting & dashboards | Observability | Advanced | ✅ GA |
| Prometheus / Grafana / Loki / OTel | Observability | Core | ✅ GA |
| Kubernetes + Helm + Terraform + Ansible | Cloud Native | Core | ✅ GA |
| GitOps (ArgoCD) with immutable tags | Cloud Native | Advanced | ✅ GA |
| Plugin platform & marketplace | Plugins | Advanced | ✅ GA |
| Distributed cluster & leader election | Distributed | Advanced | ✅ GA |
| Rolling / blue-green / canary deploys | Distributed | Advanced | ✅ GA |
| Disaster recovery & failover | Distributed | Advanced | ✅ GA |
| Signed releases & artifact manifests | Operations | Core | ✅ GA |

---

## 🏗️ Architecture

### High-Level Overview

AI Router is built as a **layered, modular platform** around a small, fast core:

1. **Edge & Gateway** — Traefik terminates TLS, applies rate limits and security headers.
2. **API Layer** — FastAPI surfaces `/v1/chat`, `/v1/embeddings`, health and admin endpoints.
3. **Core Engine** — task classification, provider scoring, weighted routing, circuit breaking, fallback and streaming.
4. **Platform Services** — security, observability, billing, plugins, migrations, release and deployment pipelines.
5. **Distributed Layer** — cluster membership, leader election, scheduling, failover and autoscaling.
6. **Provider Layer** — OpenAI, Anthropic, Google, OpenRouter, Ollama and custom providers behind one contract.

```mermaid
flowchart TB
    subgraph Clients["Clients"]
        A1["Web Apps"]
        A2["Mobile Apps"]
        A3["Agents / MCP"]
    end

    subgraph Edge["Edge & Gateway"]
        B1["Traefik — TLS · Rate Limit · Headers"]
    end

    subgraph API["API Layer — FastAPI"]
        C1["/v1/chat"]
        C2["/v1/embeddings"]
        C3["/health · /ready · /version"]
        C4["Admin & Billing APIs"]
    end

    subgraph Core["Core Engine"]
        D1["Classifier"]
        D2["Router & Scoring"]
        D3["Traffic Distribution"]
        D4["Circuit Breaker & Fallback"]
        D5["Streaming"]
        D6["Orchestration — Agents · Consensus · Debate"]
    end

    subgraph Platform["Platform Services"]
        E1["Security — Secrets · Audit · Zero-Trust"]
        E2["Observability — SLOs · Alerts · Metrics"]
        E3["Billing & Quotas"]
        E4["Plugins & Marketplace"]
        E5["Migrations & Release"]
        E6["Deployment & GitOps"]
    end

    subgraph Distributed["Distributed Layer"]
        F1["Cluster & Leader Election"]
        F2["Health & Failover"]
        F3["Scheduler"]
        F4["Autoscaling"]
        F5["Redis — State & Locks"]
    end

    subgraph Providers["Providers"]
        G1["OpenAI"]
        G2["Anthropic"]
        G3["Google"]
        G4["OpenRouter"]
        G5["Ollama / Local"]
        G6["Custom Plugins"]
    end

    A1 & A2 & A3 --> B1
    B1 --> C1 & C2 & C3 & C4
    C1 & C2 --> D1 --> D2 --> D3 --> D4 --> D5
    C4 --> E3
    D2 --> E1
    D5 --> E2
    D6 --> D2
    E1 & E2 --> E5
    E4 --> D2
    F1 & F2 & F3 & F4 <--> E1 & E2
    F5 <--> F1 & F4
    D3 --> G1 & G2 & G3 & G4 & G5 & G6
    G1 & G2 & G3 & G4 & G5 & G6 --> E2
```

### Component Descriptions

| Component | Module | Responsibility |
| :--- | :--- | :--- |
| **API Layer** | `app/main.py` | HTTP surface, auth, versioned endpoints |
| **Router & Scoring** | `app/router.py` | Provider selection by health, cost, latency and policy |
| **Traffic Distribution** | `app/traffic_distribution.py` | Weighted routing, circuit breakers, failover |
| **Orchestration** | `app/orchestration/` | Planner, agents, consensus, debate, reflection |
| **Security** | `app/security/` | Secrets, encryption, audit chain, zero-trust, threat detection |
| **Observability** | `app/observability/` | SLOs, error budgets, burn rates, alerts, dashboards |
| **Billing** | `app/billing/` | Metering, quotas, invoices, MRR/ARR |
| **Admin** | `app/admin/` | Console, settings, plugins, system status |
| **Plugins** | `app/plugins/` | Lifecycle, signing, marketplace, sandboxing |
| **Cluster** | `app/cluster/` | Membership, election, health, failover, autoscaling, deployments |
| **Releases** | `app/release/` | SemVer, changelog, signing, publishing |
| **Migrations** | `app/migrations/` | Versioned schema migrations with rollback |
| **Deployment** | `app/deploy/` | Quality gates, smoke tests, GitOps validation |

### Architecture Principles

1. **🔌 Provider abstraction everywhere** — every external dependency (provider, secret backend, transport, publisher) is behind an injectable interface. Nothing is hardwired.
2. **📦 Everything is a subsystem** — routing, security, billing, plugins: each lives in its own package with its own config, exceptions and tests. No god modules.
3. **🛡️ Secure by default** — deny-by-default authorization, signed releases, tamper-evident audit chains, non-root containers.
4. **📈 Observable by construction** — every subsystem emits metrics and events; SLOs and burn-rate alerts ship with the platform.
5. **☸️ Cloud native from day one** — GitOps, immutable tags, rolling deploys, HPA and PDB are part of the distribution, not afterthoughts.
6. **🧪 Tested at enterprise depth** — 4,475 tests passing (21 skipped), ≥ 95% coverage enforced per subsystem in CI.

> [!WARNING]
> The diagram above shows the *primary* request path. Advanced flows — multi-agent
> orchestration, plugin hook points, cluster failover — are covered in depth in the
> [Architecture guide](docs/architecture.md) and the subsystem docs.

### Request Flow

```mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant GW as Gateway (Traefik)
    participant API as API Layer
    participant SEC as Security
    participant RTR as Router Core
    participant DIST as Traffic Distribution
    participant P as Provider (OpenAI / Anthropic / …)
    participant OBS as Observability

    App->>GW: POST /v1/chat
    GW->>GW: TLS · Rate limit · Headers
    GW->>API: forward request
    API->>SEC: authenticate & authorize
    SEC-->>API: token valid
    API->>RTR: classify task & score providers
    RTR->>DIST: select provider by health/cost/latency
    DIST->>P: send request (with timeout)
    alt provider healthy
        P-->>DIST: response / stream
    else provider failed
        DIST->>P: fallback provider #2
        P-->>DIST: response
    end
    DIST-->>API: response
    API-->>GW: response
    GW-->>App: 200 OK
    DIST->>OBS: record outcome (good/bad, latency)
    OBS->>OBS: update SLI · burn rate · dashboards
```

---

## 🚀 What's Next

You now have the full picture of what AI Router is, why it exists, what it can do,
and how it is architected. In **Part 2** of this README you will go hands-on: install
AI Router with Docker, Kubernetes or Helm in minutes, run your first routed request,
explore the SDK, and take your first look at the admin console, dashboards and
cluster mode.

**Next: Installation & Quick Start**
# Installation & Quick Start

This guide gets AI Router running on your machine in minutes — locally, in Docker,
with Docker Compose, or on Kubernetes — and then walks through configuration and
the project layout.

---

## 📋 Requirements

### Operating Systems

| Platform | Support | Notes |
| :--- | :---: | :--- |
| **Linux** (Ubuntu 22.04+, Debian 12+, RHEL 9+) | ✅ **Recommended** | Production target; all tooling tested here |
| **macOS** (13+ Ventura, Intel & Apple Silicon) | ✅ Supported | Use Homebrew Python; Docker Desktop for containers |
| **Windows** | ⚠️ Via WSL2 | Native Windows is not supported — use WSL2 or containers |

> [!NOTE]
> AI Router ships as a **Linux-first** platform. For development on macOS or Windows,
> use the Docker image (`ghcr.io/anomalyco/ai-router`) — the only fully supported
> runtime path on those platforms.

### Python Versions

| Version | Support |
| :--- | :---: |
| Python **3.12** | ✅ Recommended (used for CI and the Docker image) |
| Python 3.10 / 3.11 | ✅ Supported |
| Python 3.13 / 3.14 | ✅ Supported |
| Python < 3.10 | ❌ Not supported (`requires-python = ">=3.10"`) |

### Docker & Kubernetes

| Tool | Minimum | Recommended |
| :--- | :--- | :--- |
| **Docker** | 24.x | 27.x+ (BuildKit enabled) |
| **Docker Compose** | v2.20+ | v2.30+ |
| **Kubernetes** | 1.26 | 1.29+ (manifests use `apps/v1`, `autoscaling/v2`, `networking.k8s.io/v1`) |
| **Helm** | 3.12+ | 3.16+ (only needed for the Helm chart) |

### CPU / RAM Recommendations

| Deployment | CPU | RAM | Notes |
| :--- | :--- | :--- | :--- |
| 🧪 Development / demo | 2 vCPU | 4 GB | Python venv or single container |
| 🏢 Production (single host) | 4 vCPU | 8 GB | Compose stack with Redis + monitoring |
| 🌍 Production (cluster) | 8+ vCPU | 16 GB+ | K8s with 2+ replicas, HPA headroom |
| 🦙 Local models (Ollama) | 8 vCPU | 16–32 GB | Ollama container limits in `docker-compose.yml` |

---

## 🛠️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/anomalyco/ai-router.git
cd ai-router
```

### 2. Install Python

Make sure you have Python 3.10+ (3.12 recommended):

```bash
python3 --version   # e.g. Python 3.12.7
```

> [!TIP]
> On macOS: `brew install python@3.12`. On Ubuntu: `sudo apt install python3.12 python3.12-venv`.

### 3. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# or on Windows (WSL2):
# source .venv/bin/activate
```

> [!IMPORTANT]
> Always use a virtual environment. AI Router pins its dependencies in
> `requirements.txt` and installs cleanly into an isolated `.venv`.

### 4. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs the full runtime stack: FastAPI + uvicorn, Pydantic v2, httpx,
PyYAML, Prometheus client, Redis, OpenTelemetry, and pytest for development.

### 5. Verify the installation

```bash
PYTHONPATH=. python -m app.main --help
```

---

## ⚡ Quick Start

### Run AI Router locally

```bash
PYTHONPATH=. python -m app.main
```

You should see uvicorn bind to `http://0.0.0.0:8000`.

### Verify the installation

```bash
# Liveness + per-provider health
curl http://localhost:8000/health
curl http://localhost:8000/health/providers

# Build metadata
curl http://localhost:8000/version
```

Example output:

```json
{"status": "ok", "providers": 5, "models": 12}
```

### Interactive API documentation (Swagger)

AI Router exposes FastAPI's interactive docs out of the box:

| URL | Purpose |
| :--- | :--- |
| `http://localhost:8000/docs` | Swagger UI — try every endpoint from your browser |
| `http://localhost:8000/redoc` | ReDoc — reference-style API documentation |
| `http://localhost:8000/openapi.json` | Machine-readable OpenAPI spec |

### Send your first routed request

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello AI Router!"}]
  }'
```

> [!NOTE]
> The router requires at least one healthy provider. Configure API keys via
> environment variables (see [Configuration](#configuration)) or the provider
> files in `config/`.

---

## 🐳 Docker

### Dockerfile explanation

The repository ships a **multi-stage `Dockerfile`** (and a production variant at
`deployment/Dockerfile.prod`):

| Stage | Base | Purpose |
| :--- | :--- | :--- |
| `builder` | `python:3.12-slim` | Installs pinned dependencies into a user-local wheel cache |
| `runtime` | `python:3.12-slim` | Minimal image — deps, `app/`, config, non-root user, healthcheck |

Hardening included in the image:

- 🔒 **Non-root user** `ai-router` (no shell)
- 🩺 **HEALTHCHECK** on `/health` every 30s
- 🏷️ **OCI labels** — version, build date, git commit, source, license
- 📄 **Build metadata** written to `/app/.meta/build.json` (served by `/version`)

### Build

```bash
docker build \
  --build-arg VERSION=1.0.0-rc.1 \
  --build-arg GIT_COMMIT=$(git rev-parse HEAD) \
  --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  -t ai-router:1.0.0-rc.1 .
```

### Run

```bash
docker run -d --name ai-router \
  -p 8000:8000 \
  --env-file .env \
  -v "$PWD/config":/app/config:ro \
  -v "$PWD/logs":/app/logs \
  ai-router:1.0.0-rc.1
```

### Volumes

| Mount | Purpose |
| :--- | :--- |
| `./config:/app/config:ro` | Runtime configuration (`providers.yaml`, `models.yaml`, …) — read-only |
| `./logs:/app/logs` | Application logs (consumed by Promtail) |
| `redis_data` (compose) | Redis persistence (queues, locks, distributed state) |
| `prometheus_data` / `grafana_data` / `loki_data` (compose) | Observability persistence |

> [!WARNING]
> Never mount secrets into the config volume. Use the secret store or
> environment variables (see [Secrets Management](#secrets-management)).

### Networking

- The container listens on **port 8000** (`EXPOSE 8000`).
- Standalone: publish with `-p 8000:8000`.
- In the compose stack, services share the **`ai-router-net`** bridge network and
  reach each other by service name (`redis`, `prometheus`, `grafana`…).
- In production, **Traefik** terminates TLS in front of the container.

---

## 🧩 Docker Compose

### Complete example

This is the core stack — application + Redis + monitoring. The repository ships a
fuller version in `docker-compose.yml` (with Loki, Promtail, OpenTelemetry,
Ollama and distributed workers behind profiles).

```yaml
# docker-compose.yml
services:
  ai-router:
    build:
      context: .
      args:
        VERSION: "1.0.0-rc.1"
    image: ai-router:1.0.0-rc.1
    container_name: ai-router
    profiles: ["dev", "monitoring", "production", "minimal"]
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - CONFIG_DIR=/app/config
      - REDIS_URL=redis://default:${REDIS_PASSWORD:-}@redis:6379/0
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "python", "-c", "import http.client; http.client.HTTPConnection('localhost', 8000).request('GET', '/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - ai-router-net

  redis:
    image: redis:7.2-alpine
    container_name: ai-router-redis
    command: ["redis-server", "--requirepass", "${REDIS_PASSWORD:-}", "--appendonly", "yes"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
    restart: unless-stopped
    networks:
      - ai-router-net

  prometheus:
    image: prom/prometheus:v2.53.0
    container_name: prometheus
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=30d"
    restart: unless-stopped
    networks:
      - ai-router-net

  grafana:
    image: grafana/grafana:11.1.0
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - prometheus
    restart: unless-stopped
    networks:
      - ai-router-net

volumes:
  redis_data:
  prometheus_data:
  grafana_data:

networks:
  ai-router-net:
    driver: bridge
```

### Explanation

| Piece | What it does |
| :--- | :--- |
| **Profiles** | `dev`, `monitoring`, `production`, `distributed`, `minimal` — run only what you need |
| **healthcheck** | Docker marks the app healthy only when `/health` responds |
| **depends_on** | Redis starts (and is healthy) before the router connects |
| **Shared network** | Services resolve each other by name: `redis`, `prometheus`, `grafana` |
| **Named volumes** | Persist Redis, Prometheus and Grafana state across restarts |
| **env_file** | `.env` supplies API keys and `REDIS_PASSWORD` without baking them into the file |

Run it:

```bash
docker compose --profile production up -d
docker compose ps
curl http://localhost:8000/health
```

> [!TIP]
> The full stack in the repository adds **Loki + Promtail** (logs) and the
> **OpenTelemetry collector** (traces) behind the `monitoring` profile, plus
> **Ollama** for local models and **distributed workers/scheduler** behind the
> `distributed` profile.

---

## ☸️ Kubernetes

All manifests live in `deployment/k8s/` and are applied via **kustomize**:

```bash
kubectl apply -k deployment/k8s/
kubectl -n ai-router rollout status deployment/ai-router
```

### Namespace

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: ai-router
```

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-router
  namespace: ai-router
  labels:
    app: ai-router
    version: 1.0.0-rc.1
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ai-router
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  template:
    metadata:
      labels:
        app: ai-router
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: ai-router
          image: ghcr.io/anomalyco/ai-router:1.0.0-rc.1
          ports:
            - name: http
              containerPort: 8000
          livenessProbe:
            httpGet: { path: /health, port: http }
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet: { path: /health, port: http }
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            requests: { cpu: 250m, memory: 256Mi }
            limits: { cpu: "1", memory: 512Mi }
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
```

### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: ai-router
  namespace: ai-router
spec:
  selector:
    app: ai-router
  ports:
    - name: http
      port: 8000
      targetPort: http
  type: ClusterIP
```

### Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ai-router
  namespace: ai-router
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  rules:
    - host: ai-router.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: ai-router
                port: { name: http }
  tls:
    - hosts: [ai-router.example.com]
```

### Scaling

Scaling is handled automatically — **HPA** scales 2–10 replicas on CPU (70%) and
memory (80%), and a **PodDisruptionBudget** guarantees at least one replica during
voluntary disruptions:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ai-router
  namespace: ai-router
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ai-router
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: { type: Utilization, averageUtilization: 70 }
    - type: Resource
      resource:
        name: memory
        target: { type: Utilization, averageUtilization: 80 }
```

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: ai-router
  namespace: ai-router
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: ai-router
```

> [!NOTE]
> Kubernetes is the recommended production path. For GitOps-driven rollouts,
> `deployment/gitops/apps/ai-router/application.yaml` syncs these manifests via
> **ArgoCD** with immutable image tags — `latest` is rejected by design.

---

## ⚙️ Configuration

### Environment Variables

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `CONFIG_DIR` | Directory holding `*.yaml` config files | `config/` |
| `LOG_LEVEL` | Log verbosity | `INFO` |
| `REDIS_URL` | Redis connection for distributed state | — (Redis optional) |
| `REDIS_PASSWORD` | Redis password (compose) | — |
| `OPENAI_API_KEY` | OpenAI provider key | — |
| `ANTHROPIC_API_KEY` | Anthropic provider key | — |
| `GOOGLE_API_KEY` | Google provider key | — |
| `OPENROUTER_API_KEY` | OpenRouter provider key | — |
| `DISTRIBUTED_MODE` | Enable worker mode (`1`) | `0` |
| `SCHEDULER_MODE` | Enable scheduler mode (`1`) | `0` |
| `PORT` | HTTP listen port | `8000` |

Subsystem configuration uses scoped prefixes (all with `from_env()` support):

| Prefix | Subsystem | Examples |
| :--- | :--- | :--- |
| `SEC_*` | Security | `SEC_SIGNING_KEY`, `SEC_SIEM_URL` |
| `REL_*` | Release management | `REL_INITIAL_VERSION`, `REL_REGISTRY`, `REL_PUBLISHERS` |
| `MIG_*` | Migrations | `MIG_DRIVER`, `MIG_DATABASE_PATH`, `MIG_AUTO_MIGRATE` |
| `OBS_*` | Observability | `OBS_DEFAULT_SLO`, `OBS_WINDOW_SECONDS`, `OBS_PAGE_THRESHOLD` |
| `DEP_*` | Deployment pipeline | `DEP_TARGET_VERSION`, `DEP_MIN_COVERAGE`, `DEP_ENVIRONMENT` |
| `CL_*` | Cluster | `CL_NODE_ID`, `CL_ENV` |

### Configuration Hierarchy

Configuration resolves in this order (later sources win):

```mermaid
flowchart LR
    A["Code defaults"] --> B["config/*.yaml"]
    B --> C["Environment variables"]
    C --> D["Runtime overrides"]
```

1. **Code defaults** — safe built-in defaults baked into every subsystem config.
2. **Config files** — `config/providers.yaml`, `config/models.yaml`,
   `config/orchestrator.yaml`, `config/plugins.yaml`.
3. **Environment variables** — override anything at deploy time (Twelve-Factor).
4. **Runtime overrides** — tenant/database-backed settings where supported.

> [!IMPORTANT]
> Configuration is strictly validated: unknown keys raise `TypeError` instead of
> silently passing. A typo like `DEP_TARGET_VRESION` fails fast — usually in CI.

### Example `.env`

```bash
# --- Core --------------------------------------------------------
CONFIG_DIR=/app/config
LOG_LEVEL=INFO
PORT=8000

# --- Providers ----------------------------------------------------
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
OPENROUTER_API_KEY=sk-or-...

# --- Distributed ---------------------------------------------------
REDIS_URL=redis://default:CHANGE_ME@redis:6379/0
REDIS_PASSWORD=CHANGE_ME

# --- Subsystems ----------------------------------------------------
REL_INITIAL_VERSION=1.0.0-rc.1
OBS_DEFAULT_SLO=99.9
MIG_DRIVER=sqlite
MIG_DATABASE_PATH=/app/data/migrations.db
DEP_ENVIRONMENT=staging
```

### Secrets Management

> [!WARNING]
> **Never** commit `.env`, API keys, or signing keys to the repository. Add
> `.env` to `.gitignore` and rotate any leaked key immediately.

- **Development** — environment variables are fine; keep them in a local,
  untracked `.env`.
- **Production** — use the built-in **secret store** (`app/security/secrets.py`)
  with one of six backends: Vault, Kubernetes secrets, AWS Secrets Manager,
  Azure Key Vault, Google Secret Manager, or the environment.
- **Encryption at rest** — secrets are wrapped with AES-256-GCM envelope
  encryption; keys are managed by **KMS / HSM** adapters with rotation and
  revocation.
- **Signing keys** — release signing keys (`REL_SIGNING_KEY`) are injected as CI
  secrets and used only by the release workflow.

---

## 📁 Folder Structure

```
ai-router/
├── app/                        # Core platform (Python package)
│   ├── main.py                 # Entrypoint (uvicorn app)
│   ├── router.py               # Intelligent routing & provider scoring
│   ├── classifier.py           # Task classification (NLP / keyword)
│   ├── traffic_distribution.py # Weighted routing, circuit breakers, failover
│   ├── orchestration/          # Multi-agent: planner, consensus, debate, reflection
│   ├── gateway/                # Request pipeline, quotas, rate limiting
│   ├── providers/              # Provider adapters behind one contract
│   ├── rag/                    # Retrieval-augmented generation
│   ├── mcp/ + mcp_integration/ # Model Context Protocol surfaces
│   ├── knowledge/              # Knowledge layer (retrieval, reranker, citations)
│   ├── memory/                 # Memory & context management
│   ├── security/               # Secrets, audit chain, zero-trust, threat detection
│   ├── observability/          # SLOs, burn rates, alerts, dashboards
│   ├── billing/                # Metering, quotas, invoices, MRR/ARR
│   ├── admin/                  # Admin console, settings, system status
│   ├── plugins/ + plugin/      # Plugin platform (lifecycle, signing, marketplace)
│   ├── cluster/                # Distributed: election, health, failover, autoscale
│   ├── distributed/            # Distributed workers & scheduler
│   ├── tenancy/                # Tenant isolation & resolution
│   ├── auth/                   # Authentication & API keys
│   ├── release/                # SemVer, changelog, signing, publishing
│   ├── migrations/             # Versioned schema migrations + rollback
│   ├── deploy/                 # Quality gates, smoke tests, GitOps validation
│   └── …                       # costs, caching, events, metrics, storage, tools…
├── benchmarks/                 # Benchmark runner + suite registry
│   └── suites/                 # throughput · latency · memory · cpu · concurrency · failover · rag
├── classifier/                 # Embedding classifier plugin
├── config/                     # YAML config: providers, models, orchestrator, plugins
├── deployment/                 # Production assets
│   ├── k8s/                    # Kubernetes manifests (Deployment, HPA, PDB, Ingress)
│   ├── helm/ai-router/         # Helm chart
│   ├── terraform/              # AWS ECR + ECS Fargate infrastructure
│   ├── ansible/                # VM deployment playbooks
│   └── gitops/                 # ArgoCD application manifests
├── docs/                       # Guides: architecture, api, security, ops, …
├── plugins/                    # Sample plugins (cache, guardrails, logging, translation)
├── providers/                  # Custom provider plugins
├── prometheus/                 # Prometheus config
├── grafana/                    # Provisioned dashboards + datasources
├── loki/                       # Loki log-aggregation config
├── promtail/                   # Log shipping config
├── otel/                       # OpenTelemetry collector config
├── traefik/                    # Traefik dynamic config (TLS, middleware)
├── scripts/                    # Ops helpers: deploy, rollback, backup, verify…
├── tests/                      # 4,475+ tests across subsystems
├── dist/release/               # Signed release artifacts (v1.0.0-rc.1)
├── Dockerfile                  # Multi-stage production image
├── docker-compose.yml          # Full stack with profiles
├── pyproject.toml              # Packaging + tool config (ruff, black, mypy, pytest)
├── requirements.txt            # Pinned dependencies
├── CHANGELOG.md                # Generated from conventional commits
└── README.md                   # This documentation
```

| Directory | Purpose |
| :--- | :--- |
| `app/` | Everything that *is* AI Router — each subsystem is an isolated package with its own config, exceptions and tests |
| `benchmarks/` | In-process benchmark suites (no external services required) |
| `config/` | YAML configuration consumed at runtime |
| `deployment/` | Every artifact needed to ship it: Docker, compose, k8s, Helm, Terraform, Ansible, GitOps |
| `docs/` | The full documentation set — architecture, API, SDK, plugins, ops, security |
| `plugins/` + `providers/` | Drop-in extension points for tools, guardrails and providers |
| `prometheus/` · `grafana/` · `loki/` · `promtail/` · `otel/` · `traefik/` | The complete observability and edge stack |
| `scripts/` | Operational runbooks as scripts (`deploy.sh`, `rollback.sh`, `backup.sh`…) |
| `tests/` | The regression suite — run `python -m pytest tests/ -q` |
| `dist/release/` | Signed, immutable release artifacts |

> [!TIP]
> `logs/` and `memory.db` appear at runtime — they are generated, not part of the
> source tree, and can be ignored/backed up per the ops runbooks.

---

## 🚀 What's Next

You can now run AI Router locally, in containers and on Kubernetes, and you know
exactly where everything lives. The next part of this README goes inside the
engine: how requests are classified, scored and routed across providers, how the
routing pipeline, retries and fallbacks work, and how you can tune it.

**Next: API & Routing Engine**
# API & Routing Engine

This part covers the REST API surface, the full endpoint reference, and the
adaptive routing engine that sits behind every request — scoring, ranking,
fallback, retries, circuit breakers and cost optimization.

---

## 🌐 REST API

### Overview

AI Router exposes an **OpenAI-compatible** API. If you can talk to OpenAI's
Chat Completions API, you can talk to AI Router — the payloads are identical,
so existing SDKs, tools and prompts work without changes.

| Aspect | Detail |
| :--- | :--- |
| **Base URL** | `http://localhost:8000` |
| **Content type** | `application/json` (SSE for streaming) |
| **Versioned paths** | `/v1/chat/completions`, `/v1/embeddings`, `/v1/orchestrate`, … |
| **OpenAPI** | `/docs` (Swagger UI), `/redoc`, `/openapi.json` |
| **Errors** | RFC 7807-style JSON: `{"error": "...", "detail": "..."}` |
| **Tracing** | Every request gets a `X-Request-ID` (echoed back) |
| **Rate limit headers** | `X-RateLimit-Limit`, `X-RateLimit-Reset` on every response |

### Authentication

| Method | Header | Used for |
| :--- | :--- | :--- |
| **API key** | `X-API-Key: <key>` | Service-to-service and SDK calls (primary) |
| **Bearer token** | `Authorization: Bearer <token>` | Same, when a bearer-only client is used |

- Keys are issued by the auth subsystem (`app/auth/`) with **TTL** (default 30
  days) and optional **scopes** — a key can be restricted to specific endpoints.
- Missing credentials → `401`; key without required scope → `403`.
- **OpenAI-compatible path**: the router passes through provider keys it
  consumes internally — the *client* never sees them; you only ever present your
  own router key.

> [!TIP]
> For local development without a key, set `auth.enabled=false` in config or
> use the operator key from the environment (see `docs/security.md`).

### Example

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-router-..." \
  -H "X-Request-ID: req-123" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain quantum entanglement in one sentence."}
    ],
    "temperature": 0.7,
    "max_tokens": 200,
    "stream": false
  }'
```

---

## 📡 API Endpoints

### Health & Observability

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Liveness — service up, providers summary |
| `GET` | `/ready` | Readiness — 200 only when config loaded and ≥1 provider available |
| `GET` | `/health/providers` | Per-provider health snapshot |
| `GET` | `/health/providers/{name}` | Single provider health + details |
| `GET` | `/metrics` | Prometheus metrics endpoint |
| `GET` | `/version` | Build metadata (version, commit, build date) |
| `GET` | `/` | Service index / capabilities summary |
| `GET` | `/runtime/health` · `/runtime/leader` · `/runtime/workers` · `/runtime/queue` · `/runtime/events` | Distributed runtime state |

### Inference

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/v1/chat/completions` | Chat completion (OpenAI-compatible, streaming supported) |
| `POST` | `/v1/embeddings` | Text embeddings |
| `POST` | `/v1/orchestrate` | Multi-agent orchestration (planner → executor) |
| `POST` | `/v1/agents` | Single agent run with tools |
| `POST` | `/v1/workflow` | Multi-step workflow execution |
| `POST` | `/v1/consensus` | Consensus across N models on the same prompt |
| `POST` | `/v1/debate` | Debate between two models with rebuttal rounds |

### Providers & Models

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/providers` | Registered providers + status |
| `GET` | `/providers/{name}/models` | Models offered by one provider |
| `GET` | `/providers/custom` | Custom (user-defined) providers |
| `GET` | `/models` | All models across providers |
| `GET` | `/models/{task}` | Models eligible for a task (`chat`, `coding`, `architecture`, `analysis`) |
| `GET` | `/capabilities` · `/capabilities/{provider}` · `/capabilities/{provider}/{model}` | Function-calling, vision, context windows… |

### Statistics, Logs & Costs

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/stats` | Aggregate statistics (requests, tokens, costs, errors) |
| `GET` | `/stats/providers` · `/stats/providers/{name}` · `/stats/models/{p}/{m}` · `/stats/tasks` · `/stats/errors` | Filtered statistics |
| `POST` | `/stats/reset` | Reset statistics |
| `GET` | `/logs` · `/logs/{request_id}` · `DELETE /logs` | Request logs (traceability) |
| `GET` | `/analytics/providers` · `/analytics/providers/{name}` | Long-window analytics |
| `GET` | `/costs` · `/costs/{provider}` | Cost tracking per provider |
| `GET` | `/tokens` · `/tokens/estimate` | Token usage + estimation |
| `GET` | `/cache/stats` · `POST /cache/clear` | Response cache |

### Operations

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/config` | Loaded configuration |
| `POST` | `/reload-config` | Hot-reload YAML config without restart |
| `GET` | `/benchmark` | Stored benchmark results |
| `GET` | `/benchmark/live` · `/benchmark/live/{provider}` · `POST /benchmark/live/reset` | Live in-process benchmarks |
| `GET` | `/dashboard` | Runtime dashboard summary |
| `GET` | `/distribution` · `POST /distribution/rebalance` · `/distribution/reset` · `/distribution/config` | Traffic distribution control |
| `GET` | `/classifier` | Classifier diagnostics (task → label) |
| `GET` | `/plugins` · `/plugins/reload` · `/plugins/enable` · `/plugins/disable` · `/plugins/events` | Plugin platform |

### Tasks & Approval

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/tasks` · `/tasks/orchestrate` | Create tasks / orchestration jobs |
| `GET` | `/tasks` · `/tasks/{id}` · `/tasks/{id}/graph` | List / inspect / dependency graph |
| `DELETE` | `/tasks/{id}` · `POST /tasks/{id}/cancel` | Cancel tasks |
| `GET` | `/tasks/queue/depth` | Distributed queue depth |
| `POST` | `/approval/checkpoints` | Create human-in-the-loop checkpoint |
| `POST` | `/approval/checkpoints/{id}/approve` · `/…/reject` | Resolve checkpoints |
| `GET` | `/approval/pending` · `/approval/checkpoints` | Pending / all checkpoints |

### Knowledge & Vector

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` / `GET` / `PUT` / `DELETE` | `/knowledge/collections` · `/knowledge/collections/{id}` | Collection CRUD |
| `POST` / `GET` / `PUT` / `DELETE` | `/knowledge/documents` · `/documents/{id}` | Document CRUD |
| `POST` | `/knowledge/documents/upload` · `/knowledge/documents/import` | Upload / bulk import |
| `POST` | `/knowledge/chunk` · `/chunk/preview` · `GET/DELETE /knowledge/chunks/...` | Chunking pipeline |
| `POST` | `/knowledge/embed` · `/knowledge/embed/batch` | Embedding generation |
| `POST` / `GET` / `DELETE` | `/vector/collections` · `/vector/upsert` · `/vector/search` · `/vector/statistics` | Vector store operations |

> [!NOTE]
> `app/api.py` is the single source of truth for this surface — regenerate the
> endpoint tables from `/openapi.json` if the surface evolves.

---

## ⚙️ Routing Engine

### Architecture

Every request flows through a three-stage pipeline:

```mermaid
flowchart LR
    A["Request"] --> B["Classifier"]
    B -->|"task: chat / coding / architecture / analysis"| C["Routing Engine"]
    C -->|"candidate providers scored"| D["Traffic Distribution"]
    D -->|"weighted selection"| E["Provider Adapter"]
    E --> F["Response"]
    E -.->|"failure"| G["Retry + Backoff"]
    G -.->|"still failing"| H["Fallback chain"]
    H -.->|"all fail"| I["Circuit Breaker opens"]
```

1. **Classifier** (`app/classifier.py`) — maps the prompt to a **task** type.
   The task determines which models are eligible.
2. **Routing Engine** (`app/routing.py`) — scores every eligible provider across
   seven dimensions and ranks them.
3. **Traffic Distribution** (`app/traffic_distribution.py`) — converts scores
   into selection weights, applies canary/A-B/shadow rules, then picks a winner.

### Scoring dimensions

Each provider is scored **0–100 per dimension**; the weighted sum ranks
candidates (higher is better):

| Dimension | What it measures |
| :--- | :--- |
| **Latency** | EWMA of recent latency (lower EWMA → higher score) |
| **Reliability** | Rolling success rate × 100 |
| **Cost** | `max(0, 100 − (cost / PERFECT_COST) × 100)` |
| **Config** | Base score from `config/models.yaml` |
| **Preference** | Request-level `user_preference` override |
| **Context** | Fits the model's context window (`−5000` if it doesn't) |
| **Recency** | Consecutive-selection bonus / penalty (stickiness) |

Dynamic signals are folded in at scoring time: **reputation score** (trend-aware),
**live benchmark score** (rolling window), and a **circuit breaker multiplier**
(`×0` when a provider's circuit is open). Each retry attempt penalizes
alternative providers, biasing toward stability under sustained failure.

### Routing strategies (optimization modes)

| Mode | Behavior | Weight emphasis |
| :--- | :--- | :--- |
| `balanced` *(default)* | Equal latency/reliability, moderate cost | lat .25 · rel .25 · cost .15 |
| `quality` | Maximize reliability/reputation | rel .35 · ctx .15 |
| `cheapest` | Minimize cost | cost .40 |
| `fastest` | Minimize latency | lat .40 |

Set it per request via `optimization_mode`, or per system via the routing
config. A `BALANCED` request spreads load; a `CHEAPEST` request ignores speed
and hunts for bargains.

### Provider priority

Each provider in `config/providers.yaml` declares a `priority`:

```yaml
providers:
  - name: openrouter
    priority: 10        # ← lowest number = highest priority
  - name: ollama
    priority: 20
  - name: openai
    priority: 30
```

Priority acts as the **config-score input** to the ranking (highest-priority
eligible provider starts with an advantage) and is the tie-breaker when scores
are equal. It is *not* a hard pin — a healthy, fast, cheap fallback can outrank
a slow high-priority provider.

### Fallback

Each task in `config/models.yaml` declares a primary provider and an ordered
fallback chain:

```yaml
chat:
  primary:
    provider: ollama
    model: qwen2.5-coder:7b
  fallback:
    - provider: ollama
      model: llama3.2:latest     # second choice
```

When the primary fails, the router walks the fallback chain in order; every
transition emits a `fallback.triggered` event for observability. If **no**
provider in the chain can serve the request, the router returns `503 No healthy
provider` (via `NoHealthyProviderError`).

### Retry

- **Max retries**: 3 (per provider attempt), configurable per provider.
- **Backoff**: exponential with **jitter** — `base_delay × 2^attempt ± jitter`
  to avoid thundering-herd retries.
- **Selective**: only *retryable* errors retry (timeouts, 429, 5xx). Non-retryable
  errors (validation, 400) fail immediately.
- Retries are accounted in metrics and visible in `/logs`.

### Circuit Breaker

Per-provider circuit breaker (`app/providers/manager.py`):

| State | Condition | Effect |
| :--- | :--- | :--- |
| **closed** | normal | requests flow |
| **open** | ≥ **5 consecutive failures** | all traffic diverted, provider scores ×0 |
| **half-open** | after **60 s** recovery timeout | 1 probe request allowed |
| **closed** | ≥ **3 half-open successes** | traffic restored |

Open circuits auto-recover; state is exposed via `/health/providers/{name}` and
Prometheus `circuit_breaker_state`.

### Load balancing

Traffic distribution converts ranked candidates into **normalized weights**:

- **Starvation prevention** — every eligible provider keeps a minimum weight
  floor, so losers still receive occasional traffic and health probes.
- **Canary** — a provider marked canary is capped at `max_traffic_share`
  (default 5%) until promoted.
- **A/B testing** — request segments can be pinned to specific providers.
- **Shadow traffic** — clone requests to a shadow provider with zero impact on
  the response; ideal for validating a new model in production.
- **Rebalance** — `POST /distribution/rebalance` re-normalizes weights from live
  scores without restart.

### Cost optimization

- **Live cost scoring** — every success records token counts; the routing
  engine scores against a normalized "perfect cost" baseline so cheap providers
  are favored in `cheapest` mode.
- **Token accounting** (`app/costs.py`) — prompt/completion/cache tokens tracked
  per provider and model, exposed via `/costs` and `/tokens/estimate`.
- **Model cost overrides** (`MODEL_COST_OVERRIDES`) — known-priced models are
  scored precisely; unknown models fall back to per-provider pricing tables.
- **Cost-aware selection** — combined with circuit breakers and reputation,
  `cheapest` mode still avoids unhealthy or unreliable budget providers.

---

## 🔌 Providers

Every provider implements the same async contract (`app/providers/base.py`):
`chat`, `stream_chat`, `embeddings`, `health_check`, `list_models`.

| Provider | Adapter | Default endpoint | Status |
| :--- | :--- | :--- | :--- |
| **OpenAI** | `app/providers/openai.py` | `https://api.openai.com/v1` | ✅ enabled in config |
| **Claude (Anthropic)** | `app/providers/anthropic.py` | `https://api.anthropic.com/v1` | ✅ adapter ready |
| **Gemini (Google)** | `app/providers/google.py` | `https://generativelanguage.googleapis.com/v1beta` | ✅ adapter ready |
| **Ollama (local)** | `app/providers/ollama.py` | `http://localhost:11434` | ✅ enabled in config |
| **OpenRouter** | `app/providers/openrouter.py` | `https://openrouter.ai/api/v1` | ✅ enabled in config |
| **Mistral** | `app/providers/mistral.py` | `https://api.mistral.ai/v1` | ✅ adapter ready |
| **Groq** | `app/providers/groq.py` | `https://api.groq.com/openai/v1` | ✅ adapter ready |
| **Azure OpenAI** | via OpenAI-compatible adapter | `https://<resource>.openai.azure.com` | ⚙️ custom config |

Enable a provider in `config/providers.yaml` (set `enabled: true`) and supply
its API key environment variable — the router picks it up on restart or
`POST /reload-config`.

### OpenAI

```yaml
- name: openai
  display_name: "OpenAI"
  api_key_env: "OPENAI_API_KEY"        # env var holding the key
  base_url: "https://api.openai.com/v1"
  timeout: 60.0
  max_retries: 3
  enabled: true
  priority: 30
  models:
    - "gpt-4o"
    - "gpt-4o-mini"
    - "gpt-3.5-turbo"
```

### Claude

```yaml
- name: anthropic
  api_key_env: "ANTHROPIC_API_KEY"
  base_url: "https://api.anthropic.com/v1"
  enabled: true
  priority: 40
  models: ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]
```

### Gemini

```yaml
- name: google          # "gemini" is auto-aliased to "google"
  api_key_env: "GOOGLE_API_KEY"
  base_url: "https://generativelanguage.googleapis.com/v1beta"
  enabled: true
  priority: 50
  models: ["gemini-1.5-pro", "gemini-1.5-flash"]
```

### Ollama (local)

```yaml
- name: ollama
  api_key_env: null                       # no key — local
  base_url: "http://localhost:11434"
  timeout: 120.0                          # generous for local models
  enabled: true
  priority: 20
  models: ["qwen2.5:3b", "llama3.1:8b", "mistral:7b", "codellama:7b"]
```

> [!TIP]
> The compose stack ships an `ollama` service with a shared volume — pull
> models once (`docker compose exec ollama ollama pull qwen2.5:3b`) and every
> container reuses them.

### Azure OpenAI

There is no dedicated Azure adapter — Azure's endpoint is **OpenAI-compatible**,
so configure it as a custom provider:

```yaml
- name: azure-openai
  api_key_env: "AZURE_OPENAI_API_KEY"
  base_url: "https://my-resource.openai.azure.com/openai/v1"
  timeout: 60.0
  max_retries: 3
  enabled: true
  priority: 25
  models: ["gpt-4o", "gpt-4o-mini"]
```

### OpenRouter

OpenRouter is treated like any other provider — a single key unlocks hundreds
of models:

```yaml
- name: openrouter
  api_key_env: "OPENROUTER_API_KEY"
  base_url: "https://openrouter.ai/api/v1"
  enabled: true
  priority: 10
  models:
    - "anthropic/claude-3.5-sonnet"
    - "google/gemini-pro"
```

### Custom Provider SDK

Two options for your own provider:

**1. YAML-only (zero code).** Any OpenAI-compatible endpoint works via config —
point `base_url` anywhere (Azure, Together, Fireworks, self-hosted vLLM…).

**2. Python plugin.** Subclass the contract and register it:

```python
from app.providers.base import BaseProvider
from app.models import ChatRequest, ChatResponse, HealthCheckResponse

class MyProvider(BaseProvider):
    async def chat(self, request: ChatRequest) -> ChatResponse:
        ...  # your protocol here
    async def health_check(self) -> HealthCheckResponse:
        ...
```

Drop the file in `providers/` and add the provider to `providers.yaml`; the
provider **discovery** layer (`app/providers/discovery.py`) loads it on
startup or `POST /reload-config`.

---

## 🎬 Streaming

Set `"stream": true` in `/v1/chat/completions`. The router streams the response
as **Server-Sent Events** (`text/event-stream`), OpenAI-style:

```
data: {"choices":[{"index":0,"delta":{"role":"assistant","content":""}}]}
data: {"choices":[{"index":0,"delta":{"content":"Hello"}}]}
data: {"choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

Behavior notes:

- **Live failover during stream** — if the active provider dies mid-stream, the
  router re-routes through the ranking engine to the next candidate; the client
  sees a seamless continuation.
- **Timeouts** — stream capped at `max_tokens × 0.1` seconds (min 120 s); on
  expiry a `"finish_reason":"timeout"` chunk is emitted, then `[DONE]`.
- **Cancellation** — client disconnect produces `"finish_reason":"cancelled"`.
- **Headers** — `Cache-Control: no-cache`, `X-Accel-Buffering: no` so proxies
  don't buffer the stream.
- **Metrics** — streaming chunks are not cached; non-streaming responses are
  cached 300 s in the response cache.

---

## ⚠️ Error Handling

Errors are returned as JSON with an HTTP status; the router attaches your
`X-Request-ID` so you can correlate with `/logs/{request_id}`.

| HTTP | Condition | Example body |
| :--- | :--- | :--- |
| `400` | Validation failure / bad payload | `{"error": "Validation error", "detail": "..."}` |
| `401` | Missing / invalid API key | `{"error": "Unauthorized", "detail": "..."}` |
| `403` | Key valid, scope denied | `{"error": "Forbidden", "detail": "..."}` |
| `404` | Unknown provider, model, task | `{"error": "… not found", "detail": "…"}` |
| `413` | Body exceeds limit | `{"error": "Request too large", "limit_bytes": 1000000}` |
| `429` | Rate limit hit | `{"error": "Rate limit exceeded", "retry_after": 60}` + `Retry-After` header |
| `502` | All providers failed / upstream error | `{"error": "Bad gateway", "detail": "…"}` |
| `503` | No healthy provider (circuits open) | `{"error": "Service unavailable", "detail": "…"}` |
| `504` | Provider timeout | `{"error": "Gateway timeout", "detail": "…"}` |
| `500` | Internal error (never leaks stack traces) | `{"error": "Internal server error"}` |

Gateway-specific exceptions (`app/gateway/exceptions.py`) map 1:1 to these
codes: `RateLimitExceededError`, `QuotaExceededError`, `UpstreamError`,
`AuthenticationFailedError`, `ForbiddenError`, `TenantIsolationError`, etc.

**Retry guidance for clients:**

```text
429  → wait `Retry-After` seconds, then retry (idempotent)
502  → retry after short backoff (router already retried upstream 3×)
503  → retry later; the breaker is cooling down (≈60 s)
```

---

## 💻 SDK Example

The Python package doubles as a client — import the router directly in-process,
or talk to a deployed instance over HTTP (any language).

### Python

In-process (import the package as a library):

```python
import asyncio
from app.router import AIRouter
from app.models import ChatRequest

async def main():
    router = AIRouter()
    await router.initialize()

    request = ChatRequest(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Explain quantum entanglement in one sentence."}],
    )
    response = await router.chat(request)
    print(response.choices[0].message.content)

    await router.close()

asyncio.run(main())
```

> [!NOTE]
> A ready-to-use singleton is also exported as `from app.router import router`.

Over HTTP (OpenAI-compatible — works with `openai` SDK too):

```python
import httpx

client = httpx.Client(base_url="http://localhost:8000")

resp = client.post(
    "/v1/chat/completions",
    headers={"X-API-Key": "sk-router-..."},
    json={
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello!"}],
        "stream": False,
    },
)
print(resp.json()["choices"][0]["message"]["content"])
```

Streaming variant:

```python
import httpx

with httpx.stream(
    "POST",
    "http://localhost:8000/v1/chat/completions",
    headers={"X-API-Key": "sk-router-..."},
    json={"model": "gpt-4o-mini",
          "messages": [{"role": "user", "content": "Count to 5."}],
          "stream": True},
) as r:
    for line in r.iter_lines():
        if line.startswith("data: ") and line != "data: [DONE]":
            print(line[6:])
```

### JavaScript

```javascript
const res = await fetch("http://localhost:8000/v1/chat/completions", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": "sk-router-...",
  },
  body: JSON.stringify({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: "Hello!" }],
    stream: true,
  }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const events = buffer.split("\n\n");
  buffer = events.pop(); // keep the partial event
  for (const evt of events) {
    if (evt.startsWith("data: [DONE]")) return;
    const data = JSON.parse(evt.replace("data: ", ""));
    process.stdout.write(data.choices?.[0]?.delta?.content ?? "");
  }
}
```

### cURL

```bash
# Non-streaming
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-router-..." \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Streaming (SSE)
curl -N http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-router-..." \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Count to 5."}],
    "stream": true
  }'

# Embeddings
curl -s http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-router-..." \
  -d '{"model": "text-embedding-3-small", "input": "Hello world"}'

# Multi-agent orchestration
curl -s http://localhost:8000/v1/orchestrate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-router-..." \
  -d '{"goal": "Design a load balancer", "max_steps": 5}'
```

---

## 🚀 What's Next

The router decides *where* requests go; the knowledge layer decides *what* they
know. The next part of this README covers retrieval-augmented generation — the
knowledge/collections API, document ingestion, chunking, embedding, the vector
store, and how citations ground every answer.

**Next: Knowledge & Intelligence**
# Knowledge & Intelligence

This part covers the retrieval side of the platform: the RAG pipeline, document
ingestion and chunking, embeddings and the vector store, semantic and hybrid
search, reranking, context assembly, conversation memory, citations and
evaluation — plus the Model Context Protocol (MCP) tool layer and the plugin
SDK that extends it.

---

## 🧠 RAG

### Overview

AI Router ships a full **retrieval-augmented generation** stack
(`app/rag/pipeline.py`). A RAG request answers a question using your knowledge
base instead of the model's parametric memory — grounded, current, and citable.

| Capability | Detail |
| :--- | :--- |
| **Modes** | single-shot `generate`, `stream`, async `generate_async`, `batch_generate` |
| **Caching** | context-hash keyed response cache (identical queries skip the pipeline) |
| **Fallback** | graceful degradation when retrieval or the LLM fails |
| **Sources** | knowledge collections, vector store, MCP servers, conversation memory |
| **Output** | answer + query analysis + retrieved context + citations + confidence + latency breakdown |

### Pipeline

```mermaid
flowchart LR
    Q["RAG request"] --> C{"cache hit?"}
    C -->|yes| R["cached response"]
    C -->|no| QP["Query Processor<br/>expansion · analysis"]
    QP --> RT["Retrieval Orchestrator<br/>semantic + hybrid + MCP"]
    RT --> CB["Context Builder<br/>token-budget assembly"]
    CB --> PB["Prompt Builder<br/>+ conversation history"]
    PB --> LLM["LLM provider"]
    LLM --> CI["Citation Engine"]
    CI --> OUT["Answer + citations + metrics"]
    RT -.->|"retrieval failure"| FB["Fallback answer"]
    LLM -.->|"provider failure"| FB
```

Stages, in order:

1. **Query processor** — expands/analyzes the query before retrieval.
2. **Retrieval orchestrator** — pulls candidate chunks (top-N, rerank top-N).
3. **Context builder** — fits the best chunks into the token budget.
4. **Prompt builder** — assembles system prompt, context, conversation history.
5. **LLM generation** — routed through the provider ranking engine.
6. **Citation engine** — attributes claims back to source chunks.

---

## 📄 Document Pipeline

Ingestion lives in `app/knowledge/ingestion/` and is exposed via the
`/knowledge/documents/...` API.

```mermaid
flowchart LR
    A["Upload / import"] --> L["Loaders<br/>txt · md · mdx · pdf · json"]
    L --> CL["Cleaner<br/>BOM · unicode · control chars"]
    CL --> D["Deduplication"]
    D --> LG["Language detection"]
    LG --> M["Metadata enrichment"]
    M --> V["Validation"]
    V --> S["Store + index"]
```

| Stage | Implementation | Notes |
| :--- | :--- | :--- |
| **Loaders** | `TextLoader`, `MarkdownLoader`, `PDFLoader` (+ `DocumentLoader` protocol for custom formats) | `load(path)` and `load_bytes(data, filename)` |
| **Cleaning** | `TextCleaner` | strips BOM, normalizes unicode/newlines/tabs, removes control chars |
| **Deduplication** | `DuplicateDetector` | avoids double-ingesting near-identical content |
| **Language** | `LanguageDetector` | enables language-aware chunking/search later |
| **Metadata** | `MetadataBuilder` | document-level metadata + tags API |
| **Validation** | document validators | rejects malformed content before indexing |

Entry points:

```bash
# Upload a file (multipart)
curl -X POST http://localhost:8000/knowledge/documents/upload \
  -H "X-API-Key: sk-router-..." \
  -F "file=@manual.pdf" -F "collection_id=col_1"

# Bulk import (JSON body)
curl -X POST http://localhost:8000/knowledge/documents/import \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"collection_id": "col_1", "documents": [{"title": "...", "content": "..."}]}'
```

---

## ✂️ Chunking

Chunking splits documents into retrievable units (`app/knowledge/chunking/`).

### Strategy

- **Recursive splitting** (default) — breaks text along structural boundaries
  (paragraphs → sentences → fixed-size) so chunks stay coherent.
- **Token-aware** — chunk boundaries respect token estimates, not raw character
  counts (`HeuristicTokenEstimator`).
- **Metadata** — every chunk carries `chunk_index`, source document, position.

### Tuning knobs

| Setting | Default | Env var | Meaning |
| :--- | :--- | :--- | :--- |
| `chunk_size` | 1000 | `CHUNK_SIZE` | target tokens per chunk |
| `chunk_overlap` | 200 | `CHUNK_OVERLAP` | overlap to preserve context across boundaries |
| `min_chunk_size` | 100 | `MIN_CHUNK_SIZE` | chunks smaller than this are merged |
| `max_chunk_size` | 2000 | `MAX_CHUNK_SIZE` | hard ceiling per chunk |

The chunking pipeline (`ChunkingPipeline`) validates every chunk and records
statistics; the API exposes preview before committing:

```bash
# Preview chunking without persisting
curl -X POST http://localhost:8000/knowledge/chunk/preview \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"text": "…long document…", "chunk_size": 1000, "chunk_overlap": 200}'

# Persist chunks
curl -X POST http://localhost:8000/knowledge/chunk \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"document_id": "doc_1"}'
```

> [!TIP]
> Rule of thumb: `chunk_size ≈ 10–15%` of the target model's context window,
> overlap ≈ 20%. Shorter chunks retrieve more precisely; longer chunks give the
> model more context per retrieval.

---

## 🔢 Embedding

Embeddings convert chunks into vectors (`app/knowledge/embedding/`).

- **Provider abstraction** — `create_embedding_provider()` returns an
  `EmbeddingProvider` for your configured vendor (OpenAI-compatible by default);
  model selected via config.
- **Batching** — `BatchProcessor` chunks work into configurable batches with
  **retry + exponential backoff** for transient failures.
- **Caching** — an `EmbeddingCache` dedupes embedding work: identical text is
  embedded once.
- **Validation & stats** — vector dimension/length checks, per-model statistics.

```bash
# Single chunk
curl -X POST http://localhost:8000/knowledge/embed \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"chunk_id": "chunk_1"}'

# Batch
curl -X POST http://localhost:8000/knowledge/embed/batch \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"chunk_ids": ["chunk_1", "chunk_2", "chunk_3"]}'
```

---

## 🗄️ Vector Store

Vectors are stored behind a pluggable backend (`app/knowledge/vector_store/`).

| Backend | Env | When to use |
| :--- | :--- | :--- |
| `memory` *(default)* | `VECTOR_BACKEND=memory` | dev, tests, single-node demos |
| **Qdrant** | `VECTOR_BACKEND=qdrant` + `QDRANT_URL`, `QDRANT_API_KEY` | production-scale, gRPC option |
| **Chroma** | `VECTOR_BACKEND=chroma` | lightweight embedded store |
| **pgvector** | `VECTOR_BACKEND=pgvector` + `PGVECTOR_DSN` | Postgres-centric stacks |
| **Redis Vector** | `VECTOR_BACKEND=redis_vector` | when Redis is already in the stack |

- **Distance metric**: `cosine` by default (`VECTOR_DISTANCE`).
- Collections, upsert, search and statistics via `/vector/collections`,
  `/vector/upsert`, `/vector/search`, `/vector/statistics`.

```bash
curl -X POST http://localhost:8000/vector/search \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"collection": "docs", "vector": [...], "top_k": 10}'
```

---

## 🔍 Semantic Search

Pure vector search (`app/retrieval/service.py` + `similarity.py`):

- Cosine similarity against the collection, with **ranking**, **filtering**
  (metadata/tags), **normalization** and **pagination**.
- **Query expansion** (`query_expansion.py`) optionally broadens the query to
  catch paraphrases.
- Strengths: captures *meaning* ("who won the cup" ≈ "championship victor").
- Weaknesses: misses exact identifiers — product codes, error strings, version
  numbers.

---

## 🔀 Hybrid Search

`HybridSearch` (`app/retrieval/hybrid.py`) combines semantic vectors with a
classic **BM25 inverted index**, then fuses both rankings.

```mermaid
flowchart LR
    Q["Query"] --> SEM["Semantic search<br/>embedding + cosine"]
    Q --> KW["BM25 keyword index"]
    SEM --> N["Score normalization"]
    KW --> N
    N --> F["Fusion<br/>weighted_sum · rrf · combsum · combmnz"]
    F --> RK["Reranker"]
    RK --> OUT["Ranked chunks"]
```

| Fusion strategy | How it combines | Best for |
| :--- | :--- | :--- |
| `weighted_sum` *(default)* | normalized scores summed | balanced results |
| `rrf` | reciprocal-rank fusion (rank-based, scale-free) | heterogeneous scores |
| `combsum` | sum of similarity scores | dense-vector dominated |
| `combmnz` | sum of normalized zero-mean scores | mixed corpora |

The keyword index (`BM25InvertedIndex`) is updated live via
`index_document()` / `remove_document()` as documents flow through the
pipeline.

---

## 📏 Reranking

Retrieved candidates are re-ranked (`app/reranker/`) before context assembly.
The pipeline retrieves wide (top-50) and re-ranks to top-10 — the standard
two-stage recipe.

| Provider | Default model / behavior | When to use |
| :--- | :--- | :--- |
| `rule_based` *(default)* | heuristic scoring, zero dependencies | out-of-the-box |
| `cross_encoder` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | best precision, needs model download |
| `ensemble` | weighted blend (`RERANKER_ENSEMBLE_WEIGHTS`) | production tuning |

| Setting | Default | Env |
| :--- | :--- | :--- |
| `top_k_retrieve` | 50 | `RERANKER_TOP_K_RETRIEVE` |
| `top_k_rerank` | 10 | `RERANKER_TOP_K_RERANK` |
| `top_k_return` | 10 | `RERANKER_TOP_K_RETURN` |
| batch size / max length | 32 / 512 | `RERANKER_BATCH_SIZE`, `RERANKER_MAX_LENGTH` |
| cache | 1 h TTL, 10 k entries | `RERANKER_CACHE_ENABLED` / `_TTL` / `_MAX_SIZE` |
| calibration | min-max | `RERANKER_CALIBRATION` |

---

## 🧩 Prompt Context Builder

`ContextBuilder` (`app/rag/context_builder.py`) assembles the final context
window:

- **Token-budgeted**: fills the budget with the highest-ranked chunks; chunks
  that don't fit are dropped, never truncated mid-chunk.
- **Ordering**: `build()` keeps retrieval order; `build_sorted()` preserves
  source order for narrative coherence.
- **Separators**: chunk separators are token-counted so the budget is exact.
- Output is a `ContextAssembly` (chunks + total tokens) handed to the prompt
  builder alongside conversation history.

```mermaid
flowchart LR
    A["Ranked chunks"] --> B["Score-ordered loop"]
    B --> C{"fits budget?"}
    C -->|yes| D["include + count tokens"]
    C -->|no| E["drop chunk"]
    D --> F["ContextAssembly<br/>chunks · total_tokens"]
    E --> B
```

---

## 💬 Conversation Memory

`app/memory/` provides session-aware conversation memory.

- **Sessions** — `create_session` / `get_session` / `delete_session`,
  message history with `get_messages_for_request` (auto-truncated to context).
- **Scoring** — `MemoryScorer` ranks memories by a weighted blend of
  **similarity · recency · access frequency · importance · confidence**.
- **Summarization** — `Summarizer` compresses old turns so long conversations
  stay within budget (with `MemorySummarizationError` guardrails).
- **Lifecycle** — `prune_old_sessions()`, TTL policies, deduplication.
- **MCP bridge** — memory is callable as tools by agents via
  `MCPIntegrationCoordinator` (`store_memory`, `retrieve_memories`,
  `delete_memory`), with metrics per tool call.

---

## 📚 Citation Engine

Every RAG answer is attributable (`app/citations/`):

```mermaid
flowchart LR
    ANS["Generated answer"] --> AT["Sentence-level attribution"]
    AT --> SC["Confidence scoring"]
    SC --> VT["Validation<br/>source IDs · consistency"]
    VT --> FM["Formatting"]
    FM --> OUT["Cited answer"]
```

| Component | Role |
| :--- | :--- |
| `AttributionStrategy` | maps each claim/sentence to source chunks |
| `CitationScorer` | per-citation confidence, configurable attribution threshold |
| `CitationValidator` | rejects dangling source IDs, validates the result set |
| `FormatFactory` | renders citations in the requested format |

Supported formats: **numeric, IEEE, APA, MLA, markdown, JSON** (default via
`default_format`). Formatting is pluggable — add a `CitationFormatter` to get
another style.

---

## 🎯 Knowledge Evaluation

RAG quality is measured, not assumed (`app/evaluation/`). Evaluator registry
(defaults): `retrieval`, `rag`, `citation`, `memory`, `mcp_tools`.

| Evaluator | Metrics |
| :--- | :--- |
| **retrieval** | `recall@k`, `precision@k`, `mrr`, `average_precision`, `ndcg@k` |
| **rag** | `faithfulness`, `groundedness`, `hallucination_rate` |
| **citation** | citation validity & coverage scores |
| **memory** | memory recall quality |
| **mcp_tools** | tool-call success rates |

Default quality gates (`EvaluationConfig`):

| Metric | Gate |
| :--- | :--- |
| `faithfulness` | ≥ 0.70 |
| `groundedness` | ≥ 0.70 |
| `hallucination_rate` | ≤ 0.30 |

Benchmarks run through `BenchmarkRunner` with built-in internal datasets and
JSON-imported custom datasets; an **orchestrator** + **gates** enforce
thresholds (fail → alert), and reports are generated for review. RAG answers
carry `confidence` so you can gate downstream actions.

---

## 🔌 MCP — Model Context Protocol

### Architecture

AI Router is both an **MCP host** (calls external tool servers) and an **MCP
server** (exposes its own knowledge/memory/citations to other hosts).

```mermaid
flowchart LR
    subgraph Agent["Agent / Host"]
        A1["Router MCP surface<br/>knowledge · memory · citations"]
    end
    subgraph Router["AI Router"]
        M["MCP Manager"]
        C1["MCP Client · stdio"]
        C2["MCP Client · http"]
        C3["MCP Client · sse / websocket"]
        I["MCP Integration Coordinator<br/>retriever · memory · citations"]
        R["RAG + Routing engine"]
    end
    A1 --> M
    M --> C1 & C2 & C3
    C1 --> S1["Tool server A"]
    C2 --> S2["Tool server B"]
    C3 --> S3["Tool server C"]
    I --> R
    M --> I
```

| Component | File | Role |
| :--- | :--- | :--- |
| `MCPManager` + `ConnectionManager` | `app/mcp/manager.py` | register/connect/lifecycle of server connections |
| `MCPClient` | `app/mcp/client.py` | connect, initialize, ping, discover, shutdown, tool calls |
| Transports | `app/mcp/transports.py` | **stdio**, **http**, **sse**, **websocket** |
| Protocol | `app/mcp/protocol.py` | JSON-RPC framing |
| `ServerDiscovery` | `app/mcp/discovery.py` | `tools/list`, `resources/list`, `prompts/list` |
| Sessions & auth | `app/mcp/session.py`, `auth.py` | per-server sessions, auth handshakes |
| Coordinator | `app/mcp_integration/coordinator.py` | merges MCP tools into RAG answers |
| Memory adapter | `app/mcp_integration/memory_adapter.py` | memory as tools |
| Citations | `app/mcp_integration/citations.py` | cite MCP-sourced content |

Configured via `MCPConfig` (`from_env`): server list, transport, timeouts; the
integration layer is namespaced under `MCPI_*` (`MCPI_RESOURCE_PREFIX=mcp://`,
`MCPI_CITATION_RESOURCE_PREFIX=mcp://`).

### Tool Discovery

1. **Connect** — client dials the server over its transport.
2. **Initialize** — JSON-RPC `initialize` handshake → server info
   (name/version/capabilities) + `ServerDiscovery` snapshot.
3. **Enumerate** — `tools/list` (schema per tool: name, description,
   parameters), `resources/list` (URI-addressable content), `prompts/list`.
4. **Cache** — discovered tools are cached per connection and served to the
   router's tool registry, ready for agent calls.

```mermaid
sequenceDiagram
    participant R as Router
    participant D as ServerDiscovery
    participant S as MCP Server
    R->>D: discover()
    D->>S: initialize (JSON-RPC)
    S-->>D: serverInfo + capabilities
    D->>S: tools/list
    S-->>D: tool schemas
    D->>S: resources/list · prompts/list
    S-->>D: resource & prompt catalog
    D-->>R: cached tool registry
```

### Tool Execution

```mermaid
sequenceDiagram
    participant A as Agent / RAG
    participant C as Coordinator
    participant M as MCP Manager
    participant S as Tool Server
    A->>C: answer(query, tools=["retrieve", "calc"])
    C->>M: get client
    M->>S: tools/call {name, args}
    S-->>M: tool result
    M-->>C: normalized result
    C->>C: attach context (mcp:// resources)
    C-->>A: cited, tool-grounded answer
```

- Tool calls run over JSON-RPC with per-call `record_tool_call()` metrics and
  session-scoped auth; failures surface as `MCPConnectionError` /
  `MCPTransportError` with clean retry semantics.
- Results are wrapped with `mcp://` resource URIs so the citation engine can
  attribute them.

---

## 🧩 Plugin SDK

Two layers: the **platform plugin API** (`app/plugins/sdk.py` — what plugins
import) and the **host runtime** (`app/plugins/manager.py`,
`app/plugin/loader.py`).

### Lifecycle

```mermaid
stateDiagram-v2
    [*] --> installed: on_install
    installed --> enabled: on_enable
    enabled --> disabled: on_disable
    disabled --> enabled: on_enable
    enabled --> enabled: on_reload
    enabled --> upgraded: on_upgrade
    upgraded --> enabled
    enabled --> [*]: on_uninstall
    [*] --> [*]: shutdown
```

Every plugin subclasses `Plugin` and overrides hooks:

| Hook | Called when |
| :--- | :--- |
| `on_install` / `on_uninstall` | plugin added/removed from the platform |
| `on_enable` / `on_disable` | toggled at runtime |
| `on_reload` | hot-reload with the previous version |
| `on_upgrade` | new version installed over an old one |
| `shutdown` | process teardown |

### Runtime guarantees

| Feature | Implementation |
| :--- | :--- |
| **Sandbox** | CPU/memory/timeout limits, **filesystem allow-list**, **network deny-by-default** (`Sandbox`) |
| **Permissions** | `context.check_permission()` / `require_permission()` — fine-grained resource scopes |
| **Signing** | HMAC-SHA256 signatures over canonical JSON (`signing.py`); `verify_or_raise` on load |
| **Versioning** | semver compare/parse, upgrade checks |
| **Registry & watcher** | drop-in directory watching, reload on change |
| **Events & DI** | typed event bus (`emit`), dependency injection |
| **Metrics** | per-plugin stats exposed to Prometheus |

### A minimal plugin

```python
from app.plugins.sdk import Plugin, PluginContext

class LogEveryRequest(Plugin):
    name = "logging"
    version = "1.0.0"

    async def on_enable(self, ctx: PluginContext) -> None:
        ctx.require_permission("logging", "write")
        self.hook = ctx.emit("request.completed", level="debug")

    async def on_disable(self, ctx: PluginContext) -> None:
        ctx.log("plugin disabled")
```

Sample plugins ship in `plugins/`: `cache`, `guardrails`, `logging`,
`translation`, `example`.

---

## 🛍️ Plugin Marketplace

`app/plugins/marketplace.py` is the plugin catalog — search, install, update,
rate, and verify.

| Feature | Detail |
| :--- | :--- |
| **Entries** | id, name, version, author, downloads, ratings (`average_rating`) |
| **Catalog ops** | `add`, `remove`, `get`, search/list |
| **Install pipeline** | fetch → **signature verify** → version check → sandbox → enable |
| **Updates** | semver comparison decides upgrade vs. fresh install |
| **Governance** | audit-logged via `marketplace.entry_added` events |

Runtime control via the plugin API:

```bash
curl -X POST http://localhost:8000/plugins/enable -H "Content-Type: application/json" \
  -H "X-API-Key: sk-router-..." -d '{"name": "guardrails"}'
curl -X POST http://localhost:8000/plugins/disable -H "Content-Type: application/json" \
  -H "X-API-Key: sk-router-..." -d '{"name": "translation"}'
curl -X POST http://localhost:8000/plugins/reload -H "X-API-Key: sk-router-..."
curl http://localhost:8000/plugins -H "X-API-Key: sk-router-..."   # list
```

---

## 💡 Examples

### End-to-end RAG in Python

```python
import asyncio
from app.rag import RAGPipeline
from app.rag.models import RAGRequest

async def main():
    pipeline = RAGPipeline()          # wires orchestrator + context + LLM + citations

    response = await pipeline.generate(RAGRequest(
        query="How do I configure the circuit breaker threshold?",
        retrieval_top_k=20,
        rerank_top_k=5,
        context_token_budget=1500,
    ))
    print(response.answer)
    for s in response.sources:
        print(f"- {s.get('title', s.get('id', 'source'))} (score={s.get('score'):.3f})")
    print(f"confidence={response.confidence} "
          f"retrieval={response.retrieval_latency_ms:.0f}ms "
          f"total={response.total_latency_ms:.0f}ms")

asyncio.run(main())
```

### Knowledge + vector via cURL

```bash
# Ingest → chunk → embed → search
curl -X POST localhost:8000/knowledge/documents/import \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"collection_id": "col_1", "documents": [{"title": "Runbook", "content": "…"}]}'

curl -X POST localhost:8000/knowledge/embed/batch \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"collection_id": "col_1"}'

curl -X POST localhost:8000/vector/search \
  -H "Content-Type: application/json" -H "X-API-Key: sk-router-..." \
  -d '{"collection": "col_1", "query": "circuit breaker threshold", "top_k": 5}'
```

### MCP tool call

```python
import asyncio
from app.mcp.manager import ConnectionManager
from app.mcp.config import MCPConfig

async def main():
    mgr = ConnectionManager(MCPConfig.from_env())
    client = mgr.register("weather", {"transport": "http", "url": "http://weather-tools:8001"})
    await mgr.connect_all()

    await client.initialize()
    await client.discover()                # full discovery: tools, resources, prompts
    tools = await client.list_tools()
    print("discovered:", [t["name"] for t in tools])

    result = await client.call_tool("get_forecast", {"city": "Berlin"})
    print(result)

    await mgr.disconnect_all()

asyncio.run(main())
```

### Hybrid search + rerank

```python
from app.retrieval.hybrid import HybridSearch
from app.retrieval.models import SearchQuery

searcher = HybridSearch()
searcher.index_document("d1", "Qdrant is a vector database with gRPC support.")
searcher.index_document("d2", "pgvector adds vectors to PostgreSQL.")

response = await searcher.search(SearchQuery(
    text="vector database in postgres",
    top_k=5,
    fusion_strategy="rrf",          # or weighted_sum / combsum / combmnz
))
for hit in response.results:
    print(hit.id, round(hit.score, 3))
```

---

## 📐 Mermaid Diagrams

All diagrams above are rendered inline (most README viewers support Mermaid):

| # | Diagram | Location |
| :--- | :--- | :--- |
| 1 | RAG pipeline flow | [RAG overview](#-rag) |
| 2 | Document ingestion pipeline | [Document Pipeline](#-document-pipeline) |
| 3 | Hybrid search + fusion | [Hybrid Search](#-hybrid-search) |
| 4 | Context budget assembly | [Prompt Context Builder](#-prompt-context-builder) |
| 5 | Citation engine flow | [Citation Engine](#-citation-engine) |
| 6 | MCP host/server architecture | [MCP — Architecture](#-mcp--model-context-protocol) |
| 7 | Tool discovery sequence | [Tool Discovery](#tool-discovery) |
| 8 | Tool execution sequence | [Tool Execution](#tool-execution) |
| 9 | Plugin lifecycle state machine | [Plugin SDK](#-plugin-sdk) |

### End-to-end knowledge flow (summary)

```mermaid
flowchart TD
    subgraph Ingest["Ingestion"]
        UP["Upload / import"] --> IN["Clean · dedupe · language"]
        IN --> CH["Chunk (size/overlap)"]
        CH --> EMB["Embed (batch, cached)"]
        EMB --> VS["Vector store"]
        CH --> BM["BM25 index"]
    end
    subgraph Query["Runtime"]
        Q["Question"] --> HS["Hybrid search"]
        HS --> RK["Rerank"]
        RK --> CTX["Context builder"]
        CTX --> MEM["Memory + MCP tools"]
        MEM --> GEN["Generate"]
        GEN --> CIT["Cite + validate"]
        CIT --> ANS["Answer"]
    end
    VS --> HS
    BM --> HS
    EV["Evaluation gates<br/>faithfulness · recall@k"] -.-> ANS
```

---

## ✅ Best Practices

| Area | Practice |
| :--- | :--- |
| **Chunking** | Size to ~10–15% of context; keep ~20% overlap; prefer recursive over fixed-size for prose |
| **Embeddings** | Batch + cache; pin one embedding model per collection so vectors stay comparable |
| **Vector backend** | Start `memory`, move to Qdrant (gRPC) before production traffic |
| **Search** | Always use hybrid (BM25 + semantic); fusion `rrf` is robust when score scales differ |
| **Reranking** | Retrieve wide (50) → rerank narrow (10); enable the cross-encoder for precision-critical apps |
| **Context budget** | Give the context builder a real budget (`context_token_budget`) — don't stuff the window |
| **Memory** | Enable summarization + pruning; score with recency/access weights for long sessions |
| **Citations** | Never surface `hallucination_rate > 0.3`; validate source IDs before showing citations |
| **Evaluation** | Run retrieval + RAG eval on every knowledge-base change; gate deploys on gates |
| **MCP** | Prefer stdio for local servers, HTTP/SSE for remote; scope each server's auth |
| **Plugins** | Require signatures for marketplace installs; run untrusted plugins in the sandbox with network denied |

---

## 🚀 What's Next

The stack is built and intelligent — the last part is shipping and running it.
The next part of this README covers production deployment, Docker Compose
profiles, Kubernetes and GitOps rollouts, backup/restore, observability
(SLOs, Prometheus, Grafana, Loki, OpenTelemetry), security hardening, and the
operational runbooks.

**Next: Deployment & Operations**
# Deployment & Operations

This part covers shipping AI Router to production — the four deployment paths
(Docker, Compose, Kubernetes, Helm), horizontal scaling with distributed
workers, the observability stack (Prometheus, Grafana, Loki, OpenTelemetry),
backup/restore and disaster recovery, and the performance benchmark tooling
that validates capacity before you roll out.

---

## 🚀 Deployment

### Production Deployment

Four supported paths, in order of operational maturity:

```mermaid
flowchart LR
    A["Docker<br/>single container"] --> B["Docker Compose<br/>full stack + profiles"]
    B --> C["Kubernetes / Helm<br/>self-hosted HA"]
    B --> D["Terraform + ECS Fargate<br/>managed AWS"]
```

| Path | When to use | Where |
| :--- | :--- | :--- |
| **Docker** | quick smoke test, edge, appliance | root `Dockerfile` |
| **Docker Compose** | single-host production with Redis + monitoring | `docker-compose.yml`, `deployment/docker-compose.prod.yml` |
| **Kubernetes / Helm** | multi-replica HA, autoscaling | `deployment/k8s/`, `deployment/helm/ai-router/` |
| **Terraform + ECS** | fully managed AWS (ECR, Fargate, CloudWatch) | `deployment/terraform/` |
| **GitOps (ArgoCD)** | declarative, immutable-tag rollouts | `deployment/gitops/` |

> [!IMPORTANT]
> Production rule #1: **never run with `latest`**. Tag images with the
> version + git commit and promote them immutably (see the release pipeline and
> the GitOps "latest rejected" policy).

### Docker

- `Dockerfile` — multi-stage (`builder` → `runtime`), Python 3.12-slim, non-root
  `ai-router` user, `/health` healthcheck, OCI labels, build metadata in
  `/app/.meta/build.json`.
- `deployment/Dockerfile.prod` — production variant used by the prod compose.

```bash
docker build --build-arg VERSION=1.0.0-rc.1 --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) \
  --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) -t ai-router:1.0.0-rc.1 .

docker run -d --name ai-router -p 8000:8000 --env-file .env \
  -v "$PWD/config":/app/config:ro -v "$PWD/logs":/app/logs \
  ai-router:1.0.0-rc.1
```

### Compose

The root `docker-compose.yml` is a full stack with **profiles** — enable only
what you need:

| Profile | Services |
| :--- | :--- |
| `dev` | ai-router + redis (+ ollama) |
| `minimal` | ai-router only |
| `production` | ai-router + redis + prometheus + grafana + loki + promtail + ollama |
| `monitoring` | prometheus + grafana + loki + promtail + otel-collector |
| `distributed` | redis + **ai-worker** + **ai-scheduler** + otel-collector |

Production deploy with the runbook script (validate → build → pre-health →
deploy → wait-health):

```bash
./scripts/deploy.sh --profile production --tag 1.0.0-rc.1
./scripts/healthcheck.sh --wait
```

`deployment/docker-compose.prod.yml` is the hardened production variant:
pinned images, resource limits, restart policies, log rotation, and
`stop_grace_period: 30s` for graceful drain.

### Kubernetes

`deployment/k8s/` is kustomize-based:

```bash
kubectl apply -k deployment/k8s/
kubectl -n ai-router rollout status deployment/ai-router
```

| Manifest | Contents |
| :--- | :--- |
| `ai-router.yaml` | namespace, Deployment (2 replicas, rolling update, probes, resources, securityContext), Service, HPA, PDB |
| `rbac.yaml` | ServiceAccount + minimal RBAC (leases, leader election) |
| `kustomization.yaml` | the bundle entry point |

- **Rolling update** — `maxUnavailable: 0, maxSurge: 1` (zero-downtime).
- **Probes** — liveness `/health`, readiness `/ready`.
- **Hardening** — `runAsNonRoot`, read-only rootfs, drop all capabilities.
- **HPA** — 2–10 replicas on CPU 70% / memory 80%.
- **PDB** — `minAvailable: 1` survives voluntary disruption.

### Helm

`deployment/helm/ai-router/` is the full chart (Chart.yaml `version 0.1.0`,
`appVersion 1.0.0-rc.1`):

| Template | Purpose |
| :--- | :--- |
| `deployment.yaml` | Deployment with probes, security context, resources |
| `hpa.yaml` | HPA (CPU 70% / memory 80% defaults) |
| `pdb.yaml` | PodDisruptionBudget |
| `service.yaml` + `ingress.yaml` | ClusterIP + ingress |
| `configmap.yaml` | runtime configuration |
| `serviceaccount.yaml` | RBAC for leader election |

```bash
helm upgrade --install ai-router deployment/helm/ai-router \
  --set image.tag=1.0.0-rc.1 \
  --set replicaCount=3
```

### Horizontal Scaling

AI Router is **stateless at the API layer** — scale out on demand:

```yaml
# HPA (k8s)
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - resource: { name: cpu,    target: { type: Utilization, averageUtilization: 70 } }
    - resource: { name: memory, target: { type: Utilization, averageUtilization: 80 } }
```

```bash
# Compose: run N gateway replicas on different ports behind your LB/traefik
docker compose --profile production up -d --scale ai-router=3
```

Scaling rules:

- Gateways share state via **Redis** (distributed registry, queues, leases) —
  no sticky sessions required.
- `Traefik` (traefik/ai-router-dynamic.yml) load-balances with health checks
  and TLS termination in front.
- Cluster autoscaling (`app/cluster/autoscale.py`) adds/removes workers based
  on queue depth and node load.

### Distributed Workers

Heavy async work (orchestration tasks, batch RAG, scheduled jobs) runs on
workers, not the gateway:

| Component | Image / command | Mode |
| :--- | :--- | :--- |
| `ai-router` (gateway) | default entrypoint | API + router |
| `ai-worker` | `python -m app.worker` | `DISTRIBUTED_MODE=1` — pulls tasks from the queue |
| `ai-scheduler` | same image | `DISTRIBUTED_MODE=1` + `SCHEDULER_MODE=1` — emits scheduled tasks |

```yaml
# docker-compose.yml (distributed profile)
ai-worker:
  image: ai-router:1.0.0-rc.1
  command: ["python", "-m", "app.worker"]
  environment:
    - DISTRIBUTED_MODE=1
    - REDIS_URL=redis://default:${REDIS_PASSWORD:-}@redis:6379/0
  stop_grace_period: 30s   # drain, don't kill

ai-scheduler:
  image: ai-router:1.0.0-rc.1
  environment:
    - DISTRIBUTED_MODE=1
    - SCHEDULER_MODE=1
```

Worker internals (`app/distributed/`): `DistributedTaskQueue` (Redis lists),
**leases** (`dist_lease:*`, 60 s default) so exactly one worker owns a task,
**idempotency keys**, **DLQ** for poison messages, **retry** with backoff, and
a `WorkerRegistry` heartbeat for liveness — all visible via `/runtime/workers`,
`/runtime/queue`, `/runtime/events`.

### Redis

Redis (`redis:7.2-alpine`, `redis_data` volume) powers the distributed layer:

| Use | Key space | Detail |
| :--- | :--- | :--- |
| Task queue | list | FIFO work for workers |
| Leases | `dist_lease:*` | distributed mutual exclusion, TTL + renewal |
| Worker registry | hashes + TTL | heartbeat-based membership |
| Leader election | SET NX EX | single scheduler/leader among replicas |
| Event bus | pub/sub | cross-node events (`fallback.triggered`, …) |

```yaml
redis:
  image: redis:7.2-alpine
  command: ["redis-server", "--requirepass", "${REDIS_PASSWORD:-}", "--appendonly", "yes"]
  volumes: [redis_data:/data]
  healthcheck: { test: ["CMD", "redis-cli", "ping"] }
```

> [!WARNING]
> Production: enable AOF (`appendonly yes`), set a strong `REDIS_PASSWORD`,
> and use a Redis Sentinel/cluster topology if the queue is critical (see HA).

### High Availability

```mermaid
flowchart LR
    LB["LB / Traefik"] --> G1["gateway replica 1"]
    LB --> G2["gateway replica 2"]
    LB --> G3["gateway replica N"]
    G1 & G2 & G3 --> R[(Redis)]
    R --> W1["worker 1"]
    R --> W2["worker 2"]
    S["scheduler (leader)"] --> R
```

| Layer | HA mechanism |
| :--- | :--- |
| **API** | ≥ 2 replicas behind LB; rolling deploys (`maxUnavailable: 0`) |
| **Scheduling** | leader election via Redis `SET NX EX` (`app/cluster/election.py`), epoch-guarded; observers react to leadership change |
| **Health** | `HealthMonitor` heartbeats + staleness detection (`app/cluster/health.py`); `FailoverManager` (`app/cluster/failover.py`) reroutes around dead nodes |
| **Work** | leases prevent double-execution; DLQ + retry recover failures |
| **Pod level** | PDB `minAvailable: 1`; HPA absorbs traffic spikes |
| **Managed AWS** | ECS service with multiple Fargate tasks behind ALB (Terraform), multi-AZ by default |

---

## 📊 Observability

The stack is three layers — metrics (Prometheus), logs (Loki), traces
(OpenTelemetry) — unified in Grafana:

```mermaid
flowchart LR
    A["AI Router"] -->|/metrics scrape| P["Prometheus"]
    A -->|"OTLP traces + metrics"| O["OTel Collector<br/>0.0.0.0:4318"]
    A -->|"JSON logs"| T["Promtail"]
    P --> G["Grafana"]
    O --> P
    T --> L["Loki"]
    L --> G
```

### OpenTelemetry

- Enabled with `OTEL_ENABLED=1`; `OTEL_SERVICE_NAME` (default `ai-router`),
  `OTEL_EXPORTER_ENDPOINT` (OTLP).
- The **OTel Collector** (`otel/otel-collector.yml`) receives OTLP over HTTP
  (port 4318), batches (`batch: 1s / 1024`), exports to **Prometheus**
  (namespace `ai_router`, port 8889) and debug.
- `init_tracing()` (`app/distributed/tracing.py`) wires instrumentors at
  startup.

```bash
docker compose --profile monitoring up -d   # brings up otel-collector
OTEL_ENABLED=1 OTEL_EXPORTER_ENDPOINT=http://otel-collector:4318 python -m app.main
```

### Prometheus

`prometheus/prometheus.yml`: scrape `ai-router:8000/metrics` every **10 s**
(30 s global default), rules from `prometheus/alerts.yml`. 30 d retention in
the compose stack.

### Grafana

Fully **provisioned** — no manual setup:

| Asset | Path |
| :--- | :--- |
| Dashboard: overview | `grafana/dashboards/ai-router-overview.json` |
| Dashboard: providers | `grafana/dashboards/ai-router-providers.json` |
| Datasources (Prometheus + Loki) | `grafana/provisioning/datasources/` |
| Dashboard provisioning | `grafana/provisioning/dashboards/` |

Dashboards refresh every 30 s from disk; accessible at `:3000` (default
`admin/admin` — change it).

### Metrics

Core Prometheus metrics (`app/metrics.py`):

| Metric | Type | Meaning |
| :--- | :--- | :--- |
| `ai_router_request_total` / `_success` / `_failed` | Counter | request volume & outcomes |
| `ai_router_provider_latency_seconds` | Histogram | per-provider latency |
| `ai_router_provider_requests_total` / `_failure_total` | Counter | per-provider throughput |
| `ai_router_provider_health` | Gauge | 0/1 per provider |
| `ai_router_circuit_breaker_state` | Gauge | closed=0 · half-open=1 · open=2 |
| `ai_router_cache_hit` / `_miss` | Counter | cache efficacy |
| `ai_router_tokens_total` | Counter | token spend per provider/model |
| `ai_router_cost_usd_total` | Counter | $ spend rate |
| `ai_router_uptime_seconds` | Gauge | process uptime |
| `ai_router_active_requests` | Gauge | in-flight gauge for HPA-style tuning |
| `ai_router_distribution_weight` | Gauge | per-provider selection weight |

### Alerting rules (`prometheus/alerts.yml`)

| Alert | Condition | Severity |
| :--- | :--- | :--- |
| `HighErrorRate` | 5 m error rate > 10 % | warning |
| `ProviderDown` | provider health == 0 for 1 m | critical |
| `HighLatency` | p95 latency > 5 s for 3 m | warning |
| `CircuitBreakerOpen` | breaker open for 1 m | critical |
| `HighCostSpend` | cost rate > $10/h for 5 m | warning |

SLOs are defined in code (`app/observability/slo.py`, default `99.9 %`, 30 d
window) with **burn-rate alerts** (warn at 0.5×, page at 2.0×) — the classic
error-budget alerting model.

### Tracing

- Traces (OTLP) flow through the collector with the batch processor.
- Every HTTP request carries a `X-Request-ID` propagated into logs and spans —
  follow one request across gateway → router → provider → LLM → citations.
- Per-request breakdowns (`/dashboard`, `/stats`) plus `total_latency_ms` /
  `retrieval_latency_ms` / `llm_latency_ms` in RAG responses.

### Logging

- Structured JSON logs → stdout → **Promtail** (`promtail/promtail-config.yml`)
  → **Loki** (`loki/loki-config.yml`, port 3100).
- Queryable in Grafana; `GET /logs` and `GET /logs/{request_id}` give
  request-level traceability via API.
- Container log rotation configured in compose (json-file, max size) with
  `./scripts/prune.sh` for old volumes/images.

---

## 💾 Backup · Restore · Disaster Recovery

### Backup

`./scripts/backup.sh [output_dir]` produces a timestamped bundle
(`backups/YYYYMMDD_HHMMSS/`):

| Artifact | Content |
| :--- | :--- |
| `config.tar.gz` | `config/` YAML (providers, models, orchestrator, plugins) |
| `grafana-provisioning.tar.gz` | dashboards + datasource provisioning |
| `prometheus-data.tar.gz` | `prometheus_data` volume (via throwaway alpine container) |
| `loki-data.tar.gz` | `loki_data` volume |
| `grafana-data.tar.gz` | `grafana_data` volume (DB, users, panels) |

```bash
./scripts/backup.sh /mnt/backups        # run on a schedule:
# 0 2 * * * cd /AI-Router && ./scripts/backup.sh /mnt/backups
```

> [!NOTE]
> The router itself holds **no durable state** — config + Redis are the only
> runtime artifacts, and Redis is `appendonly` (AOF). Back up `redis_data`
> (stop-safe: `SAVE`/BGSAVE first) alongside the volumes above.

### Restore

`./scripts/restore.sh <backup_dir>`:

1. Warns if services are running (restore is disruptive).
2. Restores config + Grafana provisioning into the tree.
3. Restores Prometheus / Loki / Grafana volumes into named volumes.
4. Restarts containers to pick up restored data.

```bash
./scripts/restore.sh backups/20260715_023000/
```

### Disaster Recovery

| Tier | RPO | RTO | Plan |
| :--- | :--- | :--- | :--- |
| **Config** | 1 backup run | minutes | config.tar.gz → any machine → compose up |
| **Metrics/logs** | last backup | hours | restore volumes; losing them is non-fatal |
| **State (Redis AOF)** | seconds (AOF) | minutes | Redis is rebuildable: tasks re-enqueue from DLQ/queue snapshot |
| **Full outage** | — | ~15 min | `git clone` → `.env` → `./scripts/deploy.sh --profile production` → verify |

DR checklist:

1. Config is the crown jewel — store `config.tar.gz` off-host (S3/object storage).
2. Redis AOF persists to `redis_data`; for DR replicate to a second Redis or
   snapshot daily.
3. Images are immutable and tagged — a fresh deploy is reproducible from the
   same tag + commit.
4. Test restore quarterly; `./scripts/verify.sh` validates config + health
   after any restore.
5. `./scripts/rollback.sh` keeps the previous image hash and rolls back a bad
   deploy in one command.

---

## ⚡ Performance Benchmarks

### Benchmark suites

In-process benchmark runner (`benchmarks/suites/`) — **no external services
needed**. Each suite measures one dimension and produces a pass/fail report:

| Suite | Class | Measures |
| :--- | :--- | :--- |
| `throughput` | requests per second over duration | max sustainable rate |
| `latency` | mean / p50 / p95 / p99 over N iterations | tail latency |
| `memory` | `tracemalloc` peak + allocations | memory footprint |
| `cpu` | compute loop throughput | CPU efficiency |
| `concurrency` | throughput under 8 threads × 50 tasks | scaling under load |
| `failover` | behavior when a target fails mid-run | resilience |
| `rag_quality` | RAG answer quality (faithfulness/groundedness) | retrieval quality |

Run them:

```bash
python -m benchmarks.suites --target-name default --suites throughput,latency,concurrency
python -m benchmarks.suites --iterations 500 --json   # machine-readable report
```

Each run emits a `BenchmarkReport` with `overall_passed` and per-suite
`SuiteResult` (name, metrics dict, pass/fail).

### Live benchmarks over the API

`/benchmark/live` runs suites against the live deployment:

```bash
# Live benchmark snapshot (rolling windows, ranking, fastest provider)
curl http://localhost:8000/benchmark/live -H "X-API-Key: sk-router-..."

# Per provider
curl http://localhost:8000/benchmark/live/openai -H "X-API-Key: sk-router-..."

# Run a benchmark against the router (query params: model, provider,
# num_requests, concurrency, stream, prompt)
curl "http://localhost:8000/benchmark?model=gpt-4o-mini&num_requests=20&concurrency=5" \
  -H "X-API-Key: sk-router-..."

# Reset live benchmark data
curl -X POST http://localhost:8000/benchmark/live/reset -H "X-API-Key: sk-router-..."
```

### Stress & load testing

```mermaid
flowchart LR
    B["Benchmark suites<br/>in-process"] --> R["Report (pass/fail)"]
    L["Load test<br/>scaling workers"] --> M["metrics: throughput · latency · p95"]
    S["Stress test<br/>workers=8+, RAG batch"] --> F["failover behavior"]
```

- **Stress** — run `concurrency` + `rag_quality` at high worker counts to find
  the saturation point; watch `ai_router_active_requests` and p95 in Grafana.
- **Load** — scale gateways (`--scale ai-router=3`) and workers, push traffic,
  and confirm HPA-style signals (CPU/memory) hold SLOs.
- **Failover drills** — `failover` suite + killing a provider (or `docker stop
  ai-router`) must route traffic without 5xx; the circuit breaker table in
  `prometheus/alerts.yml` makes regressions loud.

> [!TIP]
> Benchmark on the same hardware class as production, pin the image tag, and
> record the report JSON in CI so every release has a performance regression
> gate.

---

## 🚀 What's Next

The platform is deployed, scaled and observable — now it must be safe. The
next part of this README covers the security architecture (zero-trust, audit
chain, PII masking, threat detection), the quality gates (release pipeline,
tests, coverage), and how the whole thing is continuously validated.

**Next: Security & Quality**
# Security & Quality

This part covers how AI Router keeps data safe (auth, RBAC, secrets,
encryption, audit, compliance) and how it stays correct (tests, coverage, and
the CI/CD pipeline that ships every release).

---

## 🔐 Security

Security lives in `app/security/` (platform) and `app/auth/` (identity),
configured via `SEC_*` environment variables.

```mermaid
flowchart LR
    REQ["Request"] --> AUTH["Authenticate<br/>API key · token · MFA"]
    AUTH --> ZT["Zero-Trust policy<br/>authorization · tenant checks"]
    ZT --> RBAC["RBAC roles & scopes"]
    RBAC --> APP["Application"]
    APP --> SEC["Secret store<br/>env · vault · k8s · aws · azure · gcp"]
    APP --> AUD["Immutable audit chain"]
    APP --> THR["Threat detection"]
    AUTH -.->|failures| THR
```

### Authentication (`app/auth/`)

| Mechanism | Detail |
| :--- | :--- |
| **API keys** | `X-API-Key` header; TTL-scoped (default 30 d), optional scopes, hashed at rest (`hashing.py`), issued via `APIKeyManager` |
| **Sessions** | token sessions with `SEC_MAX_SESSION_AGE_SECONDS` (default 3600 s), revocation |
| **Service accounts** | machine identities with scoped permissions |
| **MFA** | multi-factor challenge flow in the zero-trust layer |
| **Providers** | pluggable identity providers (`auth/providers/`) |

### Authorization & RBAC (`app/auth/rbac.py`)

- `Principal` carries roles; **explicit denies win** — a deny list on the
  tenant policy is never overridden by a role grant.
- Admin role (`is_admin`) gates administrative endpoints (`/admin`, config,
  plugins, approval checkpoints).
- Fine-grained scopes map to API keys: a key can be limited to
  `/v1/chat/completions` only.
- **Zero-trust enforcement** (`app/security/zero_trust.py`) — every request is
  authenticated, authorized and tenant-validated; `SEC_ZERO_TRUST_ENFORCE`
  (default `true`) turns denials into hard failures instead of warnings.

### Secrets (`app/security/secrets.py`)

One `SecretManager` facade over six interchangeable backends:

| Backend | Source | Use case |
| :--- | :--- | :--- |
| `environment` | env vars | dev, CI, containers |
| `vault` | HashiCorp Vault KV v2 | production self-hosted |
| `kubernetes` | `Secret` objects | K8s-native |
| `aws` | AWS Secrets Manager | managed AWS |
| `azure` | Azure Key Vault | managed Azure |
| `gcp` | Google Secret Manager | managed GCP |

Every backend implements the same async contract (`get` / `set` / `delete` /
`list`) — provider keys, signing keys and tokens all flow through this layer.

### Encryption (`app/security/keys.py`, `crypto.py`)

- **Envelope encryption** — payloads encrypted with AES-256-GCM; the data key
  is *wrapped* by a master key.
- **Key management** — `KeyManager` owns the current key, supports **versioned
  rotation** (`SEC_KEY_ROTATION_DAYS`, default 90) with key IDs, and wraps keys
  through a **KMS adapter** or **HSM adapter** (`SimulatedHSMAdapter` for dev,
  real HSM/KMS in production — generate/wrap/unwrap/destroy).
- **At rest** — `SEC_SIGNING_KEY` and provider secrets are never stored in
  plaintext on disk.

### Audit Logs (`app/security/audit.py`)

Immutable, tamper-evident audit trail:

```mermaid
flowchart LR
    E1["record"] --> H1["hash(prev | payload)"]
    H1 --> E2["record 2"]
    E2 --> H2["hash(prev | payload)"]
    H2 --> E3["record 3"]
```

- **Hash chain** — each record links to the previous via
  `hmac_sha256(previous_hash | payload | secret)`; genesis anchor at the head.
- **Immutability** — with `audit_immutable`, an HMAC over the chain value is
  stored per record; `AuditRepository.verify_integrity()` replays the chain and
  reports tampered or missing links.
- **Retention** — `SEC_AUDIT_RETENTION_DAYS` (default 365).

### Compliance (`app/security/compliance.py`)

Readiness reports map controls to status (implemented / partially /
not-implemented) per framework:

| Framework | Controls mapped |
| :--- | :--- |
| **SOC 2** | CC6.1 access controls, CC6.6 malicious code, CC7.2/7.3 monitoring, CC8.1 change management, A1.2 backup |
| **ISO 27001** | A.5.15 access policy, A.5.24 incident mgmt, A.8.24 crypto, A.8.25 secure SDLC, A.8.28 logging, A.8.10 deletion |
| **GDPR** | Art. 5 minimisation, Art. 15 access, Art. 17 erasure, Art. 20 portability, Art. 30 records, Art. 32 security of processing |
| **CCPA** | 1798.110 right to know, 1798.105 right to delete, 1798.115 opt-out, 1798.130 disclosure |

**Privacy** (`app/security/privacy.py`) supports the data-subject side:
regex-based **PII detection** (email, phone, SSN, credit card, IP, DOB, name,
address), **masking** (`full` / `partial`, `PII_MASKING_MODE`), retention
(`SEC_PII_RETENTION_DAYS`, default 90), and **data subject requests** (access,
erasure, portability).

### Threat detection (`app/security/threat.py`)

Heuristics flag **brute force, credential stuffing, token replay and anomaly
patterns** over a sliding window (`SEC_THREAT_WINDOW_SECONDS`); events carry
severity and feed incident tracking + metrics (`threat_events`,
`account_lockouts`, `authentication_failures`).

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `SEC_ZERO_TRUST_ENFORCE` | `true` | enforce (not just log) authz/tenant denials |
| `SEC_AUDIT_ENABLED` | `true` | immutable audit chain on |
| `SEC_THREAT_DETECTION_ENABLED` | `true` | threat heuristics on |
| `SEC_KEY_ROTATION_DAYS` | 90 | master key rotation interval |
| `SEC_MAX_SESSION_AGE_SECONDS` | 3600 | max session lifetime |
| `SEC_PII_RETENTION_DAYS` | 90 | PII retention window |

---

## 🧪 Testing

The test suite spans **96 test files** (4,475 passing, 21 skipped — 4,496
collected) in `tests/` with a per-subsystem coverage floor of **95 %**.

### Unit Tests

Fast, dependency-free, focused on a single subsystem:

```bash
PYTHONPATH=. pytest tests/test_auth.py tests/test_routing.py -q
```

Examples: `test_routing.py` (scoring/ranking), `test_auth.py` (117 auth
tests — key lifecycle, RBAC, sessions), `test_classifier.py`,
`test_costs.py`, `test_exceptions.py`, `test_event_bus.py`.

### Integration Tests

End-to-end flows spanning subsystems:

| File | Covers |
| :--- | :--- |
| `test_api.py` | HTTP surface, error codes, headers |
| `test_gateway.py` | routing table, rate limiting, quotas |
| `test_knowledge.py` + `test_knowledge_chunking.py` + `test_knowledge_ingestion.py` + `test_knowledge_embedding.py` + `test_knowledge_vector_store.py` | full knowledge pipeline |
| `test_hybrid_retrieval.py` | BM25 + semantic + fusion |
| `test_citations.py` | attribution, validation, formats |
| `test_distributed_queue.py` | Redis queue, leases, DLQ |
| `test_cluster.py` | election, health, failover |
| `test_hot_reload_advanced.py` | config hot-reload |
| `test_mcp*.py`, `test_plugins*.py`, `test_deploy.py` | MCP, plugins, deployment gates |

### Benchmark Tests

- **CI benchmark** (`.github/workflows/benchmark.yml`) runs the in-process
  suites (throughput, latency, memory, cpu, concurrency, **failover + RAG**)
  on every push and uploads the report as an artifact.
- **Regression floor** — reports must pass per-suite thresholds before merge.

```bash
python -m benchmarks.suites --target-name ci --suites throughput,latency,concurrency,failover
```

### Coverage

```bash
PYTHONPATH=. pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=xml
```

- **Per-subsystem floor ≥ 95 %** enforced in CI (`test.yml`): the release,
  migrations and deploy subsystems plus benchmark suites must hold
  `--cov-fail-under=95`; overall coverage is tracked via Codecov.
- Coverage is collected on every push; release branches require the floor.

---

## 🔄 CI/CD

Seven GitHub Actions workflows:

| Workflow | Job | Gate |
| :--- | :--- | :--- |
| `ci.yml` | format (black) + security (bandit) | push / PR |
| `test.yml` | full suite + coverage + floor | push / PR |
| `lint.yml` | **ruff** check + format, **mypy** | push / PR |
| `benchmark.yml` | benchmark suites + failover/RAG | push / PR |
| `security.yml` | bandit, **pip-audit** (deps), **Trivy** (image), **Syft SBOM** | push / tags |
| `build-sign.yml` | Buildx build + **ghcr push** + **cosign sign** | tags |
| `release.yml` | semver bump, changelog, manifest signing, GitHub Release | manual dispatch |

### GitHub Actions

```yaml
# .github/workflows/test.yml (shape)
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: ${{ env.PYTHON_VERSION }} }
      - run: pip install -r requirements.txt pytest pytest-asyncio pytest-cov
      - run: PYTHONPATH=. pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=xml
      - run: pytest tests/test_release.py tests/test_migrations.py --cov=...   # 95% floor
      - uses: codecov/codecov-action@v5
```

Merge gate: **all of** lint (ruff/mypy), tests + coverage floor, bandit +
pip-audit + Trivy clean, benchmarks pass.

### Release Pipeline

```mermaid
flowchart LR
    M["manual: bump type<br/>patch · minor · major · rc · release"] --> RM["Release Manager<br/>derive next semver"]
    RM --> CL["changelog entry (conventional commits)"]
    CL --> MF["artifact manifest<br/>sha256 digests"]
    MF --> SG["sign manifest<br/>+ signature.json"]
    SG --> GH["GitHub Release<br/>prerelease if '-' in version"]
    GH --> TAG["push release tag"]
    TAG --> CI["release tag → CI"]
    CI --> IMG["build + push image<br/>ghcr.io/anomalyco/ai-router:vX.Y.Z"]
    IMG --> CO["cosign sign"]
```

Triggered manually with a bump type; the `ReleaseManager`
(`app/release/manager.py`) performs the full sequence:

1. `next_version(bump, rc=…)` — derive the next semver from the latest.
2. `create_release(version)` — stamp version + generate the changelog entry.
3. `build_artifact_manifest(version, artifacts)` — sha256 digests of every
   artifact (`app`, `requirements.txt`, `pyproject.toml`, `Dockerfile`,
   `CHANGELOG.md`).
4. `sign_manifest(version)` — signed with `REL_SIGNING_KEY` →
   `dist/release/signature.json` + `history.json` committed back.
5. **Publish** — GitHub Release with changelog body; `prerelease: true` when
   the version contains `-` (e.g. `1.0.0-rc.1`).

### Docker Publishing

- Tag pushes (e.g. `v1.0.0-rc.1`) trigger `build-sign.yml`:
  **Buildx** (multi-arch) → login to **ghcr.io** → `docker/build-push-action`
  → **cosign** sign (sigstore), with graceful skip if signing keys aren't
  configured.
- Images are **immutable**: `ghcr.io/anomalyco/ai-router:v1.0.0-rc.1` never
  changes; GitOps/ArgoCD rejects `latest`.

### Versioning

Semantic versioning with release-candidate support
(`app/release/version.py`):

```
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
1.0.0            → release
1.0.0-rc.1       → release candidate (prerelease: true)
1.0.1            → patch after release
```

- Precedence per semver spec: `1.0.0-rc.1 < 1.0.0`.
- Bumps: `patch` / `minor` / `major` / `rc` / `release` (promote RC → release).
- Strict validation on parse; `compare_versions` used across the repo.

### CHANGELOG

`CHANGELOG.md` is generated from conventional commits by the release pipeline:

```markdown
## [1.0.0-rc.1](https://github.com/anomalyco/ai-router/releases/tag/v1.0.0-rc.1) - 2026-08-02

### Added
- routing, fallback and traffic distribution
- **security:** audit chain, secret store, HSM and encryption
- **observability:** SLO/SLI tracking, burn rate alerts, dashboards
- **release:** semver, changelog, signed manifests, publishing
...
```

Every release section links to the GitHub release tag; the same body is
published to GitHub Releases (`body_path: CHANGELOG.md`).

### Release Process (runbook)

```bash
# 1. Trigger the release workflow with the bump type
#    (workflow_dispatch: patch | minor | major | rc | release)

# 2. CI validates: lint + tests + coverage floor + security scans + benchmarks

# 3. Release job derives the version, writes CHANGELOG, signs the manifest,
#    publishes the GitHub Release, pushes tag + history back to main

# 4. Tag push builds & signs the immutable image to ghcr.io

# 5. Deploy
./scripts/deploy.sh --profile production --tag 1.0.0-rc.1   # compose
kubectl apply -k deployment/k8s/                            # k8s
helm upgrade --install ai-router deployment/helm/ai-router --set image.tag=1.0.0-rc.1

# 6. Verify
./scripts/verify.sh    # 8-step post-deploy verification (health, config, endpoints)
./scripts/rollback.sh  # one-command rollback to the previous image if needed
```

Quality gates are enforced at every step — a failing scan, a coverage floor
miss, or a benchmark regression stops the pipeline before anything ships.

---

## 🚀 What's Next

The platform is secure, tested and shipped — the last part of this README
looks outward: the community, contribution workflow, roadmap and how to get
involved.

**Next: Community & Roadmap**
# Community & Roadmap

This final part of the README covers where the platform has been (the ten
stages that built it), where it is going, how to get help, and how to
contribute.

---

## 🗺️ Roadmap

### Completed Stages

AI Router was built in ten cumulative stages. Everything through
**v1.0.0-rc.1** is complete and covered by tests.

| Stage | Focus | Delivered |
| :--- | :--- | :--- |
| **Stage 1** | Core router | task classification (NLP/keyword), provider adapters, health monitoring (30 s), circuit breaker, smart routing, SSE streaming, `/v1/embeddings` |
| **Stage 2** | Reliability & observability | retry with exponential backoff + jitter, token accounting, Prometheus metrics, structured JSON logging, `/dashboard`, config auto-reload |
| **Stage 3** | Quality & delivery | 4,400+ tests, multi-stage Docker image (non-root), CI/CD workflows, documentation set |
| **Stage 4** | Adaptive traffic distribution | weighted routing, canary / A-B / shadow modes, starvation prevention, cost-optimization modes (`balanced · quality · cheapest · fastest`) |
| **Stage 5** | Provider platform | model discovery, capability registry, reputation engine, benchmark engine, response caching, rate limiting |
| **Stage 6** | Orchestration engine | planner, agents, consensus, debate, workflows, DAG execution, budget manager, context compression, human approval |
| **Stage 7** | Task workers | Redis-backed task queue, `TaskWorker`, scheduler, storage and status tracking |
| **Stage 8** | Distributed lifecycle | runtime health, leader election, leases, worker registry, queue depth, event bus, HPA |
| **Stage 9** | Knowledge foundation | 9.1 collections & documents · 9.2 ingestion pipeline · 9.3 chunking · 9.4 embedding · 9.5 vector store |
| **Stage 10** | Enterprise platform | 10.4 gateway · 10.6 admin & billing · 10.8 plugin sandbox · 10.9 security & compliance · 10.10 release / deploy / observability / migrations |

### Future Vision

Beyond the 1.0 release candidate:

| Direction | What it means |
| :--- | :--- |
| **1.0 GA** | promote from RC with stability guarantees, deprecation policy, LTS line |
| **Provider SDK v2** | richer plugin authoring: typed tool schemas, streaming SDKs, marketplace publishing |
| **Federated routing** | multi-region control plane, latency-aware geo-routing, cross-region failover |
| **Evaluation as a service** | LLM-as-a-judge suites, regression diffs on every config change |
| **Adaptive cost intelligence** | ML-driven anomaly detection on spend, spot-like pricing arbitrage |
| **SIEM & audit export** | streaming audit-chain export, SOC 2 evidence generation |
| **Model fine-tuning loop** | capture + curate + fine-tune from production traffic (opt-in) |

---

## 📚 Documentation Links

| Guide | File |
| :--- | :--- |
| Architecture | [`docs/architecture.md`](docs/architecture.md) |
| API reference | [`docs/api.md`](docs/api.md) |
| SDK usage | [`docs/sdk.md`](docs/sdk.md) |
| Deployment | [`docs/deployment.md`](docs/deployment.md) |
| Operations & runbooks | [`docs/operations.md`](docs/operations.md) |
| Observability | [`docs/observability.md`](docs/observability.md) |
| Migrations | [`docs/migrations.md`](docs/migrations.md) |
| Plugins | [`docs/plugins.md`](docs/plugins.md) |
| Security | [`docs/security.md`](docs/security.md) |
| Troubleshooting | [`docs/troubleshooting.md`](docs/troubleshooting.md) |
| Upgrade guide | [`docs/upgrade.md`](docs/upgrade.md) |
| Contributing | [`docs/contributing.md`](docs/contributing.md) |
| Interactive API | Swagger UI at `http://localhost:8000/docs` |

---

## ❓ FAQ

### General

1. **What is AI Router?** A production-ready, open-source gateway that fronts
   multiple LLM providers — it classifies requests, routes them to the best
   provider, streams responses, tracks cost, and ships with full
   observability, security and deployment tooling.

2. **How is it different from a plain reverse proxy?** A proxy forwards; AI
   Router *decides*. Every request is scored across latency, reliability,
   cost, context fit and reputation, then routed with fallback, retries and
   circuit breakers.

3. **Is it really free?** Yes — MIT licensed, no usage fees. You only pay your
   providers.

4. **Do I need an OpenAI account?** No. Any configured provider works —
   including fully local Ollama models with **no API keys at all**.

5. **Which providers are supported out of the box?** OpenAI, Anthropic
   (Claude), Google (Gemini), Ollama, OpenRouter, Mistral and Groq — plus any
   OpenAI-compatible endpoint (including Azure OpenAI) via config.

6. **Which Python versions are supported?** 3.10+; 3.12 is recommended and
   used for the Docker image and CI.

### Usage

7. **How do I add a new provider?** Add an entry to `config/providers.yaml`
   (`base_url`, `api_key_env`, `enabled: true`) and `POST /reload-config` — no
   restart. For a non-standard protocol, subclass `BaseProvider`.

8. **How do I force the cheapest routing?** Set `optimization_mode: cheapest`
   per request, or `POST /distribution/config` with the cheapest mode.

9. **What happens when my primary provider is down?** The router falls back
   through the task's fallback chain, retries with backoff, and the circuit
   breaker diverts traffic for 60 s before probing again.

10. **Is streaming supported?** Yes — OpenAI-compatible SSE on
    `/v1/chat/completions` with live failover mid-stream.

11. **How do I find the right model for a task?** `GET /models/{task}` lists
    eligible models for `chat`, `coding`, `architecture` and `analysis`.

12. **Can I run it fully offline?** Yes — Ollama provider + the `minimal`
    compose profile; the router, classifier, benchmarks and knowledge pipeline
    run with zero external services.

13. **Where is my data sent?** Only to the provider that serves your request.
    Sensitive traffic can be routed to local Ollama models; PII masking and
    zero-trust policies apply platform-wide.

### Security

14. **How are API keys stored?** Through the secret store — environment,
    Vault, Kubernetes secrets, AWS Secrets Manager, Azure Key Vault or Google
    Secret Manager — never in plaintext on disk, encrypted with AES-256-GCM
    envelope encryption.

15. **How are my provider keys protected from clients?** Clients only ever
    present their own router API key; upstream provider keys are consumed
    internally by the router.

16. **Does it log my prompts?** Requests are logged for traceability
    (`X-Request-ID`), with configurable retention (`SEC_AUDIT_RETENTION_DAYS`)
    and PII masking before persistence.

17. **Is there an audit trail?** Yes — an immutable HMAC hash chain that
    detects tampering, plus threat detection for brute force and token
    replay.

### Operations

18. **Can it run on Kubernetes?** Yes — kustomize manifests and a Helm chart
    with HPA (2–10 replicas), PDB, probes and hardening.

19. **How do I scale it?** Gateways are stateless: add replicas behind
    Traefik/ingress; heavy work drains to Redis-backed `ai-worker` and
    `ai-scheduler` nodes (`distributed` profile).

20. **How is cost tracked?** Per-provider/per-model token accounting with
    `/costs`, `/tokens/estimate`, and `ai_router_cost_usd_total` in
    Prometheus.

21. **What does a production deploy look like?**
    `./scripts/deploy.sh --profile production --tag X` → `./scripts/verify.sh`
    → `./scripts/rollback.sh` if needed; or Helm/ArgoCD for GitOps.

22. **How do I back up?** `./scripts/backup.sh` bundles config, Grafana
    provisioning and Prometheus/Loki/Grafana volumes; Redis uses AOF.

23. **How are SLOs tracked?** Burn-rate alerting with a default 99.9 % SLO
    (30-day window) — alerts at 0.5×, pages at 2× burn.

24. **Windows support?** Via WSL2 or containers only — the platform is
    Linux-first.

### Ecosystem

25. **Does it support MCP?** Yes — it is both an MCP host (stdio/HTTP/SSE/
    WebSocket transports) and an MCP server exposing knowledge, memory and
    citations as tools.

26. **Can I build plugins?** Yes — the Plugin SDK provides lifecycle hooks,
    permissions, sandboxing and signing; sample plugins (cache, guardrails,
    logging, translation) ship in `plugins/`.

27. **How do I contribute?** Read `docs/contributing.md` — pytest conventions,
    95 % per-subsystem coverage floor, config/DI patterns; CI enforces ruff,
    mypy, bandit, pip-audit and Trivy.

28. **Where do I report a security issue?** Privately — see
    `docs/security.md` for the disclosure process. Do not open public issues
    for vulnerabilities.

---

## 🤝 Contributing

Contributions are welcome. Start with [`docs/contributing.md`](docs/contributing.md),
which covers:

- **Development setup** — clone, install, `PYTHONPATH=. pytest tests/ -q`
  (suite is `4477 passed, 21 skipped` at the time of writing).
- **Conventions** — plain pytest classes, one test module per subsystem,
  config classes with `_reject_unknown` + `from_env()`, injectable
  side effects, per-subsystem exception modules.
- **Quality bar** — 95 % per-subsystem coverage floor, ruff + mypy clean,
  benchmarks must not regress.

Typical flow: open an issue → fork → implement with tests → open a PR →
CI gates (lint, tests, security scans, benchmarks) must pass → review →
merge. Releases are cut through the release workflow by maintainers.

---

## 🛡️ Security

Security is treated as a feature, not an afterthought. Full hardening
guidance lives in [`docs/security.md`](docs/security.md):

- TLS at the edge (Traefik/Let's Encrypt), rate limiting middleware
  (100 req/s avg, 50 burst).
- API keys required on gateway endpoints; provider secrets injected via the
  secret store with AES-GCM encryption and KMS/HSM-backed keys.
- Zero-trust enforcement, RBAC with explicit denies, immutable audit chain,
  PII masking, and a compliance readiness model (SOC 2, ISO 27001, GDPR,
  CCPA).

**Vulnerability disclosure:** please report privately via the process in
`docs/security.md` — never in public issues.

---

## ⚖️ License

Released under the **MIT License**. You are free to use, modify and
redistribute — including commercially — provided the license notice is
retained. See the repository root for the full license text.

---

## 🙏 Acknowledgements

- The **FastAPI** and **Pydantic** teams — the platform's foundation.
- **httpx** for the async HTTP layer across all provider adapters.
- **prometheus_client**, **OpenTelemetry**, **Loki** and **Grafana** — the
  observability stack.
- **Redis** — the distributed state backbone (queues, leases, election).
- **Qdrant**, **Chroma**, **pgvector** and the vector ecosystem — knowledge
  storage.
- **sentence-transformers** (cross-encoder rerankers) and the BM25 lineage —
  retrieval quality.
- The **Ollama**, **OpenRouter**, **OpenAI**, **Anthropic**, **Google**,
  **Mistral** and **Groq** teams — the providers this router is nothing
  without.
- Every contributor, tester and user who filed an issue.

---

## ✍️ Author

**anomalyco** — build and maintenance of AI Router.

---

## 🌍 Community

| Channel | Purpose |
| :--- | :--- |
| **[GitHub Discussions](https://github.com/anomalyco/ai-router/discussions)** | Questions, ideas, show & tell |
| **[GitHub Issues](https://github.com/anomalyco/ai-router/issues)** | Bug reports and feature requests |
| **Discord** | *Community server coming soon* — placeholder |
| **Star History** | *Watch the project grow* — star history widget placeholder |

---

## 💬 Support

| Need | Where |
| :--- | :--- |
| Setup / usage questions | GitHub Discussions, FAQ above, `docs/troubleshooting.md` |
| Bug reports | GitHub Issues (include `X-Request-ID` from `/logs`, logs, config) |
| Security vulnerabilities | Private disclosure via `docs/security.md` |
| Feature requests | GitHub Issues with the enhancement label |
| Guaranteed response times | Enterprise support — contact via the repository's maintainer channels |

---

## ❤️ Sponsor

**Sponsor placeholder** — if AI Router saves you money or time, consider
sponsoring development. Sponsorship funds CI infrastructure, maintainer time
and the community server. Details to follow.

---

## 🎉 Final Word

Thank you for reading — and for using AI Router.

This document is the complete reference: from the first `docker compose up`
to a signed, GitOps-deployed production fleet; from the first routed chat to
cited, evaluated RAG answers; from a single API key to an immutable audit
chain. The code behind every word here is tested, benchmarked, scanned and
shipped by the pipeline described in these pages.

The router is the boring part — it just works. Go build something interesting
on top of it.

---

<div align="center">

**AI Router** · v1.0.0-rc.1 · MIT License

[GitHub](https://github.com/anomalyco/ai-router) · [Discussions](https://github.com/anomalyco/ai-router/discussions) · [Issues](https://github.com/anomalyco/ai-router/issues) · [Releases](https://github.com/anomalyco/ai-router/releases)

Built with FastAPI, Redis and an unreasonable number of providers.

</div>
