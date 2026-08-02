# Simple Chat

Demonstrates the three ways to talk to AI Router: a plain REST call, the async
SDK, and token streaming.

## Run

```bash
# from the repository root
PYTHONPATH=. python examples/simple-chat/main.py
```

If you already have the gateway running (see `docker-compose up` or
`deployment/docker-compose.prod.yml`), the REST call hits `http://localhost:8000`.
The SDK and streaming calls work standalone — they use the provider
configuration from `config/providers.yaml` or the provider environment
variables (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, ...).

## Expected output

```
REST -> Routing picks the best provider per request; load balancing spreads load.

model: openai/gpt-4o-mini  id: 9f6...
usage: prompt_tokens=27 completion_tokens=12 total_tokens=39
Routing picks the best provider per request; load balancing spreads load.

streamed 89 characters
```
