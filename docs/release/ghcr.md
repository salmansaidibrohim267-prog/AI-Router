# Release — GitHub Container Registry (GHCR)

Every successful release publishes a production Docker image to GHCR.

## Images

```text
ghcr.io/salmansaidibrohim267-prog/ai-router:latest
ghcr.io/salmansaidibrohim267-prog/ai-router:1.0.0        (or 1.0.0-rc.1)
ghcr.io/salmansaidibrohim267-prog/ai-router:v1.0.0
```

`latest` tracks the newest release; versioned tags are immutable.

## Pull

```bash
docker pull ghcr.io/salmansaidibrohim267-prog/ai-router:latest
docker pull ghcr.io/salmansaidibrohim267-prog/ai-router:v1.0.0
```

The image runs as non-root `ai-router` (uid 999), exposes port `8000`, and
ships `/health`, `/ready`, `/metrics` and `/version`.

## Publishing (automatic)

The release workflow logs into GHCR with the `GITHUB_TOKEN`
(`packages: write`), builds the production `Dockerfile` with BuildKit and
pushes the tags above, then verifies every tag with
`docker buildx imagetools inspect` — a failed inspect fails the workflow.

## OCI metadata

The manifest carries OCI labels: `org.opencontainers.image.{title,
description, version, source, licenses, created, revision}` plus in-image
build metadata (`/app/app/.meta/build.json` → `GET /version`).

## Consuming in production

- Compose: `image: ghcr.io/…/ai-router:1.0.0` (pin, never `latest`)
- Kubernetes/Helm: set `image.repository` + pinned `image.tag`
- Pull secrets are unnecessary for a public repository

## Security

- Images are scanned by Trivy in CI before publishing
- SBOM (SPDX) is generated for the source and attached to each release
- Attestations are enabled via BuildKit provenance

## Visibility

Packages inherit repository visibility. Published with the `GITHUB_TOKEN`
from a public repository, the image is publicly pullable.