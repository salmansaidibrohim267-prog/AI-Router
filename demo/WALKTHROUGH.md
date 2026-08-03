# Demo — Walkthrough

A 15-minute end-to-end demonstration of AI Router. Prerequisites: the demo
deployed per `DEPLOYMENT.md` with at least one provider key.

Let `KEY` be the gateway API key (default `test-key` from the demo
environment) and `BASE=http://localhost:8000`.

```bash
export BASE=http://localhost:8000
export KEY=test-key
```

## 1. Gateway is alive (1 min)

```bash
curl -s $BASE/health | python3 -m json.tool
curl -s $BASE/ready | python3 -m json.tool
curl -s $BASE/version | python3 -m json.tool
```

**Expected:** `health.status == "ok"` (or `"degraded"` with a provider
down), `ready.status == "ok"` once a provider is healthy, version JSON
with the build metadata.

## 2. Chat completion through the router (3 min)

```bash
curl -s $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Explain an AI gateway in one sentence."}]}' \
  | python3 -m json.tool
```

**Expected:** OpenAI-compatible response: `id`, `model`, `choices[].message.content`,
`usage`. Note the `X-Request-ID` header echoed on the response.

## 3. Streaming (2 min)

```bash
curl -N $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "stream": true, "messages": [{"role": "user", "content": "Count to five."}]}'
```

**Expected:** SSE lines (`data: {"choices":[{"delta":{"content":"..."}}]}`).

## 4. Routing intelligence (3 min)

```bash
curl -s $BASE/providers | python3 -m json.tool
curl -s $BASE/models | python3 -m json.tool
curl -s $BASE/health/providers | python3 -m json.tool
curl -s $BASE/stats/providers | python3 -m json.tool
```

**Expected:** provider registry, available models, per-provider health, and
routing statistics.

## 5. Knowledge / RAG (4 min)

```bash
# Ingest a document (markdown, text, or PDF)
curl -s -X POST $BASE/knowledge/documents/upload \
  -H "Authorization: Bearer $KEY" -F "file=@README.md" | python3 -m json.tool

# Ask a grounded question
curl -s -X POST $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "What does AI Router do?"}]}' \
  | python3 -m json.tool

# Inspect the knowledge base
curl -s $BASE/knowledge/statistics | python3 -m json.tool
```

## 6. Observability (2 min)

```bash
curl -s $BASE/metrics | grep ai_router_ | head -20
# If running the monitoring profile:
#   open http://localhost:3000  (Grafana, bundled dashboards)
```

**Expected:** request/error/latency/health metrics for every provider.

## 7. Failure behavior (optional, 3 min)

Revoke the provider key, then:

```bash
curl -s $BASE/health/providers | python3 -m json.tool    # provider degraded
curl -s $BASE/ready | python3 -m json.tool               # 503 until a provider is healthy
```

Restore the key and `POST /reload-config` to recover. This demonstrates the
circuit breaker, health checks, and readiness gate.

## Done

You have demonstrated: routing, streaming, provider intelligence, RAG,
observability, and resilience. For deeper API examples see
`API_EXAMPLES.md`.
