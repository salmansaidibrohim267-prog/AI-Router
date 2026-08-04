# Benchmarks

Benchmark tooling and results for AI Router.

## CLI

```bash
python -m benchmarks.cli \
  --model gpt-4o-mini \
  --provider openai \
  --num-requests 100 \
  --concurrency 10 \
  --stream \
  --output results.json
```

### Options

| Flag | Default | Description |
| --- | --- | --- |
| `--model` | `gpt-4o-mini` | Model to benchmark |
| `--provider` | — | Restrict to a provider |
| `--num-requests` | `10` | Number of requests |
| `--concurrency` | `5` | Concurrent requests |
| `--stream` | off | Use SSE streaming |
| `--prompt` | `"Say hello in one word"` | Test prompt |
| `--output` | — | Write JSON results to a file |

### Output metrics

- Duration, average latency, P95, P99
- Throughput (req/s), success rate, errors, fallback count
- System metrics (non-streaming): cache hit ratio, totals

## HTTP benchmark surface

| Endpoint | Purpose |
| --- | --- |
| `GET /benchmark` | Benchmark report |
| `GET /benchmark/live` | Live run status |
| `GET /benchmark/live/{provider_name}` | Live per-provider status |
| `POST /benchmark/live/reset` | Reset live benchmark |

## Suites

`benchmarks/suites/` contains repeatable suites: throughput, latency,
memory, CPU and parallel-worker runs (`benchmarks/suites/suites.py`).

## Methodology

See [methodology.md](methodology.md) for how benchmarks are run and
interpreted.

## Results

See [results-template.md](results-template.md) for the reporting template;
committed results follow that format.