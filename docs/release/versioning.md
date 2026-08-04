# Release — Versioning

## Scheme

AI Router follows **Semantic Versioning** with prerelease suffixes:

```text
MAJOR.MINOR.PATCH[-prerelease[.n]]
1.0.0-rc.1    → prerelease
1.0.0         → stable
```

- `MAJOR` — breaking changes
- `MINOR` — backward-compatible features
- `PATCH` — backward-compatible fixes
- `rc.N` — release candidates before a stable cut

## Canonical version locations

`release/VERSION_MATRIX.md` is the single source of truth; every version
reference in the repository must agree before a release:

- `pyproject.toml` (`[project].version`)
- `app/release/config.py` (`initial_version`)
- `Dockerfile` / `deployment/Dockerfile.prod` (`ARG VERSION`)
- Helm `Chart.yaml` (`appVersion`), k8s image tag
- `CHANGELOG.md`, README badges

## How versions are computed

The release pipeline computes the next version from the current history
(`ReleaseManager.next_version`) — never hardcoded. The `bump` input selects
the increment. Prerelease detection (any `-` in the version) sets the GitHub
Release `prerelease` flag.

## Tag & image conventions

| Artifact | Format |
| --- | --- |
| Git tag | `v1.0.0` (leading `v`) |
| GitHub Release name | `1.0.0` (no `v`) |
| GHCR image tags | `latest`, `1.0.0`, `v1.0.0` |
| Release asset names | `ai-router-1.0.0-rc.1.tar.gz`, `signature.json`, `sbom.spdx.json` |

## Compatibility promise

Within a MAJOR version, APIs and config files are backward compatible.
Upgrade guidance: `docs/upgrade.md`.