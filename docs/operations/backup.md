# Operations — Backup & Restore

Backups cover configuration, vector/knowledge data, Redis data and metrics.

## Automated scripts

| Script | Purpose |
| --- | --- |
| `scripts/backup.sh [dir]` | Snapshot config, dashboards, DBs → `backups/<timestamp>/` |
| `scripts/restore.sh <dir>` | Restore from a backup directory |

```bash
./scripts/backup.sh                 # → ./backups/20260804_101530/
./scripts/restore.sh backups/20260804_101530
```

## What's included

- `config/` — all YAML configuration
- `grafana/`, `prometheus/` — provisioning & dashboards
- Redis data (dump) — queue/state
- SQLite DBs (knowledge, migrations)

## Recommended cadence

- Config: on every change (or nightly)
- Redis/SQLite data: nightly + before upgrades
- Full export: monthly, retain N months

## Kubernetes / Helm users

```bash
# Redis
kubectl exec deploy/redis -- redis-cli -a "$PW" BGSAVE

# Config-consistent (immutable tags)
kubectl get configmap -l app=ai-router -o yaml > config-backup.yaml
```

## Disaster recovery

1. Restore config first, verify `GET /config`
2. Restore Redis (`redis-cli --rdb …` / `--pipe` restore)
3. Restart workers after restore
4. Confirm `/ready` and provider health

## Manual example (docker)

```bash
docker exec ai-router-demo-redis redis-cli SAVE
docker cp ai-router-demo-redis:/data/dump.rdb backups/redis.rdb
```