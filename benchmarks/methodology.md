# Benchmark Methodology

How AI Router benchmarks are run so results are comparable and trustworthy.

## Principles

1. **Same environment** — results are only comparable within the same
   runner/host, provider and model.
2. **Warm-up** — let caches and connection pools settle before measuring.
3. **Fixed sample sizes** — set `--num-requests` and `--concurrency`
   explicitly; never compare across different sizes.
4. **Report percentiles** — average latency hides tail latency; P95/P99 are
   mandatory in every report.
5. **Record the environment** — CPU, memory, provider, model, versions.

## Procedure

```bash
# 1. Warm up (10 requests, low concurrency)
python -m benchmarks.cli --num-requests 10 --concurrency 1

# 2. Measured run
python -m benchmarks.cli \
  --model gpt-4o-mini \
  --num-requests 100 \
  --concurrency 10 \
  --output results.json

# 3. Streaming variant (separate run, same parameters)
python -m benchmarks.cli --stream --num-requests 100 --concurrency 10
```

## Interpreting metrics

| Metric | Meaning |
| --- | --- |
| `average_latency_ms` | Mean end-to-end latency |
| `p95_latency_ms` / `p99_latency_ms` | Tail latency percentiles |
| `throughput_reqs_per_sec` | Requests completed per second |
| `success_rate` | Fraction of successful requests |
| `fallback_count` | Provider failovers triggered |
| `cache_hit_ratio` | Cache effectiveness (non-streaming) |

## Reporting

- Include the exact CLI invocation
- Report percentiles, not just averages
- Note the environment (runner, provider latency, time of day)
- Mark results as **preliminary** if the environment is shared/cloud
- Only compare "apples to apples": identical command, same provider/model

## Caveats

- Cloud provider latency varies; rerun and report medians over ≥3 runs
- Streaming results are not comparable to non-streaming results
- System metrics are only collected for non-streaming runs