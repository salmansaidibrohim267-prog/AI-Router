# Upgrade Guide

This guide covers upgrading between AI Router versions.

## v1.0.0-rc.1 -> v1.0.0

The final 1.0.0 release is a stabilization release over `1.0.0-rc.1` with no
breaking API changes.

### What changed

- New `GET /ready` readiness endpoint (200 once the config is loaded and at
  least one provider is available, 503 otherwise)
- `/version` now reports the version baked into the image at build time
  (falls back to `1.0.0-rc.1` when running from source)
- Grafana dashboards use the real metric names (see
  `docs/observability.md`); if you imported a dashboard previously, re-import
  the bundled provisioning
- Published images include SBOM attestations and full provenance

### Steps

1. **Back up** the current state:

   ```bash
   ./scripts/backup.sh
   ```

2. **Check for local changes** before upgrading config:

   ```bash
   git diff config/ docker-compose.yml
   ```

3. **Pull and restart** (Docker Compose):

   ```bash
   docker compose pull ai-router
   docker compose up -d ai-router
   ```

   Or from source:

   ```bash
   git fetch origin && git checkout v1.0.0
   pip install -r requirements.txt
   python -m app.main
   ```

4. **Verify**:

   ```bash
   curl -s http://localhost:8000/ready        # expect 200 {"status":"ok",...}
   curl -s http://localhost:8000/health       # expect 200
   curl -s http://localhost:8000/version      # expect version: 1.0.0
   ./scripts/verify.sh
   ```

5. **Re-import Grafana dashboards** if you were on `rc.1` (metric names
   changed) — or restart the monitoring profile so the bundled dashboards
   reload.

### Rollback

```bash
./scripts/rollback.sh          # restores the previous release artifacts
```

or revert to the previous image tag:

```bash
docker compose up -d --pull always ai-router   # after pinning the old tag
```

Runtime data (metrics, memory, audit log) is forward-compatible between
`rc.1` and `1.0.0`; no migration is required.

## Upgrading from < 1.0.0-rc.1 (alpha/pre-release)

Alpha versions were development snapshots. Upgrade path:

1. Apply the schema migrations first: `python -m app.migrations upgrade`
   (see `docs/migrations.md`).
2. Recreate your `config/providers.yaml` from `config/providers.yaml.example`
   if it exists, or re-export provider keys in `.env`.
3. Confirm plugin manifests match the v1 format (`docs/plugins.md`).
4. Follow the `rc.1 -> v1.0.0` steps above.

## Version-specific notes

| Version      | Notes                                                        |
| ------------ | ------------------------------------------------------------ |
| 1.0.0-rc.1   | First public release candidate. Includes all product features. |
| 1.0.0        | Stabilization: `/ready` endpoint, build-metadata version, SBOM, docs. |
