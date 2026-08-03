# Demo — API Examples

All endpoints below are verified against the running gateway. Replace
`$BASE` and `$KEY` as in `WALKTHROUGH.md`.

## System

```bash
curl -s $BASE/                  # gateway info (name, version, links)
curl -s $BASE/ready             # 200 when config loaded + provider healthy
curl -s $BASE/version           # build metadata
curl -s $BASE/config            # applied configuration
curl -s $BASE/capabilities      # capability registry
curl -s $BASE/classifier        # task classifier state
```

## Chat

```bash
# Standard
curl -s $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini",
       "messages": [{"role": "system", "content": "Be brief."},
                    {"role": "user", "content": "Hello!"}],
       "max_tokens": 64}'

# Streaming
curl -N $BASE/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "stream": true,
       "messages": [{"role": "user", "content": "Write a haiku."}]}'
```

**Sample response shape:**

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1770000000,
  "model": "openai/gpt-4o-mini",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "..."},
     "finish_reason": "stop"}
  ],
  "usage": {"prompt_tokens": 12, "completion_tokens": 18, "total_tokens": 30}
}
```

## Providers, models, stats

```bash
curl -s $BASE/providers                     # registry with priority + health
curl -s $BASE/providers/openai/models       # models per provider
curl -s $BASE/models                        # all registered models
curl -s $BASE/models/chat                   # models for the chat task
curl -s $BASE/stats                         # aggregated stats
curl -s $BASE/stats/errors                  # error breakdown
curl -s $BASE/analytics/providers           # provider analytics
curl -s $BASE/distribution                  # traffic distribution state
curl -s $BASE/tokens                        # token usage
curl -s $BASE/costs                         # cost tracking
```

## Knowledge / RAG

```bash
curl -s $BASE/knowledge/collections                      # collections
curl -s $BASE/knowledge/documents                        # documents
curl -s $BASE/knowledge/statistics                       # KB statistics
curl -s -X POST $BASE/knowledge/chunk/preview \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"text": "AI Router is a gateway...", "chunk_size": 1000, "chunk_overlap": 200}'
```

## Vector store

```bash
curl -s $BASE/vector/collections                         # list collections
curl -s -X POST $BASE/vector/search \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"collection": "default", "query": "routing", "top_k": 5}'
curl -s $BASE/vector/statistics                          # vector stats
```

## Plugins

```bash
curl -s $BASE/plugins                                    # loaded plugins + hooks
curl -s -X POST $BASE/plugins/enable  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"plugin": "logging"}'
curl -s -X POST $BASE/plugins/disable -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{"plugin": "logging"}'
```

## Runtime / distributed

```bash
curl -s $BASE/runtime/health            # distributed runtime status
curl -s $BASE/runtime/workers           # registered workers
curl -s $BASE/runtime/queue             # queue state
curl -s $BASE/tasks                     # task list
```

## Observability

```bash
curl -s $BASE/metrics | grep ai_router_ | head -20   # Prometheus metrics
curl -s $BASE/cache/stats                            # cache hit rates
```

## Auth failures (expected)

```bash
curl -s -o /dev/null -w "%{http_code}\n" $BASE/v1/chat/completions \
  -H "Content-Type: application/json" -d '{"model":"x","messages":[]}'
# 401 without a valid key
```

Error responses share the shape `{"error": "...", "detail": "..."}` with the
appropriate HTTP status (400, 401, 403, 404, 413, 429, 502, 503, 504, 500).
