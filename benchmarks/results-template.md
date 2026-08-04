# Benchmark Results — <TITLE>

> Template — copy and fill per benchmark. Keep one file per run/matrix.

## Environment

| Field | Value |
| --- | --- |
| Date (UTC) | `YYYY-MM-DD` |
| Runner / host | e.g. `GitHub Actions ubuntu-latest` or `local (16 vCPU, 32 GB)` |
| AI Router version | `v1.0.0` |
| Provider(s) | `openai`, `anthropic`, `ollama` |
| Model(s) | `gpt-4o-mini`, `claude-3.5-sonnet`, `llama3.1:8b` |
| Python / image | `3.12.x` / `ghcr.io/…/ai-router:1.0.0` |

## Invocation

```bash
python -m benchmarks.cli \
  --model gpt-4o-mini \
  --num-requests 100 \
  --concurrency 10 \
  --output results.json
```

## Results

| Metric | Value |
| --- | --- |
| Duration (s) | `—` |
| Avg latency (ms) | `—` |
| P95 (ms) | `—` |
| P99 (ms) | `—` |
| Throughput (req/s) | `—` |
| Success rate (%) | `—` |
| Errors | `—` |
| Fallback count | `—` |
| Cache hit ratio (%) | `—` |

## Streaming variant (if measured)

| Metric | Value |
| --- | --- |
| Avg latency (ms) | `—` |
| P95 (ms) | `—` |
| Throughput (req/s) | `—` |

## Comparison / notes

- Compare against the previous run using the **same** invocation.
- Note provider-side variance, retries, or degraded health during the run.

## Conclusion

- `—` summary sentence (e.g. "P95 within budget; fallbacks zero; cache hit
  78%").