# Deployment — Docker Compose

Compose stacks for local and production use.

## Demo (5 minutes)

```bash
cd demo
cp .env.example .env       # add at least one provider key
docker compose up -d
```

Full walkthrough: [`demo/README.md`](../../demo/README.md).

## Production stack

Use `deployment/docker-compose.prod.yml` for the production profile
(gateway + Redis + Prometheus + Grafana + Loki + Promtail + OpenTelemetry):

```bash
cp .env.example .env
docker compose -f docker-compose.yml --profile production up -d
```

The root `docker-compose.yml` provides profiles:

| Profile | Includes |
| --- | --- |
| `dev` | gateway + Redis + Ollama |
| `production` | gateway + Redis + full monitoring |
| `monitoring` | Prometheus + Grafana + Loki + Promtail |
| `distributed` | gateway + Redis + workers + scheduler |

## Key settings

| Setting | Value | Notes |
| --- | --- | --- |
| Image | `ai-router:latest` (built) | `docker-compose.yml` builds from `Dockerfile` |
| Ports | `8000:8000` | API |
| Redis | `redis:7.2-alpine` | `REDIS_URL=redis://…@redis:6379/0` |
| Config | `./config:/app/config:ro` | Live config mount |
| Logs | `./logs:/app/logs` | JSON-file driver, 10m rotation |

## Operations

```bash
docker compose ps                 # status
docker compose logs -f ai-router  # follow logs
docker compose up -d --build      # rebuild after image change
docker compose down               # stop and remove containers
docker compose down -v            # also drop data volumes
```

## Production hardening

- Pin image tags (never `latest`) in production stacks
- Set `ALLOWED_HOSTS` / `CORS_ORIGINS` / TLS via Traefik (`traefik/`)
- Move secrets to Docker secrets (`/run/secrets`)
- Enable `DISTRIBUTED_MODE=1` + workers for scale
  (see [`docs/operations/scaling.md`](../operations/scaling.md))
