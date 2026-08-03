import time

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, generate_latest

request_total = Counter("ai_router_request_total", "Total requests", ["provider", "model", "task"])
request_success = Counter("ai_router_request_success", "Successful requests", ["provider", "model"])
request_failed = Counter("ai_router_request_failed", "Failed requests", ["provider", "model", "error_type"])
provider_latency_seconds = Histogram(
    "ai_router_provider_latency_seconds",
    "Provider latency in seconds",
    ["provider", "model"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
provider_requests_total = Counter("ai_router_provider_requests_total", "Total requests per provider", ["provider"])
provider_failure_total = Counter(
    "ai_router_provider_failure_total",
    "Total failures per provider",
    ["provider", "error_type"],
)
cache_hit = Counter("ai_router_cache_hit", "Cache hit count", ["cache_name"])
cache_miss = Counter("ai_router_cache_miss", "Cache miss count", ["cache_name"])
provider_health = Gauge(
    "ai_router_provider_health",
    "Provider health status (1=healthy, 0=unhealthy)",
    ["provider"],
)
provider_latency_gauge = Gauge(
    "ai_router_provider_latency_ms",
    "Provider latency in milliseconds",
    ["provider"],
)
uptime_seconds = Gauge("ai_router_uptime_seconds", "Uptime in seconds")

tokens_total = Counter(
    "ai_router_tokens_total",
    "Total tokens consumed",
    ["provider", "model", "type"],
)
cost_usd_total = Counter(
    "ai_router_cost_usd_total",
    "Total cost in USD",
    ["provider", "model"],
)
circuit_breaker_state = Gauge(
    "ai_router_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half-open, 2=open)",
    ["provider"],
)
fallback_total = Counter(
    "ai_router_fallback_total",
    "Fallback count",
    ["provider", "model", "from_provider"],
)
rate_limit_total = Counter(
    "ai_router_rate_limit_total",
    "Rate limited requests",
)
active_requests = Gauge(
    "ai_router_active_requests",
    "Currently active requests",
)

# Traffic distribution metrics
distribution_weight = Gauge(
    "ai_router_distribution_weight",
    "Traffic distribution weight per provider",
    ["provider", "model"],
)
distribution_selections_total = Counter(
    "ai_router_distribution_selections_total",
    "Total selections per provider via distribution",
    ["provider", "model"],
)
canary_traffic_total = Counter(
    "ai_router_canary_traffic_total",
    "Total requests sent to canary providers",
    ["provider", "model"],
)
shadow_traffic_total = Counter(
    "ai_router_shadow_traffic_total",
    "Total shadow requests sent",
    ["provider", "model"],
)

# Benchmark metrics
benchmark_latency = Gauge(
    "ai_router_benchmark_latency_ms",
    "Average latency per window",
    ["provider", "window"],
)
benchmark_throughput = Gauge(
    "ai_router_benchmark_throughput",
    "Requests per second",
    ["provider", "window"],
)
benchmark_tokens_per_sec = Gauge(
    "ai_router_benchmark_tokens_per_sec",
    "Tokens per second",
    ["provider", "window"],
)
benchmark_failure_rate = Gauge(
    "ai_router_benchmark_failure_rate",
    "Failure rate per window",
    ["provider", "window"],
)
benchmark_timeout_rate = Gauge(
    "ai_router_benchmark_timeout_rate",
    "Timeout rate per window",
    ["provider", "window"],
)
benchmark_p95_latency = Gauge(
    "ai_router_benchmark_p95_latency_ms",
    "P95 latency per window",
    ["provider", "window"],
)
benchmark_first_token_latency = Gauge(
    "ai_router_benchmark_first_token_latency_ms",
    "Average first token latency",
    ["provider", "window"],
)


_start_time = time.time()


def record_request(provider: str, model: str, task: str):
    request_total.labels(provider=provider, model=model, task=task).inc()
    provider_requests_total.labels(provider=provider).inc()


def record_success(provider: str, model: str):
    request_success.labels(provider=provider, model=model).inc()


def record_failure(provider: str, model: str, error_type: str = "unknown"):
    request_failed.labels(provider=provider, model=model, error_type=error_type).inc()
    provider_failure_total.labels(provider=provider, error_type=error_type).inc()


def record_latency(provider: str, model: str, latency_ms: float):
    provider_latency_seconds.labels(provider=provider, model=model).observe(latency_ms / 1000.0)


def record_cache_hit(cache_name: str = "responses"):
    cache_hit.labels(cache_name=cache_name).inc()


def record_cache_miss(cache_name: str = "responses"):
    cache_miss.labels(cache_name=cache_name).inc()


def record_tokens(provider: str, model: str, prompt_tokens: int, completion_tokens: int):
    tokens_total.labels(provider=provider, model=model, type="prompt").inc(prompt_tokens)
    tokens_total.labels(provider=provider, model=model, type="completion").inc(completion_tokens)


def record_cost(provider: str, model: str, cost_usd: float):
    cost_usd_total.labels(provider=provider, model=model).inc(cost_usd)


def set_circuit_breaker_state(provider: str, state: str):
    val = {"closed": 0, "half-open": 1, "open": 2}.get(state, 0)
    circuit_breaker_state.labels(provider=provider).set(val)


def record_fallback(provider: str, model: str, from_provider: str = ""):
    fallback_total.labels(provider=provider, model=model, from_provider=from_provider).inc()


def record_rate_limit():
    rate_limit_total.inc()


def inc_active_requests():
    active_requests.inc()


def dec_active_requests():
    active_requests.dec()


def set_provider_health(provider: str, healthy: bool):
    provider_health.labels(provider=provider).set(1 if healthy else 0)


def set_provider_latency(provider: str, latency_ms: float):
    provider_latency_gauge.labels(provider=provider).set(latency_ms)


def update_uptime():
    uptime_seconds.set(time.time() - _start_time)


def record_distribution_selection(provider: str, model: str, is_canary: bool = False, is_shadow: bool = False):
    distribution_selections_total.labels(provider=provider, model=model).inc()
    if is_canary:
        canary_traffic_total.labels(provider=provider, model=model).inc()
    if is_shadow:
        shadow_traffic_total.labels(provider=provider, model=model).inc()


def update_distribution_metrics():
    try:
        from app.traffic_distribution import traffic_distribution

        for w in traffic_distribution.get_weights():
            distribution_weight.labels(provider=w["provider"], model=w["model"]).set(w["weight"])
    except Exception:
        pass


def update_benchmark_metrics():
    """Update Prometheus gauges from live benchmark data."""
    try:
        from app.benchmark.live import live_benchmark

        snapshot = live_benchmark.get_snapshot()
        for provider, windows in snapshot.items():
            for window_name, data in windows.items():
                benchmark_latency.labels(provider=provider, window=window_name).set(data.get("avg_latency_ms", 0))
                benchmark_throughput.labels(provider=provider, window=window_name).set(
                    data.get("throughput_req_per_sec", 0)
                )  # noqa: E501
                benchmark_tokens_per_sec.labels(provider=provider, window=window_name).set(
                    data.get("tokens_per_sec", 0)
                )  # noqa: E501
                benchmark_failure_rate.labels(provider=provider, window=window_name).set(data.get("failure_rate", 0))
                benchmark_timeout_rate.labels(provider=provider, window=window_name).set(data.get("timeout_rate", 0))
                benchmark_p95_latency.labels(provider=provider, window=window_name).set(data.get("p95_latency_ms", 0))
                benchmark_first_token_latency.labels(provider=provider, window=window_name).set(
                    data.get("avg_first_token_latency_ms", 0)
                )  # noqa: E501
    except Exception:
        pass


def get_metrics():
    update_uptime()
    update_benchmark_metrics()
    update_distribution_metrics()
    return generate_latest(REGISTRY)
