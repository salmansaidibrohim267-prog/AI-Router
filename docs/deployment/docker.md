# Deployment — Docker

Run AI Router as a single container.

## Pull the image

```bash
docker pull ghcr.io/salmansaidibrohim267-prog/ai-router:latest
```

Or build locally:

```bash
docker build -t ai-router .
```

## Run

```bash
docker run -d --name ai-router \
  -p 8000:8000 \
  -e OPENAI_API_KEY=... \
  -e OPENAI_API_KEY=... \
  -v "$(pwd)/config:/app/config:ro" \
  ghcr.io/salmansaidibrohim267-prog/ai-router:latest
```

> The image runs as non-root `ai-router` (uid `999`). No privileged
> operation is required; `/app/logs` is pre-created and owned by that user.

## Image facts

| Fact | Value |
| --- | --- |
| Base | `python:3.12-slim` (multi-stage) |
| User | `ai-router` (uid/gid `999`) |
| Ports | `8000` |
| Healthcheck | `GET /health` every 30s |
| Metadata | `/version` (build date, commit, python, uvicorn) |
| Config | `/app/config` (mount read-only) |
| Entrypoint | `python -m app.main` |

## Environment

Pass any variable from `.env.example` with `-e` or `--env-file`:

```bash
docker run --env-file .env -p 8000:8000 ghcr.io/.../ai-router:latest
```

## Update & rollback

```bash
docker pull ghcr.io/.../ai-router:latest
docker stop ai-run && docker rm ai-run
docker run ... ghcr.io/.../ai-router:latest      # exact same flags, new tag
```

See [`docs/operations/backup.md`](../operations/backup.md) for backups and
[`scripts/`](../../scripts/) for assisted operational runbooks.