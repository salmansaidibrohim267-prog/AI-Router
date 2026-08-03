# Demo

Public demonstration assets for AI Router. This directory documents how to
run a full demonstration instance: deployment, configuration, environment,
walkthrough, and API examples.

> **Screenshots:** none are included in this repository. Screenshots must be
> captured from a running instance by a maintainer.
>
> MANUAL ACTION REQUIRED — after deploying the demo, capture and add:
> - `demo/screenshots/dashboard.png` — Grafana overview
> - `demo/screenshots/swagger.png` — Swagger UI (`/docs`)
> - `demo/screenshots/chat-response.png` — a chat completion response
> - `demo/screenshots/ready-health.png` — `/ready` and `/health` output

## Contents

| File | Purpose |
| --- | --- |
| `DEPLOYMENT.md` | Deploy the demo with Docker Compose |
| `CONFIGURATION.md` | Configure providers, models, plugins |
| `ENVIRONMENT.md` | Full environment-variable reference used by the demo |
| `WALKTHROUGH.md` | End-to-end 15-minute walkthrough |
| `API_EXAMPLES.md` | Copy-paste API examples with expected responses |

## Quick start

```bash
cp .env.example .env            # fill in at least one provider key
docker compose --profile demo up -d
curl http://localhost:8000/ready
```

See `DEPLOYMENT.md` for details.
