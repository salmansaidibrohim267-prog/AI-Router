# Quick Start

Get a working AI Router gateway in under five minutes.

## Prerequisites

- Python 3.10+ **or** Docker with Compose v2
- One LLM provider API key (OpenAI, Anthropic, Google, OpenRouter, ...)

## Option A — Docker Compose (recommended)

```bash
git clone https://github.com/salmansaidibrohim267-prog/AI-Router.git
cd AI-Router
cp .env.example .env          # add one provider key, e.g. OPENAI_API_KEY=sk-...
docker compose up -d
until curl -fsS http://localhost:8000/ready >/dev/null; do sleep 2; done
```

## Option B — From source

```bash
git clone https://github.com/salmansaidibrohim267-prog/AI-Router.git
cd AI-Router
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...          # at least one provider key
PYTHONPATH=. python -m app.main
```

## Verify

```bash
curl -s http://localhost:8000/health     # {"status":"ok"|"degraded", ...}
curl -s http://localhost:8000/version    # version, build metadata
```

## Send your first request

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer test-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini",
       "messages": [{"role": "user", "content": "Hello AI Router!"}]}'
```

If your provider key is `test`-style or unset, the gateway may respond with
`503`/`502` — that is expected: configure a real key in `.env` (Option A) or
as an environment variable (Option B) and reload:

```bash
curl -X POST http://localhost:8000/reload-config -H "Authorization: Bearer test-key"
```

## Next steps

- Interactive API docs: `http://localhost:8000/docs`
- Full README: [`../README.md`](../README.md)
- Configuration: `demo/CONFIGURATION.md`
- Environment reference: `demo/ENVIRONMENT.md`
- Deeper examples: `examples/`
