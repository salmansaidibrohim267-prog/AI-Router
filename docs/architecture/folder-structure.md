# Architecture — Folder Structure

Top-level layout of the repository.

```text
AI-Router/
├── app/                        # The application (Python package)
│   ├── admin/                  # Admin console, settings, feature flags
│   ├── api.py                  # FastAPI application and routes
│   ├── auth/                   # Authentication & authorization
│   ├── benchmark/              # Benchmark engine
│   ├── billing/               # Metered usage, quotas, invoices
│   ├── cache.py                # Caching primitives
│   ├── capability_registry.py  # Model capabilities registry
│   ├── classifier.py           # Task classification
│   ├── config.py               # ConfigManager (YAML + env)
│   ├── costs.py                # Cost tracking & estimation
│   ├── distributed/            # Worker pool, leader election, Redis
│   ├── event_bus.py            # Internal pub/sub
│   ├── knowledge/              # RAG: ingestion, chunking, embedding, vector
│   ├── logger.py               # Structured logging + secret masking
│   ├── mcp/                    # Model Context Protocol SDK
│   ├── metrics.py              # Prometheus metrics
│   ├── migrations/             # Versioned schema migrations
│   ├── observability/          # SLOs, error budgets, telemetry
│   ├── orchestration/          # Multi-agent orchestration
│   ├── plugin/, plugins/       # Plugin SDK + runtime
│   ├── providers/              # Provider adapters (OpenAI, Anthropic, …)
│   ├── rag/                    # Retrieval-augmented generation features
│   ├── reranker/               # Reranking backends
│   ├── retrieval/              # Hybrid & semantic search
│   ├── security/               # Keys, secrets, zero-trust, audit
│   ├── tenancy/                # Multi-tenancy
│   └── worker.py               # Distributed worker entrypoint
├── benchmarks/                 # Benchmark suite + CLI
│   └── suites/                 # Named benchmark suites
├── branding/                   # Brand assets & guidelines (markdown)
├── classifier/                 # Classifier model assets/samples
├── config/                     # YAML configuration
│   ├── models.yaml
│   ├── providers.yaml
│   └── …
├── deployment/                 # Production deployment assets
│   ├── ansible/
│   ├── gitops/                  # ArgoCD applications
│   ├── helm/ai-router/          # Helm chart
│   ├── k8s/                     # Kubernetes manifests
│   └── terraform/
├── demo/                       # One-command local demo
├── dist/                       # Release artifacts (build output)
├── docs/                       # Documentation
│   ├── api/
│   ├── architecture/
│   ├── deployment/
│   ├── operations/
│   └── release/
├── examples/                   # Copy-paste examples
│   ├── config/
│   ├── datasets/
│   ├── mcp/ plugin/ providers/ rag/ requests/ simple-chat/
├── grafana/                    # Grafana dashboards & provisioning
├── insomnia/                  # Insomnia collection
├── loki/                       # Loki config (logs)
├── otel/                      # OpenTelemetry collector config
├── plugins/                  # Bundled/external plugins
├── postman/                  # Postman collection
├── prometheus/               # Prometheus config
├── promtail/                 # Promtail config
├── providers/                # Reference provider fixtures/examples
├── scripts/                  # Ops scripts (backup, deploy, verify…)
├── tests/                    # Test suite
├── traefik/                  # Traefik config
├── Dockerfile                # Production image (multi-stage, non-root)
├── docker-compose.yml        # Dev / production compose stack
├── requirements.txt          # Python dependencies
└── pyproject.toml            # Build, lint, mypy, ruff config
```

## Conventions

- Application code lives under `app/`, one package per subsystem.
- Configuration is declarative YAML in `config/`.
- Deployment assets live under `deployment/`; docs under `docs/`.
- Ops tooling is shell in `scripts/` + compose/K8s assets in `deployment/`.
- Release assets are emitted into `dist/` (generated during CI, not edited).