# Troubleshooting

## Service won't start

- `./scripts/status.sh` — confirm the container is running.
- `docker logs ai-router` — check startup errors (config path, env vars).
- Validate config: `./scripts/validate.sh`.

## Provider calls all fail

1. Check `/health` for provider health status.
2. Check API keys are present in `.env` / environment.
3. Check `logs/` for provider-specific errors and rate limits.
4. Confirm at least one provider is healthy; routing skips unhealthy ones.

## High latency

- Verify p95 against the `ai_router_latency_seconds` histogram in Prometheus.
- Check per-provider latency; routing prefers the fastest healthy provider.
- Ensure the host meets the CPU/memory reservations in compose/k8s.

## Quality gates blocking a release

The release is intentionally blocked. Resolve the specific gate:

| Gate | Fix |
| --- | --- |
| `coverage` | Add tests; per-subsystem floor is 95% |
| `p95_latency_ms` | Optimize routing/provider or raise the budget deliberately |
| `error_rate` | Fix the provider issue before shipping |
| `tests_passed` | All tests must pass (`pytest tests/`) |

## Smoke tests failing after deploy

- Probe `/health` and `/ready` manually.
- Check the version endpoint matches the expected `v1.0.0-rc.1` tag.
- If verification fails, auto-rollback engages; verify the previous release
  recovers, then re-run the pipeline.

## Migrations stuck or conflicting

- `MigrationManager.status()` shows applied/pending versions.
- A version recorded in `schema_versions` but absent from code → rollback
  skips it; re-add the migration file to match.
- If locked: another migrator holds the lock; wait or roll back the
  uncommitted transaction.

## Signature verification fails

- Re-download the artifact and `signature.json`.
- Confirm the signing key matches the one used at build time
  (`REL_SIGNING_KEY`).
- Tampered payloads fail verification by design — treat as a security
  incident.

## Alerts not firing

- `OBS_ALERTS_ENABLED` must be truthy.
- Rules need a condition or evaluator (e.g. `burn_rate:api>0.5`).
- `for_seconds` delays firing; check the firing window has elapsed.
