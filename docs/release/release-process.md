# Release — Release Process

AI Router uses a single, automated release pipeline (`.github/workflows/release.yml`)
driven by `workflow_dispatch` with a version-bump input.

## Trigger

```text
Actions → Release → Run workflow → bump: patch | minor | major | rc | release
```

The pipeline runs on `main` and publishes versioned artifacts.

## Steps executed by the pipeline

1. **Checkout** full history (`fetch-depth: 0`)
2. **Derive the next version** via `ReleaseManager.next_version(bump)`
   and write `CHANGELOG.md` + `dist/release/history.json`
3. **Assemble artifacts** (app, requirements, Dockerfile, README, changelog)
4. **Sign an artifact manifest** (SHA-based signature → `signature.json`)
5. **Generate SBOM** (`anchore/sbom-action`, SPDX JSON)
6. **Create a GitHub Release** (`softprops/action-gh-release`) with
   signature, history, SBOM and changelog attached
7. **Push the release commit** back to `main` (chore(release): <version>)
8. **(Post-release) Publish Docker image** to GHCR + `imagetools inspect`

## Version bumps

| Input | Example result | Prerelease tag? |
| --- | --- | --- |
| `rc` | `1.0.1-rc.1` | yes |
| `patch` | `1.0.1` | no |
| `minor` | `1.1.0` | no |
| `major` | `2.0.0` | no |
| `release` | promotes `rc.1 → 1.0.0` | no |

## Pre-flight checklist

Follow `release/RELEASE_CHECKLIST.md` — confirm tests, coverage, lint,
security scans, version matrix, changelog and release notes before starting
a pipeline run.

## After the run

- Copy/manage the GitHub Release notes (`release/RELEASE_NOTES_v1.0.0.md`)
- Verify GHCR images (`docker pull ghcr.io/…/ai-router:latest`)
- Record deviations in the run's discussion thread

## Manual admission

Release creation still lands in the `release/` directory assets coming from
`VERSION_MATRIX.md`. Maintainers verify before announcing. Releases are
immutable — no `latest`-style drift in production manifests
(`docs/deployment/kubernetes.md`).