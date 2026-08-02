# Operations

Operational runbooks for running AI Router in production.

## Scripts

`scripts/` ships operational helpers:

| Script | Purpose |
| --- | --- |
| `backup.sh` / `restore.sh` | Backup and restore state (config, Grafana provisioning, Prometheus/Loki/Grafana volumes) |
| `deploy.sh` | Validate config, build the image with version metadata, deploy via compose and wait for health |
| `rollback.sh` | Revert to the previous release image |
| `healthcheck.sh` / `verify.sh` | Probe `/health` and report container/service status |
| `status.sh` | Show container, volume and network state |
| `prune.sh` | Clean old images, volumes and logs |
| `update.sh` | Update config from the repo |
| `validate.sh` | Validate compose and config files |

## Health

- Liveness: `GET /health` — restart if failing for 3 consecutive probes.
- Readiness: `GET /ready` — returns 200 only when the config is loaded and at
  least one provider is available (503 otherwise). Docker and k8s probes wire
  this automatically.
- `GET /health/providers` gives per-provider readiness for routing decisions.

## Deployment verification

The `app.deploy` pipeline enforces, before traffic:

1. **Quality gates** — coverage ≥ 95%, p95 latency ≤ 500ms, error rate ≤ 1%,
   tests green.
2. **Smoke tests** — health, readiness and a minimal chat path must respond.
3. **Rollback test** — deploy the new version, revert, confirm recovery.
4. **Verification** — version matches `1.0.0-rc.1`, latency within budget.

## Backup

```bash
./scripts/backup.sh                # full snapshot
./scripts/restore.sh <snapshot>    # restore
```

## Rollback

```bash
./scripts/rollback.sh              # swap to previous release dir
kubectl rollout undo deployment/ai-router   # k8s equivalent
helm rollback ai-router 1                    # Helm equivalent
```

## Capacity

- HPA scales 2–10 replicas on CPU (70%) and memory (80%).
- PDB guarantees at least 1 replica during voluntary disruptions.
- Rolling update keeps `maxUnavailable: 0`.

## Alerting

Burn-rate alerts (see `docs/observability.md`) page on-call when the error
budget is consumed at ≥ 2× the allowed rate; warnings fire at 0.5×.
