# Deployment

AI Router v1.0.0-rc.1 ships with production-grade deployment assets under
`deployment/` and a GitOps workflow.

## Options

| Path | Use case |
| --- | --- |
| `docker-compose.prod.yml` | Single-host production stack (app + redis + Prometheus + Grafana) |
| `deployment/k8s/` | Kubernetes manifests (Deployment, Service, HPA, PDB, Ingress, RBAC) |
| `deployment/helm/ai-router/` | Helm chart for the same resources, parameterised |
| `deployment/terraform/` | AWS ECR + ECS Fargate infrastructure |
| `deployment/ansible/` | VM-based deployment with release dirs and verification |

## Image

Pinned immutable tag: `ghcr.io/anomalyco/ai-router:1.0.0-rc.1`.

Build with build args `VERSION`, `GIT_COMMIT`, `BUILD_DATE`; the image drops
privileges to a non-root user and runs a `/health` HEALTHCHECK.

## Quick start (Docker)

```bash
docker compose -f deployment/docker-compose.prod.yml up -d
curl http://localhost:8000/health
```

## Quick start (Kubernetes)

```bash
kubectl apply -k deployment/k8s/
kubectl -n ai-router rollout status deployment/ai-router
```

## GitOps (ArgoCD)

`deployment/gitops/apps/ai-router/application.yaml` syncs the k8s manifests at
revision `v1.0.0-rc.1` with auto-prune and self-heal. Releases promote by
updating `targetRevision` and the image tag together.

## Release flow

1. CI runs quality gates (tests, coverage ≥ 95%, benchmarks).
2. `release.yml` derives the next version, writes `CHANGELOG.md`, signs the
   artifact manifest and publishes a GitHub release.
3. `build-sign.yml` builds the image with the exact tag and cosign-signs it.
4. ArgoCD picks up the new tag and rolls out; smoke + verification tests gate
   the rollout; auto-rollback reverts on failure.
