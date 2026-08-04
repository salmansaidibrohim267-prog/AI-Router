# Operations — Scaling

## When to scale

- Latency rises or `queue_depth` grows (workers saturated)
- Redis CPU/memory saturation under distributed mode
- HPA approaching `maxReplicas` on Kubernetes

## Distributed mode

Set the gateway to process work across a worker pool:

```env
DISTRIBUTED_MODE=1
REDIS_URL=redis://default:password@redis:6379/0
WORKER_COUNT=2
WORKER_CONCURRENCY=5
LEASE_TIMEOUT=30
HEARTBEAT_INTERVAL=5
```

```bash
docker compose --profile distributed up -d
```

This starts `ai-worker` (DISTRIBUTED_MODE=1) and `ai-scheduler`
(`SCHEDULER_MODE=1`) alongside the gateway.

## Vertical scaling

- Raise `WORKER_COUNT` / `WORKER_CONCURRENCY`
- Increase Redis memory; add persistence + AOF
- Raise rate limits (`RATE_LIMIT_REQUESTS/WINDOW`) for higher allowed load

## Horizontal scaling (Kubernetes)

Helm `autoscaling.enabled=true` (2–10 replicas) + PDB `minAvailable: 1`
ensure zero-downtime rolling scale.

```bash
helm upgrade --install ai-router deployment/helm/ai-router \
  --set autoscaling.enabled=true --set autoscaling.maxReplicas=20
```

Kubernetes HPA drives replicas from CPU/metrics; tune resource requests in
`values.yaml`.

## Guidance

1. Scale workers before replicas to absorb queued/async load
2. Keep gateways stateless so replicas scale freely
3. Always scale Redis capacity in tandem (queue is Redis-backed)
4. Verify GitOps immutable tags after autoscale (`docs/release/`)

## See also

- [`docs/deployment/kubernetes.md`](../deployment/kubernetes.md)
- [`docs/observability.md`](../observability.md)