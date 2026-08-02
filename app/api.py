"""FastAPI application for AI Router with dashboard and Prometheus metrics."""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.config import config_manager
from app.exceptions import (
    AIRouterError,
    AllProvidersFailedError,
    ConfigurationError,
    NoHealthyProviderError,
    ProviderError,
    RateLimitError,
    ValidationError,
)
from app.models import (
    BenchmarkRequest,
    BenchmarkResponse,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthCheckResponse,
    LogEntry,
    ModelInfo,
    ProviderConfig,
    ProviderStatus,
    ReloadConfigResponse,
    StatsSummary,
    StreamChunk,
    TaskType,
)
from app.providers.manager import provider_manager
from app.router import router
from app.stats import stats
from app.logger import logger
from app.cache import cache_manager
from app.rate_limit import rate_limiter, RateLimitConfig
from app.costs import token_accounting
from app.metrics import (
    get_metrics,
    inc_active_requests,
    dec_active_requests,
    record_cache_hit,
    record_cache_miss,
    record_rate_limit,
)
from app.event_bus import event_bus
from app.orchestration.models import (
    OrchestrationRequest,
    OrchestrationResponse,
    WorkflowDefinition,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await router.initialize()
    rate_limiter.set_default(RateLimitConfig(requests=100, window_seconds=60))
    config_manager.enable_watcher(callback=lambda: None)

    # Distributed lifecycle (Stage 8)
    _distributed_mode = os.getenv("DISTRIBUTED_MODE", "0") == "1"
    _distributed_resources = []

    if _distributed_mode:
        from app.distributed.distributed_queue import DistributedTaskQueue
        from app.distributed.distributed_scheduler import DistributedScheduler
        from app.distributed.event_bus import DistributedEventBus, EventTypes
        from app.distributed.idempotency import IdempotencyGuard
        from app.distributed.lease import LeaseManager
        from app.distributed.redis_client import AsyncRedisClient
        from app.distributed.tracing import init_tracing
        from app.distributed.worker_registry import WorkerRegistry

        logger.info("Starting in distributed mode")

        if os.getenv("OTEL_ENABLED", "0") == "1":
            init_tracing(
                service_name=os.getenv("OTEL_SERVICE_NAME", "ai-router"),
                exporter_endpoint=os.getenv("OTEL_EXPORTER_ENDPOINT", ""),
            )

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_client = AsyncRedisClient(url=redis_url)
        await redis_client.connect()
        _distributed_resources.append(redis_client)

        task_queue = DistributedTaskQueue(redis_client)
        lease_manager = LeaseManager(redis_client)
        worker_registry = WorkerRegistry(redis_client)
        scheduler = DistributedScheduler(redis_client)
        event_bus = DistributedEventBus(redis_client)
        idempotency = IdempotencyGuard(redis_client)

        await worker_registry.start_heartbeat_loop()
        await scheduler.start()
        await event_bus.start_listener()
        await event_bus.publish(EventTypes.WORKER_STARTED, {
            "instance": scheduler._instance_id,
        })

        logger.info("Distributed services started")

    yield

    if _distributed_mode:
        try:
            await event_bus.publish(EventTypes.WORKER_STOPPED, {
                "instance": scheduler._instance_id,
            })
        except Exception:
            pass
        await scheduler.stop()
        await worker_registry.stop_heartbeat()
        await event_bus.stop_listener()
        for res in reversed(_distributed_resources):
            try:
                await res.close()
            except Exception:
                pass
        logger.info("Distributed services stopped")

    await router.close()
    logger.shutdown()


def _get_build_metadata() -> dict:
    try:
        import json
        meta_file = os.path.join(os.path.dirname(__file__), ".meta", "build.json")
        if os.path.isfile(meta_file):
            with open(meta_file) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _get_app_version() -> str:
    """Resolve the app version from build metadata, falling back to the release constant."""
    version = _get_build_metadata().get("version")
    return version if version else "1.0.0-rc.1"


app = FastAPI(
    title="AI Router Gateway",
    description="Production-ready AI Gateway with intelligent routing, health checks, and fallback",
    version=_get_app_version(),
    lifespan=lifespan,
)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)

if ALLOWED_HOSTS != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.middleware("http")
async def request_body_limit(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length:
            limit = int(os.getenv("MAX_REQUEST_SIZE_BYTES", "10485760"))  # 10MB default
            if int(content_length) > limit:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"error": "Request too large", "limit_bytes": limit},
                )
    return await call_next(request)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    inc_active_requests()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        raise
    finally:
        dec_active_requests()


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in ["/health", "/metrics", "/", "/favicon.ico"]:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    allowed, info = rate_limiter.is_allowed(f"ip:{client_ip}")

    if not allowed:
        record_rate_limit()
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Rate limit exceeded", "retry_after": info.get("retry_after", 60)},
            headers={
                "X-RateLimit-Limit": str(info.get("limit", 100)),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(info.get("reset_time", 0))),
                "Retry-After": str(info.get("retry_after", 60)),
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(info.get("limit", 100))
    response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 99))
    response.headers["X-RateLimit-Reset"] = str(int(info.get("reset_time", 0)))
    return response


@app.exception_handler(AIRouterError)
async def ai_router_error_handler(request: Request, exc: AIRouterError):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
        headers={"X-Request-ID": request.state.request_id},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc)},
        headers={"X-Request-ID": request.state.request_id},
    )


# ==================== Health & Status ====================


def _get_memory_usage() -> dict:
    try:
        with open("/proc/self/status") as f:
            data = f.read()
        vm = 0
        rss = 0
        for line in data.splitlines():
            if line.startswith("VmSize:"):
                vm = int(line.split()[1])
            elif line.startswith("VmRSS:"):
                rss = int(line.split()[1])
        return {"virtual_mb": vm / 1024, "rss_mb": rss / 1024}
    except Exception:
        return {}


def _get_cpu_usage() -> dict:
    try:
        with open("/proc/self/stat") as f:
            parts = f.read().split()
        utime = int(parts[13])
        stime = int(parts[14])
        starttime = int(parts[21])
        with open("/proc/stat") as f:
            total = sum(int(v) for v in f.read().split()[1:])
        hertz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        uptime_s = (total - starttime) / hertz
        cpu_percent = (utime + stime) / hertz / max(uptime_s, 1) * 100
        return {"cpu_percent": round(cpu_percent, 1), "uptime_s": round(uptime_s)}
    except Exception:
        return {}


def _get_uptime() -> float:
    from app.metrics import _start_time
    return time.time() - _start_time


@app.get("/health")
async def health_check() -> dict[str, Any]:
    provider_health = await provider_manager.check_health()
    healthy_count = sum(1 for h in provider_health.values() if h.status == ProviderStatus.HEALTHY)
    degraded = sum(1 for h in provider_health.values() if h.status == ProviderStatus.DEGRADED)

    build = _get_build_metadata()
    memory = _get_memory_usage()
    cpu = _get_cpu_usage()

    deps = {
        "config_loaded": config_manager.config is not None,
    }

    overall = "ok"
    if healthy_count == 0:
        overall = "degraded"

    return {
        "status": overall,
        "version": build.get("version", app.version),
        "commit": build.get("git_commit", "unknown"),
        "build_date": build.get("build_date", "unknown"),
        "python_version": build.get("python_version", "unknown"),
        "uptime_seconds": _get_uptime(),
        "config_hash": config_manager.config_hash,
        "providers": {name: health.status.value for name, health in provider_health.items()},
        "healthy_count": healthy_count,
        "degraded_count": degraded,
        "total_providers": len(provider_health),
        "memory": memory,
        "cpu": cpu,
        "dependencies": deps,
        "timestamp": logger.now().isoformat(),
    }


@app.get("/health/providers")
async def providers_health() -> dict[str, HealthCheckResponse]:
    return await provider_manager.check_health()


@app.get("/ready")
async def readiness_check() -> dict[str, Any]:
    """Readiness probe: the router accepts traffic only when configuration is
    loaded and at least one provider is available."""
    config_loaded = config_manager.config is not None
    provider_health = await provider_manager.check_health()
    available = any(
        h.status in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)
        for h in provider_health.values()
    )
    ready = config_loaded and available
    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if ready else "unavailable",
            "config_loaded": config_loaded,
            "providers_available": available,
            "healthy_count": sum(1 for h in provider_health.values() if h.status == ProviderStatus.HEALTHY),
            "total_providers": len(provider_health),
        },
    )


@app.get("/health/providers/{provider_name}")
async def provider_health(provider_name: str) -> HealthCheckResponse:
    health = await provider_manager.check_health(provider_name)
    if provider_name not in health:
        raise HTTPException(status_code=404, detail=f"Provider {provider_name} not found")
    return health[provider_name]


# ==================== Prometheus Metrics ====================

@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    data = get_metrics()
    return PlainTextResponse(content=data.decode(), media_type="text/plain")


# ==================== Provider & Model Endpoints ====================

@app.get("/providers")
async def list_providers() -> dict[str, Any]:
    providers = provider_manager.get_all()
    health = provider_manager.get_health_status()
    result = []
    for name, provider in providers.items():
        h = health.get(name) if isinstance(health, dict) else None
        result.append({
            "name": name,
            "display_name": provider.display_name,
            "status": h.status.value if h else ProviderStatus.UNKNOWN.value,
            "latency_ms": h.latency_ms if h else None,
            "last_check": h.checked_at.isoformat() if h and h.checked_at else None,
        })
    return {"providers": result, "total": len(result), "healthy_count": sum(1 for p in result if p["status"] == ProviderStatus.HEALTHY.value)}


@app.get("/providers/{provider_name}/models")
async def list_provider_models(provider_name: str) -> list[ModelInfo]:
    provider = provider_manager.get(provider_name)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider {provider_name} not found")
    return await provider.list_models()


@app.get("/models")
async def list_all_models() -> dict[str, Any]:
    """Model discovery: aggregate models from all providers."""
    all_models = await provider_manager.list_models()
    return {"models": [m.model_dump() for m in all_models], "total": len(all_models)}


@app.get("/models/{task}")
async def list_models_for_task(task: str) -> list[ModelInfo]:
    candidates = config_manager.get_task_config(task)
    if not candidates:
        raise HTTPException(status_code=404, detail=f"Task {task} not configured")
    models = []
    for provider_name, model_name in [(candidates.primary.name, candidates.primary.model)] + [(f.name, f.model) for f in candidates.fallback]:
        provider = provider_manager.get(provider_name)
        if provider:
            all_models = await provider.list_models()
            model = next((m for m in all_models if m.id == model_name), None)
            if model:
                models.append(model)
    return models


# ==================== Chat Completion ====================

@app.post("/v1/chat/completions")
async def chat_completion(request: ChatRequest):
    """OpenAI-compatible chat completion with streaming support."""
    if request.stream:
        async def generate():
            try:
                timeout = request.max_tokens * 0.1 if request.max_tokens else 120.0
                async with asyncio.timeout(timeout):
                    async for chunk in router.stream_chat(request):
                        yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"timeout\"}]}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                yield "data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"cancelled\"}]}\n\n"
                yield "data: [DONE]\n\n"
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    cache_key = {"model": request.model, "messages": [m.model_dump() for m in request.messages], "temperature": request.temperature, "max_tokens": request.max_tokens}
    cached = cache_manager.get_cache("responses").get(cache_key)
    if cached:
        record_cache_hit()
        await event_bus.emit("cache.hit", cache_name="responses")
        return cached
    record_cache_miss()
    await event_bus.emit("cache.miss", cache_name="responses")

    try:
        response = await router.chat(request)
        if not request.stream and response:
            cache_manager.get_cache("responses").set(cache_key, response, ttl=300)
        return response
    except NoHealthyProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except AllProvidersFailedError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ProviderError as e:
        raise HTTPException(status_code=e.status_code, detail=e.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Embeddings ====================

@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    try:
        return await router.embeddings(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Statistics ====================

@app.get("/stats", response_model=StatsSummary)
async def get_stats() -> StatsSummary:
    return stats.summary()


@app.get("/stats/providers")
async def get_provider_stats() -> dict[str, Any]:
    return router.get_provider_stats()


@app.get("/stats/providers/{provider_name}")
async def get_provider_stat(provider_name: str) -> dict[str, Any]:
    result = stats.get_provider_stats(provider_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Provider {provider_name} not found")
    return result


@app.get("/stats/models/{provider_name}/{model_name}")
async def get_model_stats(provider_name: str, model_name: str) -> dict[str, Any]:
    result = stats.get_model_stats(provider_name, model_name)
    if not result:
        raise HTTPException(status_code=404, detail="Model stats not found")
    return result


@app.get("/stats/tasks")
async def get_task_stats() -> dict[str, int]:
    return stats.get_task_stats()


@app.get("/stats/errors")
async def get_error_stats() -> dict[str, int]:
    return stats.get_error_stats()


@app.post("/stats/reset")
async def reset_stats() -> dict[str, str]:
    stats.reset()
    token_accounting.reset()
    return {"message": "Statistics and token accounting reset successfully"}


# ==================== Logs ====================

@app.get("/logs")
async def get_logs(limit: int = 100, provider: str | None = None, success: bool | None = None) -> list[LogEntry]:
    return logger.get_logs(limit=limit, provider=provider, success=success)


@app.get("/logs/{request_id}")
async def get_log_by_request_id(request_id: str) -> LogEntry | None:
    return logger.get_log(request_id)


@app.delete("/logs")
async def clear_logs() -> dict[str, str]:
    logger.clear()
    return {"message": "Logs cleared"}


# ==================== Live Benchmark ====================

@app.get("/benchmark/live")
async def get_live_benchmark() -> dict[str, Any]:
    """Live benchmark data with rolling windows for all providers."""
    from app.benchmark.live import live_benchmark
    snapshot = live_benchmark.get_snapshot()
    ranking = live_benchmark.get_ranking()
    fastest = live_benchmark.get_fastest()
    return {
        "providers": snapshot,
        "ranking": ranking,
        "fastest_provider": fastest,
        "total_providers": len(snapshot),
    }


@app.get("/benchmark/live/{provider_name}")
async def get_provider_benchmark(provider_name: str) -> dict[str, Any]:
    """Live benchmark data for a specific provider."""
    from app.benchmark.live import live_benchmark
    snapshot = live_benchmark.get_provider_snapshot(provider_name)
    if not snapshot or not any(w.get("requests", 0) > 0 for w in snapshot.values()):
        raise HTTPException(status_code=404, detail=f"No benchmark data for provider {provider_name}")
    return {"provider": provider_name, "windows": snapshot}


@app.post("/benchmark/live/reset")
async def reset_benchmark() -> dict[str, str]:
    """Reset all live benchmark data."""
    from app.benchmark.live import live_benchmark
    live_benchmark.reset()
    return {"message": "Live benchmark data reset successfully"}


# ==================== Benchmark ====================

@app.get("/benchmark", response_model=BenchmarkResponse)
async def run_benchmark(
    model: str = "gpt-4o-mini",
    provider: str | None = None,
    num_requests: int = 10,
    concurrency: int = 5,
    stream: bool = False,
    prompt: str = "Say hello in one word",
) -> BenchmarkResponse:
    """Run a benchmark against the router."""
    from benchmarks.runner import run_benchmark as _run_benchmark

    result = await _run_benchmark(
        model=model,
        provider=provider,
        num_requests=num_requests,
        concurrency=concurrency,
        stream=stream,
        prompt=prompt,
    )
    await event_bus.emit("benchmark.completed", model=model, provider=provider, num_requests=num_requests, result=result.to_dict())
    return BenchmarkResponse(**result.to_dict())


# ==================== Configuration ====================

@app.get("/config")
async def get_config() -> dict[str, Any]:
    config = config_manager.config
    if not config:
        return {}
    provider_configs = config_manager.get_all_provider_configs()
    return {
        "version": app.version,
        "config_hash": config_manager.config_hash,
        "tasks": {name: {"primary": {"provider": t.primary.name, "model": t.primary.model}, "fallback": [{"provider": f.name, "model": f.model} for f in t.fallback]} for name, t in config.tasks.items()},
        "task_names": list(config.tasks.keys()),
        "default_task": config.default_task,
        "scoring": config.scoring,
        "providers": [{"name": p.name, "model": p.model, "display_name": p.display_name, "enabled": p.enabled, "priority": p.priority} for p in provider_configs],
        "cache_ttl": config.cache_ttl,
        "rate_limit": config.rate_limit,
        "rate_limit_window": config.rate_limit_window,
        "timeout": config.timeout,
        "health_check_interval": config.health_check_interval,
    }


@app.post("/reload-config", response_model=ReloadConfigResponse)
async def reload_config() -> ReloadConfigResponse:
    result = config_manager.reload()
    if result.success:
        await provider_manager.reload()
    return result


# ==================== Analytics ====================

@app.get("/analytics/providers")
async def analytics_providers() -> dict[str, Any]:
    """Historical analytics for all providers with reputation, trend, uptime."""
    from app.reputation import compute_reputation, compute_trend

    provider_stats = router.get_provider_stats()
    health = router.get_health_summary()
    result = {}
    for name, ps in provider_stats.items():
        h = health.get(name, {})
        result[name] = {
            **ps,
            "circuit_state": h.get("circuit_state", "closed"),
            "disabled": h.get("disabled", False),
        }
    return {"providers": result, "total": len(result)}


@app.get("/analytics/providers/{provider_name}")
async def analytics_provider(provider_name: str) -> dict[str, Any]:
    """Analytics for a single provider."""
    provider_stats = router.get_provider_stats()
    if provider_name not in provider_stats:
        raise HTTPException(status_code=404, detail=f"Provider {provider_name} not found")
    health = router.get_health_summary()
    h = health.get(provider_name, {})
    return {
        **provider_stats[provider_name],
        "circuit_state": h.get("circuit_state", "closed"),
        "disabled": h.get("disabled", False),
    }


# ==================== Cache ====================

@app.get("/cache/stats")
async def get_cache_stats() -> dict[str, Any]:
    return cache_manager.get_all_stats()


@app.post("/cache/clear")
async def clear_cache(cache_name: str | None = None) -> dict[str, str]:
    if cache_name:
        cache_manager.get_cache(cache_name).clear()
        return {"message": f"Cache '{cache_name}' cleared"}
    cache_manager.clear_all()
    return {"message": "All caches cleared"}


# ==================== Dashboard API ====================

@app.get("/dashboard")
async def dashboard() -> dict[str, Any]:
    """Unified dashboard endpoint."""
    provider_health = provider_manager.get_health_status()
    if isinstance(provider_health, dict):
        providers_data = {name: {"status": h.status.value, "latency_ms": h.latency_ms, "checked_at": h.checked_at.isoformat() if h.checked_at else None, "error": h.error} for name, h in provider_health.items()}
    else:
        providers_data = {}

    all_models = await provider_manager.list_models()
    models_data = [{"id": m.id, "provider": m.provider, "owned_by": m.owned_by} for m in all_models[:50]]

    s = stats.summary()
    usage_data = {
        "total_requests": s.total_requests,
        "successful_requests": s.successful_requests,
        "failed_requests": s.failed_requests,
        "success_rate": s.success_rate,
        "provider_usage": s.provider_usage,
        "model_usage": s.model_usage,
    }

    latency_data = {
        "average_latency_ms": s.average_latency_ms,
        "provider_latency": {name: m.avg_latency_ms for name, m in stats._get_provider_latency().items()} if hasattr(stats, '_get_provider_latency') else {},
    }

    uptime_data = {"uptime_seconds": stats.get_uptime_seconds()}

    cache_stats = cache_manager.get_all_stats()
    cache_data = {name: {"hits": cs.get("hits", 0), "misses": cs.get("misses", 0), "hit_rate": cs.get("hit_rate", 0.0), "size": cs.get("size", 0)} for name, cs in cache_stats.items()}

    cost_data = token_accounting.get_summary()

    return {
        "providers": providers_data,
        "models": {"total": len(all_models), "list": models_data},
        "usage": usage_data,
        "latency": latency_data,
        "uptime": uptime_data,
        "cache": cache_data,
        "costs": cost_data,
        "timestamp": logger.now().isoformat(),
    }


# ==================== Token Accounting ====================

@app.get("/costs")
async def get_costs() -> dict[str, Any]:
    return token_accounting.get_summary()


@app.get("/costs/{provider}")
async def get_provider_cost(provider: str) -> dict[str, Any]:
    result = token_accounting.get_provider_cost(provider)
    if not result:
        raise HTTPException(status_code=404, detail=f"Provider {provider} not found")
    return result


# ==================== Root ====================

# ==================== Traffic Distribution ====================

@app.get("/distribution")
async def get_distribution() -> dict[str, Any]:
    from app.traffic_distribution import traffic_distribution
    return traffic_distribution.get_distribution_report()


@app.post("/distribution/rebalance")
async def force_rebalance() -> dict[str, str]:
    from app.traffic_distribution import traffic_distribution
    traffic_distribution.force_rebalance()
    return {"message": "Distribution weights rebalanced"}


@app.post("/distribution/reset")
async def reset_distribution_stats() -> dict[str, str]:
    from app.traffic_distribution import traffic_distribution
    traffic_distribution.reset_stats()
    return {"message": "Distribution statistics reset"}


@app.post("/distribution/config")
async def set_distribution_config(enabled: bool = True, min_weight: float = 0.01) -> dict[str, str]:
    from app.traffic_distribution import TrafficDistributionConfig, traffic_distribution
    cfg = traffic_distribution.config
    cfg.enabled = enabled
    cfg.min_weight = min_weight
    traffic_distribution.config = cfg
    traffic_distribution.force_rebalance()
    return {"message": f"Distribution config updated: enabled={enabled}, min_weight={min_weight}"}


# ==================== Capability Registry ====================

@app.get("/capabilities")
async def list_capabilities() -> dict[str, Any]:
    """List all models and their capabilities from the registry."""
    from app.capability_registry import capability_registry
    return {
        "total_models": len(capability_registry),
        "providers": capability_registry.get_providers(),
        "models": [cap.to_dict() for cap in capability_registry.get_all_models()],
    }


@app.get("/capabilities/{provider_name}")
async def get_provider_capabilities(provider_name: str) -> dict[str, Any]:
    """List capabilities for all models of a provider."""
    from app.capability_registry import capability_registry
    models = capability_registry.get_models_by_provider(provider_name)
    if not models:
        raise HTTPException(status_code=404, detail=f"No registry entries for provider {provider_name}")
    return {
        "provider": provider_name,
        "total_models": len(models),
        "models": [cap.to_dict() for cap in models],
    }


# ==================== Token Intelligence ====================

@app.get("/tokens")
async def get_token_intelligence(model: str | None = None) -> dict[str, Any]:
    """Token intelligence statistics and estimates."""
    from app.token_intelligence import token_intelligence
    summary = token_intelligence.get_summary()
    if model:
        stats = token_intelligence.get_stats(model)
        return {"summary": summary, "model_stats": stats}
    stats = token_intelligence.get_stats()
    return {"summary": summary, "models": stats}


@app.get("/tokens/estimate")
async def estimate_tokens(text: str = "", model: str = "gpt-4o", provider: str = "") -> dict[str, Any]:
    """Estimate tokens for a text string."""
    from app.token_intelligence import token_intelligence
    count = token_intelligence.estimate(text, model, provider)
    cost = token_intelligence.estimate_request_cost(provider or "openai", model, count)
    return {
        "text_length": len(text),
        "estimated_tokens": count,
        "model": model,
        "provider": provider or "openai",
        "estimated_cost": cost,
    }


# ==================== Capability Registry ====================

@app.get("/capabilities/{provider_name}/{model_name}")
async def get_model_capability(provider_name: str, model_name: str) -> dict[str, Any]:
    """Get capability for a specific model."""
    from app.capability_registry import capability_registry
    cap = capability_registry.get(provider_name, model_name)
    if not cap:
        raise HTTPException(status_code=404, detail=f"No registry entry for {provider_name}/{model_name}")
    return cap.to_dict()


# ==================== Version ====================

@app.get("/version")
async def version_info() -> dict:
    build = _get_build_metadata()
    return {
        "version": build.get("version", app.version),
        "git_commit": build.get("git_commit", "unknown"),
        "build_date": build.get("build_date", "unknown"),
        "python_version": build.get("python_version", f"{sys.version_info.major}.{sys.version_info.minor}"),
        "uvicorn_version": uvicorn.__version__ if hasattr(uvicorn, "__version__") else "unknown",
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": "AI Router Gateway",
        "version": app.version,
        "description": "Production-ready AI Gateway with intelligent routing",
        "docs": "/docs",
        "version_endpoint": "/version",
        "health": "/health",
        "metrics": "/metrics",
        "config": "/config",
        "dashboard": "/dashboard",
    }


# ==================== Plugin System ====================


@app.get("/plugins")
async def list_plugins() -> dict[str, Any]:
    """List all loaded plugins with their status."""
    report = router.plugin_registry.get_report()
    return report


@app.post("/plugins/reload")
async def reload_plugins() -> dict[str, Any]:
    """Rediscover and reload all plugins from plugins/ directory."""
    loaded = router.plugin_registry.discover_and_load()
    return {"message": "Plugins reloaded", "loaded": loaded}


@app.post("/plugins/enable")
async def enable_plugin(name: str) -> dict[str, str]:
    """Enable a plugin by name."""
    if router.plugin_registry.enable(name):
        return {"message": f"Plugin '{name}' enabled"}
    raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")


@app.post("/plugins/disable")
async def disable_plugin(name: str) -> dict[str, str]:
    """Disable a plugin by name."""
    if router.plugin_registry.disable(name):
        return {"message": f"Plugin '{name}' disabled"}
    raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")


@app.get("/plugins/events")
async def list_plugin_events(limit: int = 50) -> dict[str, Any]:
    """List recent event bus events."""
    return {
        "total_events": len(event_bus.event_names()),
        "registered_events": event_bus.event_names(),
        "recent": event_bus.get_history(limit=limit),
    }


# ==================== Classifier Management ====================


@app.get("/classifier")
async def get_classifier_info() -> dict[str, Any]:
    """Get current classifier information."""
    from app.classifier import classifier
    return classifier.get_info()


# ==================== Custom Providers ====================


@app.get("/providers/custom")
async def list_custom_providers() -> dict[str, Any]:
    """List discovered custom providers in providers/ directory."""
    from app.providers.discovery import discover_custom_providers
    discovered = discover_custom_providers()
    return {
        "total": len(discovered),
        "providers": list(discovered.keys()),
    }


# ==================== Orchestration API ====================


@app.post("/v1/orchestrate")
async def orchestrate(request: OrchestrationRequest):
    """Run an orchestrated multi-agent workflow."""
    from app.orchestration import orchestrator

    if request.stream:
        async def generate():
            try:
                async for chunk in orchestrator.orchestrate_stream(request):
                    yield f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"timeout\"}]}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                yield "data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"cancelled\"}]}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return await orchestrator.orchestrate(request)


@app.post("/v1/agents")
async def run_agents(
    prompt: str = "",
    agents: list[str] = ["chat"],
    parallel: bool = False,
    reflection: bool = False,
) -> OrchestrationResponse:
    """Execute a set of agents on a prompt."""
    from app.orchestration import orchestrator
    req = OrchestrationRequest(
        prompt=prompt,
        agents=agents,
        mode="multi" if len(agents) > 1 else "single",
        parallel=parallel,
        reflection=reflection,
    )
    return await orchestrator.orchestrate(req)


@app.post("/v1/workflow")
async def run_workflow(workflow: WorkflowDefinition) -> OrchestrationResponse:
    """Execute a defined workflow."""
    from app.orchestration import orchestrator
    req = OrchestrationRequest(
        mode="workflow",
        workflow=workflow,
    )
    return await orchestrator.orchestrate(req)


@app.post("/v1/consensus")
async def run_consensus(
    prompt: str = "",
    providers: list[str] = ["openai", "anthropic", "google"],
    strategy: str = "majority_vote",
) -> OrchestrationResponse:
    """Run consensus across multiple providers."""
    from app.orchestration import orchestrator
    req = OrchestrationRequest(
        prompt=prompt,
        mode="consensus",
        consensus=True,
        consensus_providers=providers,
        consensus_strategy=strategy,
    )
    return await orchestrator.orchestrate(req)


@app.post("/v1/debate")
async def run_debate(
    prompt: str = "",
    provider_a: str = "openai",
    provider_b: str = "anthropic",
) -> OrchestrationResponse:
    """Run a debate between two providers."""
    from app.orchestration import orchestrator
    req = OrchestrationRequest(
        prompt=prompt,
        mode="debate",
        debate=True,
        debate_provider_a=provider_a,
        debate_provider_b=provider_b,
    )
    return await orchestrator.orchestrate(req)


# ==================== Task Queue API ====================

_task_queue = None


def _get_task_queue():
    global _task_queue
    if _task_queue is None:
        from app.tasks.queue import TaskQueue
        _task_queue = TaskQueue()
    return _task_queue


@app.post("/tasks")
async def create_task(
    task_type: str = "orchestrate",
    priority: int = 0,
    max_retries: int = 3,
    timeout: int = 300,
    session_id: str = "",
) -> dict:
    """Create a background task."""
    queue = _get_task_queue()
    task = queue.create_task(
        task_type=task_type,
        payload={},
        priority=priority,
        max_retries=max_retries,
        timeout=timeout,
        session_id=session_id,
    )
    return {"task_id": task["task_id"], "state": task["state"]}


@app.post("/tasks/orchestrate")
async def create_orchestrate_task(
    request: OrchestrationRequest,
    priority: int = 0,
    max_retries: int = 3,
) -> dict:
    """Submit an orchestration request as a background task."""
    queue = _get_task_queue()
    task = queue.create_task(
        task_type="orchestrate",
        payload=request.model_dump(),
        priority=priority,
        max_retries=max_retries,
        timeout=request.timeout or 300,
    )
    return {"task_id": task["task_id"], "state": task["state"]}


@app.get("/tasks")
async def list_tasks(
    state: str = "",
    task_type: str = "",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List all tasks with optional filters."""
    queue = _get_task_queue()
    return queue.list_tasks(state=state, task_type=task_type, limit=limit, offset=offset)


@app.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get task details."""
    queue = _get_task_queue()
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str) -> dict:
    """Delete a task."""
    queue = _get_task_queue()
    queue.delete_task(task_id)
    return {"status": "deleted", "task_id": task_id}


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    """Cancel a task."""
    queue = _get_task_queue()
    cancelled = queue.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Task cannot be cancelled")
    return {"status": "cancelled", "task_id": task_id}


@app.get("/tasks/{task_id}/graph")
async def get_task_graph(task_id: str) -> dict:
    """Get execution graph for a task."""
    queue = _get_task_queue()
    task = queue.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    graph = task.get("graph") or {"nodes": [], "edges": []}
    timeline = task.get("timeline", [])
    return {
        "task_id": task_id,
        "state": task.get("state", ""),
        "graph": graph,
        "timeline": timeline,
        "duration_ms": (
            (task.get("completed_at", 0) - task.get("started_at", 0)) * 1000
            if task.get("completed_at") and task.get("started_at")
            else 0
        ),
        "cost": task.get("result", {}).get("total_cost", 0) if task.get("result") else 0,
        "tokens": task.get("result", {}).get("total_tokens", 0) if task.get("result") else 0,
    }


@app.get("/tasks/queue/depth")
async def get_queue_depth() -> dict:
    """Get queue depth by state."""
    queue = _get_task_queue()
    return queue.get_depth()


# ==================== Approval API ====================

_approval_manager = None


def _get_approval_manager():
    global _approval_manager
    if _approval_manager is None:
        from app.orchestration.approval import ApprovalManager
        _approval_manager = ApprovalManager()
    return _approval_manager


@app.post("/approval/checkpoints")
async def create_approval_checkpoint(
    workflow_id: str = "",
    step_id: str = "",
    prompt: str = "",
) -> dict:
    """Create an approval checkpoint."""
    mgr = _get_approval_manager()
    cp = mgr.create_checkpoint(workflow_id, step_id, prompt)
    return {
        "checkpoint_id": cp.checkpoint_id,
        "workflow_id": cp.workflow_id,
        "step_id": cp.step_id,
        "status": cp.status,
        "created_at": cp.created_at,
    }


@app.post("/approval/checkpoints/{checkpoint_id}/approve")
async def approve_checkpoint(
    checkpoint_id: str, user: str = "", notes: str = ""
) -> dict:
    """Approve a pending checkpoint."""
    mgr = _get_approval_manager()
    success = mgr.approve(checkpoint_id, user=user, notes=notes)
    if not success:
        raise HTTPException(
            status_code=400, detail="Checkpoint not found or already decided"
        )
    return {"status": "approved", "checkpoint_id": checkpoint_id}


@app.post("/approval/checkpoints/{checkpoint_id}/reject")
async def reject_checkpoint(
    checkpoint_id: str, user: str = "", notes: str = ""
) -> dict:
    """Reject a pending checkpoint."""
    mgr = _get_approval_manager()
    success = mgr.reject(checkpoint_id, user=user, notes=notes)
    if not success:
        raise HTTPException(
            status_code=400, detail="Checkpoint not found or already decided"
        )
    return {"status": "rejected", "checkpoint_id": checkpoint_id}


@app.get("/approval/pending")
async def list_pending_approvals() -> list[dict]:
    """List all pending approval checkpoints."""
    mgr = _get_approval_manager()
    return [
        {
            "checkpoint_id": cp.checkpoint_id,
            "workflow_id": cp.workflow_id,
            "step_id": cp.step_id,
            "prompt": cp.prompt,
            "created_at": cp.created_at,
        }
        for cp in mgr.list_pending()
    ]


@app.get("/approval/checkpoints")
async def list_all_approvals() -> list[dict]:
    """List all approval checkpoints."""
    mgr = _get_approval_manager()
    return mgr.list_all()


# ---------------------------------------------------------------------------
# Runtime health endpoints (distributed / Stage 8)
# ---------------------------------------------------------------------------

_health_checker: Any | None = None
_health_init_lock = asyncio.Lock()


async def _get_health() -> Any:
    global _health_checker
    if _health_checker is not None:
        return _health_checker
    async with _health_init_lock:
        if _health_checker is not None:
            return _health_checker
        from app.distributed.health import RuntimeHealth
        from app.distributed.distributed_queue import DistributedTaskQueue
        from app.distributed.event_bus import DistributedEventBus
        from app.distributed.redis_client import AsyncRedisClient
        from app.distributed.distributed_scheduler import DistributedScheduler
        from app.distributed.worker_registry import WorkerRegistry
        from app.distributed.lease import LeaseManager

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis = AsyncRedisClient(url=redis_url)
        queue = DistributedTaskQueue(redis)
        registry = WorkerRegistry(redis)
        lease = LeaseManager(redis)
        scheduler = DistributedScheduler(redis)
        bus = DistributedEventBus(redis)
        _health_checker = RuntimeHealth(
            redis=redis,
            queue=queue,
            worker_registry=registry,
            scheduler=scheduler,
            event_bus=bus,
            lease_manager=lease,
        )
        await redis.connect()
    return _health_checker


@app.get("/runtime/health")
async def runtime_health() -> dict:
    """Full runtime health check (Redis, queue, workers, scheduler, event bus)."""
    h = await _get_health()
    return await h.full_health()


@app.get("/runtime/workers")
async def runtime_workers() -> list[dict]:
    """List all registered workers."""
    h = await _get_health()
    return await h.get_workers_list()


@app.get("/runtime/leader")
async def runtime_leader() -> dict:
    """Get the current scheduler leader."""
    h = await _get_health()
    leader = await h.check_scheduler()
    return leader


@app.get("/runtime/queue")
async def runtime_queue() -> dict:
    """Queue depth and stats."""
    h = await _get_health()
    return await h.check_queue()


@app.get("/runtime/events")
async def runtime_events() -> dict:
    """Event bus stats."""
    h = await _get_health()
    return await h.check_event_bus()


# ---------------------------------------------------------------------------
# Knowledge Foundation (Stage 9.1)
# ---------------------------------------------------------------------------

from app.knowledge.service import KnowledgeService
from app.knowledge.validation import ValidationError

_knowledge_repo: Any = None
_knowledge_lock = asyncio.Lock()


async def _get_knowledge_service() -> KnowledgeService:
    global _knowledge_repo
    if _knowledge_repo is None:
        async with _knowledge_lock:
            if _knowledge_repo is None:
                from app.knowledge.repository import create_knowledge_repository
                backend = os.getenv("KNOWLEDGE_STORAGE_BACKEND", "sqlite")
                db_path = os.getenv("KNOWLEDGE_DATABASE_PATH", "knowledge.db")
                _knowledge_repo = create_knowledge_repository(backend=backend, db_path=db_path)
    return KnowledgeService(_knowledge_repo)


@app.post("/knowledge/collections", status_code=201)
async def create_collection(body: dict) -> dict:
    svc = await _get_knowledge_service()
    try:
        coll = await svc.create_collection(
            name=body.get("name", ""),
            description=body.get("description", ""),
            metadata=body.get("metadata"),
            tags=body.get("tags"),
        )
        return coll.to_dict()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/knowledge/collections")
async def list_collections(skip: int = 0, limit: int = 100) -> list[dict]:
    svc = await _get_knowledge_service()
    cols = await svc.list_collections(skip=skip, limit=limit)
    return [c.to_dict() for c in cols]


@app.get("/knowledge/collections/{collection_id}")
async def get_collection(collection_id: str) -> dict:
    svc = await _get_knowledge_service()
    coll = await svc.get_collection(collection_id)
    if not coll:
        raise HTTPException(status_code=404, detail="Collection not found")
    return coll.to_dict()


@app.put("/knowledge/collections/{collection_id}")
async def update_collection(collection_id: str, body: dict) -> dict:
    svc = await _get_knowledge_service()
    try:
        coll = await svc.update_collection(
            collection_id=collection_id,
            name=body.get("name"),
            description=body.get("description"),
            status=body.get("status"),
            metadata=body.get("metadata"),
            tags=body.get("tags"),
        )
        if not coll:
            raise HTTPException(status_code=404, detail="Collection not found")
        return coll.to_dict()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.delete("/knowledge/collections/{collection_id}")
async def delete_collection(collection_id: str) -> dict:
    svc = await _get_knowledge_service()
    ok = await svc.delete_collection(collection_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"deleted": True}


@app.post("/knowledge/documents", status_code=201)
async def create_document(body: dict) -> dict:
    svc = await _get_knowledge_service()
    try:
        doc = await svc.create_document(
            collection_id=body.get("collection_id", ""),
            title=body.get("title", ""),
            content=body.get("content", ""),
            source=body.get("source", ""),
            metadata=body.get("metadata"),
            tags=body.get("tags"),
        )
        return doc.to_dict()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/knowledge/documents")
async def list_documents(
    collection_id: str = "",
    skip: int = 0,
    limit: int = 100,
    query: str = "",
) -> list[dict]:
    svc = await _get_knowledge_service()
    if query:
        docs = await svc.search_documents(query=query, collection_id=collection_id, limit=limit)
    else:
        docs = await svc.list_documents(collection_id=collection_id, skip=skip, limit=limit)
    return [d.to_dict() for d in docs]


@app.get("/knowledge/documents/{document_id}")
async def get_document(document_id: str) -> dict:
    svc = await _get_knowledge_service()
    doc = await svc.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc.to_dict()


@app.put("/knowledge/documents/{document_id}")
async def update_document(document_id: str, body: dict) -> dict:
    svc = await _get_knowledge_service()
    try:
        doc = await svc.update_document(
            document_id=document_id,
            title=body.get("title"),
            content=body.get("content"),
            source=body.get("source"),
            status=body.get("status"),
            metadata=body.get("metadata"),
            tags=body.get("tags"),
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc.to_dict()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.delete("/knowledge/documents/{document_id}")
async def delete_document(document_id: str) -> dict:
    svc = await _get_knowledge_service()
    ok = await svc.delete_document(document_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": True}


@app.get("/knowledge/statistics")
async def knowledge_statistics(collection_id: str = "") -> dict:
    svc = await _get_knowledge_service()
    return await svc.get_statistics(collection_id=collection_id)


@app.post("/knowledge/documents/{document_id}/tags")
async def add_document_tags(document_id: str, body: dict) -> dict:
    svc = await _get_knowledge_service()
    try:
        doc = await svc.add_document_tags(document_id, body.get("tags", []))
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc.to_dict()
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.delete("/knowledge/documents/{document_id}/tags")
async def remove_document_tags(document_id: str, body: dict) -> dict:
    svc = await _get_knowledge_service()
    doc = await svc.remove_document_tags(document_id, body.get("tags", []))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc.to_dict()


# ---------------------------------------------------------------------------
# Knowledge Ingestion (Stage 9.2)
# ---------------------------------------------------------------------------

from app.knowledge.ingestion import IngestionPipeline, IngestionConfig
from app.knowledge.ingestion.validation import IngestionValidationError

_pipeline: IngestionPipeline | None = None
_pipeline_lock = asyncio.Lock()


async def _get_ingestion_pipeline() -> IngestionPipeline:
    global _pipeline
    if _pipeline is None:
        async with _pipeline_lock:
            if _pipeline is None:
                svc = await _get_knowledge_service()
                config = IngestionConfig.from_env()
                _pipeline = IngestionPipeline(knowledge_service=svc, config=config)
    return _pipeline


@app.post("/knowledge/documents/upload", status_code=201)
async def upload_document(
    collection_id: str = Form(...),
    title: str = Form(""),
    file: UploadFile = File(...),
) -> dict:
    pipeline = await _get_ingestion_pipeline()
    data = await file.read()
    try:
        result = await pipeline.ingest_bytes(
            data=data,
            filename=file.filename or "upload.bin",
            collection_id=collection_id,
            title=title or None,
        )
    except IngestionValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if result.is_duplicate:
        raise HTTPException(status_code=409, detail={
            "message": "Duplicate document",
            "document_id": result.document_id,
            "checksum": result.checksum,
        })
    return result.to_dict()


@app.post("/knowledge/documents/import", status_code=201)
async def import_document(body: dict) -> dict:
    path = body.get("path", "")
    if not path:
        raise HTTPException(status_code=422, detail="path is required")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    collection_id = body.get("collection_id", "")
    if not collection_id:
        raise HTTPException(status_code=422, detail="collection_id is required")
    title = body.get("title", "")

    pipeline = await _get_ingestion_pipeline()
    try:
        result = await pipeline.ingest_file(
            path=path,
            collection_id=collection_id,
            title=title or None,
        )
    except IngestionValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if result.is_duplicate:
        raise HTTPException(status_code=409, detail={
            "message": "Duplicate document",
            "document_id": result.document_id,
            "checksum": result.checksum,
        })
    return result.to_dict()


@app.get("/knowledge/documents/{document_id}/metadata")
async def get_document_metadata(document_id: str) -> dict:
    svc = await _get_knowledge_service()
    doc = await svc.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    meta_dict: dict[str, str] = {}
    for km in doc.metadata:
        meta_dict[km.key] = km.value
    return {
        "document_id": doc.id,
        "title": doc.title,
        "source": doc.source,
        "size": meta_dict.get("size", "0"),
        "mime_type": meta_dict.get("mime_type", "unknown"),
        "checksum": meta_dict.get("checksum", ""),
        "encoding": meta_dict.get("encoding", "utf-8"),
        "language": meta_dict.get("language", ""),
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


# ---------------------------------------------------------------------------
# Knowledge Chunking (Stage 9.3)
# ---------------------------------------------------------------------------

from app.knowledge.chunking import ChunkingPipeline, ChunkingConfig, create_strategy, ChunkStatistics

_chunking_pipeline: ChunkingPipeline | None = None
_chunking_lock = asyncio.Lock()


async def _get_chunking_pipeline() -> ChunkingPipeline:
    global _chunking_pipeline
    if _chunking_pipeline is None:
        async with _chunking_lock:
            if _chunking_pipeline is None:
                svc = await _get_knowledge_service()
                config = ChunkingConfig.from_env()
                _chunking_pipeline = ChunkingPipeline(knowledge_service=svc, config=config)
    return _chunking_pipeline


@app.post("/knowledge/chunk", status_code=201)
async def chunk_document(body: dict) -> dict:
    document_id = body.get("document_id", "")
    if not document_id:
        raise HTTPException(status_code=422, detail="document_id is required")

    pipeline = await _get_chunking_pipeline()
    try:
        result = await pipeline.chunk_document(document_id=document_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    saved = await pipeline.save_chunks(document_id, result.chunks)

    return {
        "document_id": result.document_id,
        "total_chunks": result.total_chunks,
        "statistics": result.statistics,
        "chunks": [c.to_dict() for c in saved],
    }


@app.post("/knowledge/chunk/preview", status_code=200)
async def chunk_preview(body: dict) -> dict:
    document_id = body.get("document_id", "")
    if not document_id:
        raise HTTPException(status_code=422, detail="document_id is required")
    strategy_name = body.get("strategy", "")
    chunk_size = body.get("chunk_size", 0)
    overlap = body.get("overlap", 0)

    svc = await _get_knowledge_service()
    doc = await svc.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pipeline = await _get_chunking_pipeline()
    strat = None
    if strategy_name:
        strat = create_strategy(
            strategy_name,
            chunk_size=chunk_size or pipeline.config.chunk_size,
            overlap=overlap if overlap is not None else pipeline.config.chunk_overlap,
        )

    result = await pipeline.preview(doc, strategy=strat)
    return result.to_dict()


@app.get("/knowledge/chunks/{document_id}")
async def list_chunks(document_id: str) -> list[dict]:
    svc = await _get_knowledge_service()
    chunks = await svc._repo.list_chunks(document_id)
    return [c.to_dict() for c in chunks]


@app.get("/knowledge/chunks/{document_id}/{chunk_id}")
async def get_chunk(document_id: str, chunk_id: str) -> dict:
    svc = await _get_knowledge_service()
    chunks = await svc._repo.list_chunks(document_id)
    for c in chunks:
        if c.id == chunk_id:
            return c.to_dict()
    raise HTTPException(status_code=404, detail="Chunk not found")


@app.delete("/knowledge/chunks/{chunk_id}")
async def delete_chunk(chunk_id: str) -> dict:
    svc = await _get_knowledge_service()
    await svc._repo.delete_chunks_by_document(chunk_id)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Knowledge Embedding (Stage 9.4)
# ---------------------------------------------------------------------------

from app.knowledge.embedding import (
    EmbeddingService,
    EmbeddingConfig,
    EmbeddingValidator,
    EmbeddingValidationError,
    create_embedding_provider,
)

_embedding_service: EmbeddingService | None = None
_embedding_lock = asyncio.Lock()


async def _get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        async with _embedding_lock:
            if _embedding_service is None:
                svc = await _get_knowledge_service()
                config = EmbeddingConfig.from_env()
                provider = create_embedding_provider(config.provider, config=config)
                _embedding_service = EmbeddingService(
                    knowledge_service=svc, config=config, provider=provider,
                )
    return _embedding_service


@app.post("/knowledge/embed", status_code=200)
async def embed_text(body: dict) -> dict:
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=422, detail="text is required")

    svc = await _get_embedding_service()
    try:
        result = await svc.embed_text(text)
    except EmbeddingValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return result.to_dict()


@app.post("/knowledge/embed/batch", status_code=200)
async def embed_texts(body: dict) -> list[dict]:
    texts = body.get("texts", [])
    if not texts:
        raise HTTPException(status_code=422, detail="texts is required")

    svc = await _get_embedding_service()
    try:
        results = await svc.embed_texts(texts)
    except EmbeddingValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return [r.to_dict() for r in results]


@app.get("/knowledge/embedding/stats")
async def embedding_stats() -> dict:
    svc = await _get_embedding_service()
    return await svc.get_statistics()


@app.delete("/knowledge/embedding/cache")
async def clear_embedding_cache() -> dict:
    svc = await _get_embedding_service()
    if svc._cache:
        await svc._cache.clear()
    return {"cleared": True}


@app.get("/knowledge/embedding/{chunk_id}")
async def get_embedding_endpoint(chunk_id: str) -> dict:
    svc = await _get_embedding_service()
    record = await svc.get_embedding(chunk_id)
    if record is None:
        raise HTTPException(status_code=404, detail="embedding not found")
    return record.to_dict()


@app.delete("/knowledge/embedding/{chunk_id}", status_code=200)
async def delete_embedding_endpoint(chunk_id: str) -> dict:
    svc = await _get_embedding_service()
    deleted = await svc.delete_embedding(chunk_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="embedding not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Knowledge Vector Store (Stage 9.5)
# ---------------------------------------------------------------------------

from app.knowledge.vector_store import (
    VectorCollection,
    VectorRecord,
    VectorStoreConfig,
    VectorStoreService,
    create_vector_store,
    DistanceMetric,
)

_vector_store_service: VectorStoreService | None = None
_vector_store_lock = asyncio.Lock()


async def _get_vector_store_service() -> VectorStoreService:
    global _vector_store_service
    if _vector_store_service is None:
        async with _vector_store_lock:
            if _vector_store_service is None:
                config = VectorStoreConfig.from_env()
                store = create_vector_store(config)
                _vector_store_service = VectorStoreService(store=store, config=config)
    return _vector_store_service


class CreateCollectionRequest(BaseModel):
    name: str
    dimensions: int | None = None
    distance: str = "cosine"
    namespace: str = "default"
    metadata: dict[str, Any] = {}


class UpsertVectorRequest(BaseModel):
    id: str = ""
    vector: list[float]
    metadata: dict[str, Any] = {}
    namespace: str = "default"


class BatchUpsertRequest(BaseModel):
    records: list[UpsertVectorRequest]


class SearchVectorsRequest(BaseModel):
    vector: list[float]
    top_k: int = 10
    score_threshold: float | None = None
    collection: str = ""
    namespace: str = "default"
    filter: dict[str, Any] = {}
    include_metadata: bool = True
    include_vector: bool = False


class DeleteVectorsRequest(BaseModel):
    ids: list[str] = []
    filter: dict[str, Any] = {}
    collection: str = ""
    namespace: str = "default"


@app.post("/vector/collections", status_code=201)
async def create_vector_collection(body: CreateCollectionRequest) -> dict:
    svc = await _get_vector_store_service()
    try:
        coll = await svc.create_collection(
            name=body.name,
            dimensions=body.dimensions,
            distance=DistanceMetric(body.distance),
            namespace=body.namespace,
            metadata=body.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))
    return coll.to_dict()


@app.get("/vector/collections")
async def list_vector_collections() -> list[dict]:
    svc = await _get_vector_store_service()
    colls = await svc.list_collections()
    return [c.to_dict() for c in colls]


@app.delete("/vector/collections/{name}")
async def delete_vector_collection(name: str) -> dict:
    svc = await _get_vector_store_service()
    deleted = await svc.delete_collection(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="collection not found")
    return {"deleted": True}


@app.post("/vector/upsert")
async def upsert_vector(body: UpsertVectorRequest) -> dict:
    svc = await _get_vector_store_service()
    try:
        record = await svc.upsert(VectorRecord(
            id=body.id, vector=body.vector,
            metadata=body.metadata, namespace=body.namespace,
        ))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return record.to_dict()


@app.post("/vector/upsert/batch")
async def upsert_vectors_batch(body: BatchUpsertRequest) -> list[dict]:
    svc = await _get_vector_store_service()
    records = [
        VectorRecord(id=r.id, vector=r.vector, metadata=r.metadata, namespace=r.namespace)
        for r in body.records
    ]
    try:
        results = await svc.upsert_batch(records)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return [r.to_dict() for r in results]


@app.post("/vector/search")
async def search_vectors(body: SearchVectorsRequest) -> list[dict]:
    svc = await _get_vector_store_service()
    try:
        results = await svc.search(
            vector=body.vector,
            top_k=body.top_k,
            score_threshold=body.score_threshold,
            collection=body.collection,
            namespace=body.namespace,
            filter=body.filter or None,
            include_metadata=body.include_metadata,
            include_vector=body.include_vector,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return [r.to_dict(include_vector=body.include_vector) for r in results]


@app.delete("/vector/{id}")
async def delete_vector_by_id(id: str) -> dict:
    svc = await _get_vector_store_service()
    count = await svc.delete(ids=[id])
    return {"deleted": count > 0, "count": count}


@app.get("/vector/statistics")
async def vector_store_statistics() -> dict:
    svc = await _get_vector_store_service()
    stats = await svc.statistics()
    return stats.to_dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
