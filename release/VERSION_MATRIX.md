# Version Matrix

Canonical version references across the repository. **1.0.0-rc.1** is the
pinned code version; **1.0.0** is the public release target produced by the
release pipeline (promotes `rc.1 → 1.0.0`).

| Location | Value | Notes |
| --- | --- | --- |
| `pyproject.toml` — `[project].version` | `1.0.0-rc.1` | Package metadata |
| `app/release/config.py` — `initial_version` | `1.0.0-rc.1` | Release tooling start point |
| `Dockerfile` — `ARG VERSION` | `1.0.0-rc.1` | Base image build |
| `deployment/Dockerfile.prod` — `ARG VERSION` | `1.0.0-rc.1` | Production image build |
| `deployment/helm/ai-router/Chart.yaml` — `appVersion` | `1.0.0-rc.1` | Helm chart app version |
| `deployment/helm/ai-router/Chart.yaml` — `version` | `0.1.0` | Chart revision (independent) |
| `deployment/k8s/ai-router.yaml` — image tag | `:1.0.0-rc.1` | Kubernetes manifest |
| `deployment/docker-compose.prod.yml` — image tag | `:1.0.0-rc.1` | Production compose |
| `deployment/terraform/variables.tf` — default image | `:1.0.0-rc.1` | Terraform default |
| `CHANGELOG.md` — top release | `[1.0.0]` | Published release entry |
| `README.md` — badge | `v1.0.0-rc.1` | Code version badge |
| Image registry | `ghcr.io/salmansaidibrohim267-prog/AI-Router` | Published artifacts |

## Release workflow

`bump: release` in the Release workflow promotes the RC to the final
version, regenerates the changelog, and updates the tag. After running it,
re-verify the table above and commit the resulting changes.

## Image tags

| Tag | Meaning |
| --- | --- |
| `1.0.0-rc.1` | Release candidate (pre-release, may change) |
| `1.0.0` | Stable public release (immutable) |
| `latest` | Latest stable (set by the registry publisher) |
