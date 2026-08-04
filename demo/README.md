# Demo

Run AI Router locally in minutes with **one command**:

```bash
docker compose up -d
```

The demo starts the gateway plus a local Redis, uses the bundled example
configuration, and works with **zero API keys** if you have Ollama running
locally. Add keys for OpenAI, Anthropic, Google or OpenRouter to use cloud
models too.

> **Screenshots:** none are included in this repository. Maintainers capture
> screenshots from a running instance — see `demo/WALKTHROUGH.md`.

## Contents

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | Single-file demo stack (gateway + Redis) |
| `.env.example` | Environment template — copy to `.env` |
| `README.md` | This guide |
| `DEPLOYMENT.md` | Deploying the demo in detail |
| `CONFIGURATION.md` | Configure providers, models, plugins |
| `ENVIRONMENT.md` | Full environment-variable reference |
| `WALKTHROUGH.md` | End-to-end 15-minute walkthrough |
| `API_EXAMPLES.md` | Copy-paste API examples with expected responses |

## Requirements

- **Docker Engine 24+** with **Docker Compose v2** (`docker compose version`)
  or Docker Desktop (macOS/Windows)
- **~1.5 GB free RAM** for the stack (gateway + Redis)
- Port **8000** free on the host (configurable via `PORT`)
- **Optional:** [Ollama](https://ollama.com) running locally on port 11434
  for the zero-key demo path
- **Optional:** API keys for any cloud provider you want to try

No Python, no virtualenv, no manual dependency installation.

## Installation

```bash
git clone https://github.com/salmansaidibrohim267-prog/AI-Router.git
cd AI-Router/demo
cp .env.example .env      # edit .env and add at least one provider key
```

Edit `.env` — at minimum set one of the provider keys. If you leave all
keys empty, the gateway still starts and Ollama models remain usable.

## Startup

```bash
# from the demo/ directory
docker compose up -d

# or from the repository root
docker compose -f demo/docker-compose.yml up -d
```

First run builds the image (a few minutes). Subsequent runs start instantly.

### Verify it is running

```bash
curl http://localhost:8000/ready          # -> {"status":"ready", ...}
curl http://localhost:8000/health         # -> {"status":"ok", ...}
```

Open the interactive API docs at <http://localhost:8000/docs> (Swagger UI).

### Send your first request

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "ollama/llama3.1:8b",
       "messages": [{"role": "user", "content": "Hello!"}]}'
```

Use `examples/` for ready-made requests, the Postman/Insomnia collections,
or follow the walkthrough in `WALKTHROUGH.md`.

## Environment variables

The demo reads `demo/.env`. The most important variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | *(empty)* | Enables OpenAI models |
| `ANTHROPIC_API_KEY` | *(empty)* | Enables Anthropic models |
| `GOOGLE_API_KEY` | *(empty)* | Enables Google / Gemini models |
| `OPENROUTER_API_KEY` | *(empty)* | Enables OpenRouter models |
| `MISTRAL_API_KEY` / `GROQ_API_KEY` | *(empty)* | Enables Mistral / Groq models |
| `PORT` | `8000` | Host port for the gateway |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |
| `DISTRIBUTED_MODE` | `0` | Set to `1` for distributed mode |

Ollama needs **no key** — point it at your local `http://localhost:11434`
(default in `config/providers.yaml`).

See `ENVIRONMENT.md` for the complete reference.

## Shutdown

```bash
docker compose down          # stop and remove containers (keeps volumes)
docker compose down -v       # also remove Redis data volume
```

To stop without removing containers: `docker compose stop`.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `port is already allocated` / `Bind for 0.0.0.0:8000 failed` | Port 8000 in use | `PORT=8001 docker compose up -d` |
| Gateway not answering `/health` | Image still building or starting | `docker compose logs -f ai-router`, wait for `Application startup complete` |
| `401 Unauthorized` on chat | No API key for the requested model | Add the provider key to `.env` and `docker compose up -d` again |
| Ollama model not found | Ollama not running / model not pulled | `ollama pull llama3.1:8b`, keep `ollama serve` running |
| Redis connection refused | Redis failed to start | `docker compose logs redis`; `docker compose up -d` again |
| Docker permission denied | User not in `docker` group | `sudo usermod -aG docker $USER` then re-login |
| CPU pinned during first run | Image build step | Expected on first start only |
| Everything green but slow responses | First call warms caches / models | Repeat the request |

For anything else, see `docs/troubleshooting.md` or open an issue at
<https://github.com/salmansaidibrohim267-prog/AI-Router/issues>.

## Next steps

- Follow the 15-minute walkthrough: `WALKTHROUGH.md`
- Configure providers/models: `CONFIGURATION.md`
- Try API examples: `API_EXAMPLES.md` and `../examples/`
- Deploy for real: `../docs/deployment/` or `../deployment/`
