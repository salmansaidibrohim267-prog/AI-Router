# Deployment

> In-depth guides: [`docs/deployment/`](deployment/)

AI Router is designed to run anywhere — from a single container on a laptop
to a multi-region cluster with GitOps.

## Supported deployment targets

| Target | Asset | Guide |
| --- | --- | --- |
| **Docker** (single container) | `Dockerfile` | [`docs/deployment/docker.md`](deployment/docker.md) |
| **Docker Compose** (stack) | `docker-compose.yml`, `deployment/docker-compose.prod.yml` | [`docs/deployment/compose.md`](deployment/compose.md) |
| **Kubernetes** | `deployment/k8s/` | [`docs/deployment/kubernetes.md`](deployment/kubernetes.md) |
| **Helm** | `deployment/helm/ai-router/` | [`docs/deployment/helm.md`](deployment/helm.md) |
| **Terraform** | `deployment/terraform/` | [`docs/deployment/`](deployment/) |
| **Ansible** | `deployment/ansible/` | [`docs/deployment/`](deployment/) |
| **GitOps (ArgoCD)** | `deployment/gitops/` | [`docs/deployment/kubernetes.md`](deployment/kubernetes.md) |

## Quick picks

- **Try it now:** [`demo/`](../demo/) — one command, local stack.
- **Production on Docker:** `deployment/docker-compose.prod.yml` +
  `docs/deployment/compose.md`.
- **Production on Kubernetes:** `deployment/k8s/ai-router.yaml` +
  `docs/deployment/kubernetes.md`.
- **Helm chart:** `deployment/helm/ai-router/` + `docs/deployment/helm.md`.

## Container image

Official images are published to **GHCR**:

```bash
docker pull ghcr.io/salmansaidibrohim267-prog/ai-router:latest
docker pull ghcr.io/salmansaidibrohim267-prog/ai-router:v1.0.0
```

The image runs as non-root user `ai-router` (uid 999) and exposes:
`8000` (API), `/health`, `/ready`, `/metrics`.

## Deployment checklist

1. Provision provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …)
2. Configure `config/providers.yaml` + `config/models.yaml`
3. Set `ALLOWED_HOSTS`, `CORS_ORIGINS` and TLS (Traefik/Ingress)
4. Enable Redis + `REDIS_URL` for distributed mode
5. Configure secrets (env vars or Docker/K8s secrets)
6. Wire monitoring (Prometheus, Grafana, Loki, OpenTelemetry)
7. Set up backups (`docs/operations/backup.md`)
8. Plan upgrades using `docs/upgrade.md` and releases via `docs/release/`

## Common topologies

- **Standalone:** one gateway + optional Redis (demo, dev, small prod)
- **Stacked:** gateway + Redis + Prometheus + Grafana + Loki + OpenTelemetry
  (`docker-compose.yml`, `production` profile)
- **Distributed:** gateway + worker pool + scheduler over Redis
  (`DISTRIBUTED_MODE=1`, see `docs/operations/scaling.md`)
- **Kubernetes:** Deployment + HPA + PDB + Service + Ingress (Helm chart)