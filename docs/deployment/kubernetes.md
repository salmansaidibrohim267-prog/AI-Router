# Deployment — Kubernetes

Manifests live in [`deployment/k8s/`](../../deployment/k8s/):

| File | Resource |
| --- | --- |
| `ai-router.yaml` | Deployment (2 replicas) + Service (ClusterIP :8000) |
| `rbac.yaml` | ServiceAccount + RBAC |
| `kustomization.yaml` | Kustomize entrypoint |

Also used by GitOps: `deployment/gitops/apps/ai-router/application.yaml`
(ArgoCD Application, immutable tag `v1.0.0-rc.1`).

## Requirements

- A Kubernetes cluster (1.27+)
- `kubectl`
- Image pull access to `ghcr.io` (public repo — no secret required)
- (Optional) `kustomize` or `kubectl apply -k`

## Deploy

```bash
kubectl apply -k deployment/k8s/
```

Or individually:

```bash
kubectl apply -f deployment/k8s/ai-router.yaml
kubectl apply -f deployment/k8s/rbac.yaml
```

## Verify

```bash
kubectl get deploy,svc,pod -l app=ai-router
kubectl port-forward svc/ai-router 8000:8000 &
curl http://localhost:8000/ready
```

## Built-in safeguards

| Guardrail | Manifest |
| --- | --- |
| Rolling update `maxUnavailable: 0` | Deployment |
| HPA 2–10 replicas | HPA |
| PDB `minAvailable: 1` | PDB |
| `runAsNonRoot`, drop capabilities | SecurityContext |
| Liveness/readiness on `/health` + `/ready` | Probes |

## Configuration

Provide configuration as a ConfigMap (the manifest ships with one) and
secrets via the secret store or `env`/`envFrom`:

```yaml
env:
  - name: CONFIG_DIR
    value: /app/config
  - name: REDIS_URL
    valueFrom:
      secretKeyRef:
        name: ai-router-redis
        key: url
```

## GitOps (ArgoCD)

```bash
kubectl apply -f deployment/gitops/apps/ai-router/application.yaml
```

ArgoCD syncs `deployment/k8s` at a pinned target revision. The
`app.deploy.gitops.GitOpsValidator` (enforced in CI) rejects manifests that
drift — missing `targetRevision`, `latest`/`dev` tags, or unsafe security
contexts fail validation.

## Update & rollback

```bash
kubectl rollout status deploy/ai-router
kubectl rollout undo deploy/ai-router       # rollback
```

See [`docs/release/github-release.md`](../release/github-release.md) for the
immutable-tag release policy.