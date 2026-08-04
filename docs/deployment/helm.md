# Deployment — Helm

A production Helm chart ships in `deployment/helm/ai-router/`.

## Chart layout

```text
deployment/helm/ai-router/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── _helpers.tpl       # naming/labels helpers
    ├── configmap.yaml     # app configuration
    ├── deployment.yaml    # main workload
    ├── hpa.yaml           # autoscaling
    ├── ingress.yaml       # traefik ingress + TLS
    ├── pdb.yaml           # pod disruption budget
    ├── service.yaml       # ClusterIP :8000
    └── serviceaccount.yaml
```

## Install

```bash
helm upgrade --install ai-router deployment/helm/ai-router \
  --namespace ai-router --create-namespace
```

## Values overview (`values.yaml`)

| Key | Default | Description |
| --- | --- | --- |
| `replicaCount` | `2` | Replicas |
| `image.repository` | `ghcr.io/…/AI-Router` | Image repository |
| `image.tag` | `1.0.0-rc.1` | **Pin to immutable tags** |
| `image.pullPolicy` | `IfNotPresent` | Pull policy |
| `service.type` / `service.port` | `ClusterIP` / `8000` | Service |
| `ingress.enabled` | `true` | Ingress (traefik) |
| `ingress.hosts[].host` | `ai-router.example.com` | Ingress host |
| `resources` | 250m/256Mi → 1/512Mi | Requests/limits |
| `autoscaling` | enabled, 2–10 | HPA bounds |
| `pdb` | `minAvailable: 1` | Disruption budget |

## Overrides

```bash
helm upgrade --install ai-router deployment/helm/ai-router \
  --set image.tag=v1.0.0 \
  --set replicaCount=3 \
  --set autoscaling.enabled=true
```

Provide provider keys via `--set` or a values file:

```yaml
env:
  - name: OPENAI_API_KEY
    valueFrom:
      secretKeyRef:
        name: ai-router-secrets
        key: openai
```

## Verify

```bash
helm list -n ai-router
kubectl -n ai-router get pods -o wide
kubectl -n ai-router port-forward svc/ai-router 8000:8000
curl http://localhost:8000/ready
```

## Uninstall

```bash
helm uninstall ai-router -n ai-router
```