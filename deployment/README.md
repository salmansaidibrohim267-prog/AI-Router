# Deployment Assets

Production deployment assets for AI Router **v1.0.0-rc.1**.

## Layout

| Path | Purpose |
| --- | --- |
| `Dockerfile.prod` | Multi-stage production image (slim, non-root, pinned version) |
| `docker-compose.prod.yml` | Production compose stack (app + redis + monitoring) |
| `k8s/` | Kubernetes manifests (Deployment, Service, HPA, PDB, Ingress, RBAC, kustomization) |
| `helm/ai-router/` | Helm chart (deployment, service, ingress, HPA, PDB, configmap, service account) |
| `terraform/` | AWS infrastructure (ECR, ECS Fargate, CloudWatch) |
| `ansible/` | VM deployment playbook with health verification and release dirs |
| `gitops/apps/ai-router/application.yaml` | ArgoCD Application pointing at the k8s path, immutable tag `v1.0.0-rc.1` |

## Principles

- **Immutable infrastructure** — image tags are pinned (`:1.0.0-rc.1`), never `latest`.
- **Rolling deployments** — `maxUnavailable: 0`, HPA 2–10 replicas, PDB `minAvailable: 1`.
- **Non-root, read-only rootfs** — `runAsNonRoot: 1000`, drop all capabilities.
- **Health gates** — liveness/readiness on `/health` and `/ready` before traffic.
- **GitOps** — ArgoCD syncs `deployment/k8s` at revision `v1.0.0-rc.1`; the
  `app.deploy.gitops.GitOpsValidator` rejects manifests that drift from these
  rules (missing `targetRevision`, `latest`/`dev` image tags).

## Quick start

```bash
# Docker
docker compose -f deployment/docker-compose.prod.yml up -d

# Kubernetes
kubectl apply -k deployment/k8s/

# Helm
helm upgrade --install ai-router deployment/helm/ai-router --namespace ai-router --create-namespace

# Terraform
cd deployment/terraform && terraform init && terraform plan

# Ansible
ansible-playbook -i deployment/ansible/inventory/production.yml deployment/ansible/playbook.yml

# ArgoCD
kubectl apply -f deployment/gitops/apps/ai-router/application.yaml
```
