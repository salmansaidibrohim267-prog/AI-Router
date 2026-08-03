# Demo — Deployment

The demo runs the AI Router gateway locally with Docker Compose, using the
`dev` profile (default) which includes Ollama for a fully offline path.

## Prerequisites

- Docker Engine 24+ with Compose v2
- At least one provider credential (any of the keys in `ENVIRONMENT.md`)
- 2 GB RAM available (4 GB if using Ollama)

## Deploy

```bash
# 1. From the repository root, prepare the environment
cp .env.example .env

# 2. Set at least one provider key in .env, e.g.
#    OPENAI_API_KEY=sk-...   or   OPENROUTER_API_KEY=...

# 3. Start the gateway (dev profile: gateway + redis + ollama)
docker compose up -d

# 4. Wait for readiness
until curl -fsS http://localhost:8000/ready >/dev/null; do sleep 2; done
echo "AI Router is ready"
```

## Verify

| Check | Command | Expected |
| --- | --- | --- |
| Readiness | `curl -s http://localhost:8000/ready` | `200` `{"status":"ok",...}` |
| Liveness | `curl -s http://localhost:8000/health` | `200` |
| Version | `curl -s http://localhost:8000/version` | JSON with version |
| Swagger | open `http://localhost:8000/docs` | Interactive API docs |
| Metrics | `curl -s http://localhost:8000/metrics` | Prometheus text format |

## Production-like demo (monitoring + distributed)

```bash
docker compose --profile monitoring up -d     # + Grafana, Prometheus, Loki, OTel
docker compose --profile distributed up -d    # + ai-worker, ai-scheduler
```

Grafana is then available at `http://localhost:3000` with the bundled
dashboards (provisioned). Credentials come from the compose defaults — change
them before any public exposure.

## Stop

```bash
docker compose down            # keep volumes
docker compose down -v        # remove volumes (state, redis, logs)
```

## Troubleshooting

- `503` from `/ready`: no provider is configured or no provider is healthy —
  check `config/providers.yaml` and the provider keys in `.env`.
- Ollama not reachable: `docker compose logs ollama` and confirm
  `ollama pull llama3.2` inside the container.
- Anything else: see `docs/troubleshooting.md`.
