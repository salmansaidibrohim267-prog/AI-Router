"""Enhanced AI Router with adaptive routing, retry with jitter, and cost optimization."""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.classifier import TaskClassifier, classifier
from app.config import config_manager
from app.costs import token_accounting
from app.exceptions import (
    AllProvidersFailedError,
    NoHealthyProviderError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RouterError,
)
from app.logger import logger
from app.metrics import (
    record_request,
    record_success,
    record_failure,
    record_latency,
    record_tokens,
    record_cost,
    record_distribution_selection,
    record_fallback,
)
from app.models import (
    ChatChoice,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    Message,
    ProviderStatus,
    StreamChunk,
    TaskType,
)
from app.providers.base import BaseProvider
from app.providers.manager import provider_manager
from app.benchmark.live import live_benchmark
from app.capability_registry import capability_registry
from app.reputation import compute_reputation, compute_trend
from app.routing import (
    EWMA_ALPHA,
    OptimizationMode,
    RoutingContext,
    RoutingEngine,
    estimate_prompt_tokens,
    routing_engine,
)
from app.token_intelligence import token_intelligence
from app.traffic_distribution import traffic_distribution
from app.stats import stats
from app.storage import ProviderStats as StorageProviderStats
from app.event_bus import event_bus
from app.plugin.registry import PluginRegistry
from app.plugin.pipeline import MiddlewarePipeline
from app.plugin.watcher import PluginWatcher

HISTORY_SIZE = 100
ROLLING_WINDOW = 100
EWMA_ALPHA_VALUE = EWMA_ALPHA

RETRYABLE_CODES = {429, 500, 502, 503, 504}


@dataclass
class ProviderMetrics:
    name: str = ""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency: float = 0.0
    last_latency: float = 0.0
    consecutive_failures: int = 0
    consecutive_success: int = 0
    ewma_latency: float = 0.0
    total_cost: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    _start_time: float = field(default_factory=time.time)
    latency_history: deque[float] = field(default_factory=lambda: deque(maxlen=HISTORY_SIZE))
    request_history: deque[bool] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def failure_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    @property
    def avg_latency(self) -> float:
        if self.successful_requests == 0:
            return float('inf')
        return self.total_latency / self.successful_requests

    @property
    def avg_cost(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_cost / self.total_requests

    @property
    def rolling_success_rate(self) -> float:
        if not self.request_history:
            return 1.0
        return sum(self.request_history) / len(self.request_history)

    @property
    def rolling_failure_rate(self) -> float:
        return 1.0 - self.rolling_success_rate

    @property
    def rolling_throughput(self) -> float:
        if not self.request_history:
            return 0.0
        elapsed = time.time() - self._start_time
        if elapsed <= 0:
            return 0.0
        return len(self.request_history) / elapsed

    @property
    def p95_latency(self) -> float:
        if len(self.latency_history) < 2:
            return self.ewma_latency if self.ewma_latency > 0 else 0.0
        sorted_lats = sorted(self.latency_history)
        idx = max(0, min(len(sorted_lats) - 1, int(len(sorted_lats) * 0.95)))
        return sorted_lats[idx]

    @property
    def p99_latency(self) -> float:
        if len(self.latency_history) < 2:
            return self.ewma_latency if self.ewma_latency > 0 else 0.0
        sorted_lats = sorted(self.latency_history)
        idx = max(0, min(len(sorted_lats) - 1, int(len(sorted_lats) * 0.99)))
        return sorted_lats[idx]

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def record_success(self, latency_ms: float, cost_usd: float = 0.0, prompt_tokens: int = 0, completion_tokens: int = 0):
        self.total_requests += 1
        self.successful_requests += 1
        self.total_latency += latency_ms
        self.last_latency = latency_ms
        self.consecutive_failures = 0
        self.consecutive_success += 1
        self.last_success_time = time.time()
        self.total_cost += cost_usd
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        if self.ewma_latency == 0:
            self.ewma_latency = latency_ms
        else:
            self.ewma_latency = EWMA_ALPHA_VALUE * latency_ms + (1 - EWMA_ALPHA_VALUE) * self.ewma_latency
        self.latency_history.append(latency_ms)
        self.request_history.append(True)

    def to_storage(self) -> StorageProviderStats:
        return StorageProviderStats(
            name=self.name,
            total_requests=self.total_requests,
            successful_requests=self.successful_requests,
            failed_requests=self.failed_requests,
            total_latency=self.total_latency,
            ewma_latency=self.ewma_latency,
            total_cost=self.total_cost,
            total_prompt_tokens=self.total_prompt_tokens,
            total_completion_tokens=self.total_completion_tokens,
            uptime_seconds=self.uptime_seconds,
            first_seen=self._start_time,
            last_seen=time.time(),
            consecutive_failures=self.consecutive_failures,
            consecutive_success=self.consecutive_success,
        )

    @classmethod
    def from_storage(cls, s: StorageProviderStats) -> ProviderMetrics:
        m = cls(name=s.name)
        m.total_requests = s.total_requests
        m.successful_requests = s.successful_requests
        m.failed_requests = s.failed_requests
        m.total_latency = s.total_latency
        m.ewma_latency = s.ewma_latency
        m.total_cost = s.total_cost
        m.total_prompt_tokens = s.total_prompt_tokens
        m.total_completion_tokens = s.total_completion_tokens
        m._start_time = s.first_seen if s.first_seen > 0 else time.time()
        m.last_seen = s.last_seen
        m.consecutive_failures = s.consecutive_failures
        m.consecutive_success = s.consecutive_success
        return m

    def record_failure(self, latency_ms: float):
        self.total_requests += 1
        self.failed_requests += 1
        self.last_latency = latency_ms
        self.consecutive_failures += 1
        self.consecutive_success = 0
        self.last_failure_time = time.time()
        self.latency_history.append(latency_ms)
        self.request_history.append(False)


def _detect_required_capabilities(request: ChatRequest) -> set[str]:
    """Detect required capabilities from a chat request."""
    required: set[str] = set()

    if request.stream:
        required.add("streaming")

    for msg in request.messages:
        content = msg.content or ""
        # Vision: base64 image data or image URL patterns
        if "data:image/" in content or "![image]" in content:
            required.add("vision")
        # Tool calls in assistant messages
        if msg.tool_calls:
            required.add("tools")
            required.add("function_calling")

    return required


def _is_retryable(e: Exception) -> bool:
    """Check if an exception should be retried."""
    if isinstance(e, (ProviderRateLimitError, ProviderTimeoutError, ProviderUnavailableError)):
        return True
    if isinstance(e, ProviderError):
        return e.status_code in RETRYABLE_CODES
    if isinstance(e, (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, ConnectionResetError, TimeoutError)):
        return True
    return True  # generic exceptions are retryable (transient)


def _is_non_retryable(e: Exception) -> bool:
    """Check if an exception should never be retried."""
    if isinstance(e, ProviderAuthError):
        return True
    if isinstance(e, ProviderError) and e.status_code in {400, 401, 403, 404, 422}:
        return True
    return False


async def retry_with_backoff(coro_factory, max_retries=3, base_delay=1.0):
    """Retry with exponential backoff and jitter. Only retries retryable errors.

    Retries: 429, 500, 502, 503, 504, network timeouts, connection resets.
    Never retries: 400, 401, 403, 404, 422, auth errors.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except Exception as e:
            if _is_non_retryable(e):
                raise
            if not _is_retryable(e):
                raise
            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                await asyncio.sleep(delay)
    raise last_error


class AIRouter:
    def __init__(self, storage_backend=None):
        self.classifier = classifier
        self.provider_manager = provider_manager
        self.metrics: dict[str, ProviderMetrics] = defaultdict(ProviderMetrics)
        self.routing_engine = routing_engine
        self._storage = storage_backend
        self._initialized = False
        self._persist_task: asyncio.Task | None = None
        self.plugin_registry = PluginRegistry()
        self.pipeline = MiddlewarePipeline(self.plugin_registry)
        self._plugin_watcher = PluginWatcher(self.plugin_registry)

    async def initialize(self) -> None:
        if not self._initialized:
            await self.provider_manager.initialize()
            await self._load_persisted_metrics()
            self._start_persist_loop()
            self._initialized = True
            loaded = self.plugin_registry.discover_and_load()
            if loaded:
                await self.pipeline.initialize_plugins()
            self._plugin_watcher.start()

    async def _load_persisted_metrics(self) -> None:
        if not self._storage:
            return
        try:
            all_stats = await self._storage.load_all_providers()
            for s in all_stats:
                if s.name:
                    m = ProviderMetrics.from_storage(s)
                    self.metrics[s.name] = m
        except Exception:
            pass

    async def _persist_all_metrics(self) -> None:
        if not self._storage:
            return
        for name, m in self.metrics.items():
            try:
                stats = m.to_storage()
                await self._storage.save_provider(stats)
            except Exception:
                pass

    def _start_persist_loop(self) -> None:
        if not self._storage:
            return
        async def loop():
            while True:
                try:
                    await asyncio.sleep(30)
                    await self._persist_all_metrics()
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass
        self._persist_task = asyncio.create_task(loop())

    def _get_provider_configs(self, task: str) -> list[tuple[str, str]]:
        configs = []
        primary = config_manager.get_primary_provider(task)
        if primary:
            configs.append((primary.name, primary.model))
        for fallback in config_manager.get_fallback_providers(task):
            configs.append((fallback.name, fallback.model))
        return configs

    def _get_optimization_mode(self, request: ChatRequest) -> OptimizationMode:
        meta = request.metadata or {}
        mode_str = meta.get("optimization_mode", "")
        if mode_str:
            try:
                return OptimizationMode(mode_str.lower())
            except ValueError:
                pass
        return OptimizationMode.BALANCED

    def _build_routing_context(
        self,
        prompt: str,
        task: TaskType,
        user_preference: str | None,
        opt_mode: OptimizationMode,
        retry_attempt: int = 0,
        required_capabilities: set[str] | None = None,
        model: str = "",
        provider: str = "",
    ) -> RoutingContext:
        return RoutingContext(
            task=task.value,
            prompt_token_estimate=estimate_prompt_tokens(prompt, model=model, provider=provider),
            optimization_mode=opt_mode,
            user_preference=user_preference,
            retry_attempt=retry_attempt,
            required_capabilities=required_capabilities or set(),
        )

    async def _send_shadow(
        self,
        provider_name: str,
        model: str,
        request: ChatRequest,
        request_id: str,
        task: TaskType,
    ) -> None:
        """Fire-and-forget a shadow request for comparison."""
        try:
            provider = self.provider_manager.get(provider_name)
            if not provider:
                return
            shadow_req = request.model_copy()
            shadow_req.model = model
            shadow_req.stream = False
            start = time.perf_counter()
            await asyncio.wait_for(provider.chat(shadow_req), timeout=30.0)
            latency = (time.perf_counter() - start) * 1000
            from app.metrics import shadow_traffic_total
            shadow_traffic_total.labels(provider=provider_name, model=model).inc()
            logger.log_request(
                request_id=f"{request_id}-shadow",
                provider=provider_name,
                model=model,
                task=task.value,
                latency_ms=latency,
                success=True,
                metadata={"shadow_of": request_id},
            )
        except Exception:
            pass

    def _rank_providers(
        self,
        task: str,
        candidates: list[tuple[str, str]],
        user_preference: str | None = None,
        retry_attempt: int = 0,
        required_capabilities: set[str] | None = None,
        prompt: str = "",
        return_scores: bool = False,
    ) -> list[tuple[str, str]] | list[tuple[float, str, str]]:
        """Rank providers using the adaptive routing engine."""
        model_hint = candidates[0][1] if candidates else ""
        provider_hint = candidates[0][0] if candidates else ""
        ctx = self._build_routing_context(
            prompt if prompt else task,
            TaskType.CHAT if task else TaskType.UNKNOWN,
            user_preference,
            OptimizationMode.BALANCED,
            retry_attempt,
            required_capabilities=required_capabilities,
            model=model_hint,
            provider=provider_hint,
        )
        return self.routing_engine.rank_providers(candidates, self.metrics, self.provider_manager, ctx, return_scores=return_scores)

    def _is_provider_available(self, provider: str) -> bool:
        if provider not in self.provider_manager.get_provider_names():
            return False
        if self.provider_manager.is_disabled(provider):
            return False
        h = self.provider_manager.get_health_status(provider)
        if isinstance(h, dict):
            h = h.get(provider)
        if hasattr(h, 'status') and h.status == ProviderStatus.UNHEALTHY:
            return False
        return True

    async def _try_provider(self, provider_name: str, model: str, request: ChatRequest, request_id: str, task: TaskType, retry_attempt: int = 0, context: dict | None = None) -> ChatResponse | None:
        provider = self.provider_manager.get(provider_name)
        if not provider:
            return None

        metrics = self.metrics[provider_name]
        start = time.perf_counter()

        await event_bus.emit("provider.selected", provider=provider_name, model=model, request_id=request_id)

        hook_ctx = context or {}
        hook_result = await self.pipeline.execute_before_provider(request, provider_name, model, hook_ctx)
        if hook_result.should_cancel:
            return None
        if hook_result.modified_request is not None:
            request = hook_result.modified_request

        try:
            request.model = model
            record_request(provider_name, model, task.value)

            async def do_chat():
                return await provider.chat(request)

            response = await retry_with_backoff(do_chat, max_retries=3, base_delay=1.0)

            await self.pipeline.execute_after_provider(request, response, provider_name, model, hook_ctx)

            latency = (time.perf_counter() - start) * 1000

            pt = response.usage.prompt_tokens if response.usage else 0
            ct = response.usage.completion_tokens if response.usage else 0
            tt = response.usage.total_tokens if response.usage else 0
            cache_t = response.usage.cache_tokens if response.usage else 0
            reason_t = response.usage.reasoning_tokens if response.usage else 0
            cost = token_accounting.estimate_cost(provider_name, model, pt, ct, cache_t)

            metrics.record_success(latency, cost_usd=cost, prompt_tokens=pt, completion_tokens=ct)

            record_success(provider_name, model)
            record_latency(provider_name, model, latency)

            token_accounting.record(provider_name, model, pt, ct, cache_t, reason_t)

            record_tokens(provider_name, model, pt, ct)
            record_cost(provider_name, model, cost)
            token_intelligence.record(model, pt, ct, cache_t, reason_t)

            logger.log_request(request_id=request_id, provider=provider_name, model=model, task=task.value, latency_ms=latency, success=True, prompt_tokens=pt, completion_tokens=ct, total_tokens=tt)
            stats.record(provider=provider_name, model=model, latency_ms=latency, success=True, task=task, prompt_tokens=pt, completion_tokens=ct, total_tokens=tt)

            live_benchmark.record(
                provider=provider_name,
                latency_ms=latency,
                tokens=tt,
                success=True,
                timeout=False,
                model=model,
            )

            if self._storage:
                try:
                    await self._storage.save_provider(metrics.to_storage())
                except Exception:
                    pass

            return response

        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            metrics.record_failure(latency)
            record_failure(provider_name, model, type(e).__name__)
            record_latency(provider_name, model, latency)
            logger.log_request(request_id=request_id, provider=provider_name, model=model, task=task.value, latency_ms=latency, success=False, error=str(e))
            stats.record(provider=provider_name, model=model, latency_ms=latency, success=False, task=task)

            is_timeout = isinstance(e, (asyncio.TimeoutError, ProviderTimeoutError))
            live_benchmark.record(
                provider=provider_name,
                latency_ms=latency,
                tokens=0,
                success=False,
                timeout=is_timeout,
                model=model,
            )

            await event_bus.emit("provider.failed", provider=provider_name, model=model, request_id=request_id, error=str(e))
            await self.pipeline.execute_on_error(request, e, {"request_id": request_id, "provider": provider_name, "model": model})
            return None

    async def chat(self, request: ChatRequest) -> ChatResponse:
        await self.initialize()
        request_id = str(uuid.uuid4())
        if not request.metadata:
            request.metadata = {}
        request.metadata["request_id"] = request_id

        prompt = request.messages[-1].content if request.messages else ""
        task = self.classifier.classify(prompt)

        await event_bus.emit("request.started", request_id=request_id, task=task.value, model=request.model)

        opt_mode = self._get_optimization_mode(request)
        self.routing_engine.set_mode(opt_mode)

        required_caps = _detect_required_capabilities(request)
        metadata_caps = request.metadata.get("required_capabilities", []) if request.metadata else []
        if metadata_caps:
            required_caps.update(metadata_caps)

        context = {"request_id": request_id, "task": task.value, "provider": "", "model": ""}
        hook_result = await self.pipeline.execute_before_request(request, context)
        if hook_result.should_cancel:
            raise RouterError(f"Request cancelled by plugin: {hook_result.cancel_reason}")
        if hook_result.modified_request is not None:
            request = hook_result.modified_request

        route_result = await self.pipeline.execute_before_route(request, context)
        if route_result.should_cancel:
            raise RouterError(f"Request cancelled by plugin: {route_result.cancel_reason}")
        if route_result.modified_request is not None:
            request = route_result.modified_request

        candidates = self._get_provider_configs(task)
        available = [(p, m) for p, m in candidates if self._is_provider_available(p)]
        if not available:
            available = candidates
        if not available:
            raise NoHealthyProviderError(task=task)

        user_pref = request.metadata.get("preferred_provider") if request.metadata else None
        full_prompt = " ".join(m.content or "" for m in request.messages)
        ranked_raw = self._rank_providers(
            task, available, user_preference=user_pref,
            required_capabilities=required_caps, prompt=full_prompt, return_scores=True,
        )
        if ranked_raw and isinstance(ranked_raw[0], tuple) and len(ranked_raw[0]) == 3:
            scored_ranked = ranked_raw
            ranked = [(p, m) for _, p, m in scored_ranked]
        else:
            ranked = ranked_raw
            scored_ranked = []

        errors = []
        selected = traffic_distribution.select(scored_ranked if scored_ranked else ranked)

        shadow_task = None
        if selected and selected.shadow_provider:
            shadow_task = asyncio.create_task(
                self._send_shadow(
                    selected.shadow_provider, selected.shadow_model,
                    request, request_id, task,
                )
            )

        if selected:
            record_distribution_selection(
                selected.provider, selected.model,
                is_canary=selected.ab_test_name != "" or any(
                    c.provider == selected.provider and c.model == selected.model
                    for c in [traffic_distribution.config.canary] if traffic_distribution.config.canary
                ),
            )

        providers_to_try = [(selected.provider, selected.model)] if selected else []
        providers_to_try += [(p, m) for p, m in ranked if (p, m) not in providers_to_try]

        after_route_result = await self.pipeline.execute_after_route(request, context, providers_to_try)
        if after_route_result.should_cancel:
            raise RouterError(f"Request cancelled by plugin: {after_route_result.cancel_reason}")

        for attempt, (provider_name, model) in enumerate(providers_to_try):
            response = await self._try_provider(provider_name, model, request, request_id, task, retry_attempt=attempt, context=context)
            if response:
                response.metadata = {"request_id": request_id, "task": task.value}
                before_resp_result = await self.pipeline.execute_before_response(request, response, context)
                if before_resp_result.should_cancel:
                    raise RouterError(f"Request cancelled by plugin: {before_resp_result.cancel_reason}")
                if before_resp_result.modified_response is not None:
                    response = before_resp_result.modified_response
                await self.pipeline.execute_after_response(request, response, context)
                await event_bus.emit("request.finished", request_id=request_id, provider=provider_name, model=model, success=True)
                if before_resp_result.metadata:
                    if not response.metadata:
                        response.metadata = {}
                    response.metadata.update(before_resp_result.metadata)
                return response
            record_fallback(provider_name, model, from_provider="")
            await event_bus.emit("fallback.triggered", from_provider=provider_name, to_provider="", task=task.value)
            errors.append(ProviderError(f"Provider {provider_name} failed", provider=provider_name, model=model))

        await event_bus.emit("request.finished", request_id=request_id, success=False, error=str(errors[-1]) if errors else "All providers failed")
        raise AllProvidersFailedError(task=task, errors=errors)

    async def stream_chat(self, request: ChatRequest):
        await self.initialize()
        request_id = str(uuid.uuid4())
        if not request.metadata:
            request.metadata = {}
        request.metadata["request_id"] = request_id

        prompt = request.messages[-1].content if request.messages else ""
        task = self.classifier.classify(prompt)

        await event_bus.emit("request.started", request_id=request_id, task=task.value, model=request.model)

        opt_mode = self._get_optimization_mode(request)
        self.routing_engine.set_mode(opt_mode)

        required_caps = _detect_required_capabilities(request)
        metadata_caps = request.metadata.get("required_capabilities", []) if request.metadata else []
        if metadata_caps:
            required_caps.update(metadata_caps)

        context = {"request_id": request_id, "task": task.value, "provider": "", "model": ""}
        hook_result = await self.pipeline.execute_before_request(request, context)
        if hook_result.should_cancel:
            raise RouterError(f"Request cancelled by plugin: {hook_result.cancel_reason}")
        if hook_result.modified_request is not None:
            request = hook_result.modified_request

        route_result = await self.pipeline.execute_before_route(request, context)
        if route_result.should_cancel:
            raise RouterError(f"Request cancelled by plugin: {route_result.cancel_reason}")
        if route_result.modified_request is not None:
            request = route_result.modified_request

        candidates = self._get_provider_configs(task)
        available = [(p, m) for p, m in candidates if self._is_provider_available(p)]
        if not available:
            available = candidates
        if not available:
            raise NoHealthyProviderError(task=task)

        user_pref = request.metadata.get("preferred_provider") if request.metadata else None
        full_prompt = " ".join(m.content or "" for m in request.messages)
        ranked_raw = self._rank_providers(
            task, available, user_preference=user_pref,
            required_capabilities=required_caps, prompt=full_prompt, return_scores=True,
        )
        if ranked_raw and isinstance(ranked_raw[0], tuple) and len(ranked_raw[0]) == 3:
            scored_ranked = ranked_raw
            ranked = [(p, m) for _, p, m in scored_ranked]
        else:
            ranked = ranked_raw
            scored_ranked = []

        errors = []
        selected = traffic_distribution.select(scored_ranked if scored_ranked else ranked)

        shadow_task = None
        if selected and selected.shadow_provider:
            shadow_task = asyncio.create_task(
                self._send_shadow(
                    selected.shadow_provider, selected.shadow_model,
                    request, request_id, task,
                )
            )

        if selected:
            record_distribution_selection(
                selected.provider, selected.model,
                is_canary=selected.ab_test_name != "" or any(
                    c.provider == selected.provider and c.model == selected.model
                    for c in [traffic_distribution.config.canary] if traffic_distribution.config.canary
                ),
            )

        providers_to_try = [(selected.provider, selected.model)] if selected else []
        providers_to_try += [(p, m) for p, m in ranked if (p, m) not in providers_to_try]

        after_route_result = await self.pipeline.execute_after_route(request, context, providers_to_try)
        if after_route_result.should_cancel:
            raise RouterError(f"Request cancelled by plugin: {after_route_result.cancel_reason}")

        for attempt, (provider_name, model) in enumerate(providers_to_try):
            provider = self.provider_manager.get(provider_name)
            if not provider:
                errors.append(ProviderError(f"Provider {provider_name} not found", provider=provider_name))
                continue

            metrics = self.metrics[provider_name]
            start = time.perf_counter()
            record_request(provider_name, model, task.value)

            try:
                request.model = model
                final_usage = None
                first_token_latency = 0.0
                first_chunk_received = False

                hook_ctx_stream = dict(context)
                bp_result = await self.pipeline.execute_before_provider(request, provider_name, model, hook_ctx_stream)
                if bp_result.should_cancel:
                    return
                if bp_result.modified_request is not None:
                    request = bp_result.modified_request

                async for chunk in provider.stream_chat(request):
                    if not first_chunk_received:
                        first_token_latency = (time.perf_counter() - start) * 1000
                        first_chunk_received = True
                    if chunk.usage:
                        final_usage = chunk.usage
                    chunk.metadata = {"request_id": request_id, "task": task.value}
                    yield chunk

                latency = (time.perf_counter() - start) * 1000

                pt = final_usage.prompt_tokens if final_usage else 0
                ct = final_usage.completion_tokens if final_usage else 0
                tt = final_usage.total_tokens if final_usage else 0
                cache_t = final_usage.cache_tokens if final_usage else 0
                reason_t = final_usage.reasoning_tokens if final_usage else 0
                cost = token_accounting.estimate_cost(provider_name, model, pt, ct, cache_t)

                metrics.record_success(latency, cost_usd=cost, prompt_tokens=pt, completion_tokens=ct)

                record_success(provider_name, model)
                record_latency(provider_name, model, latency)

                token_accounting.record(provider_name, model, pt, ct, cache_t, reason_t)

                token_intelligence.record(model, pt, ct, cache_t, reason_t)

                record_tokens(provider_name, model, pt, ct)
                record_cost(provider_name, model, cost)

                logger.log_request(request_id=request_id, provider=provider_name, model=model, task=task.value, latency_ms=latency, success=True, prompt_tokens=pt, completion_tokens=ct, total_tokens=tt)
                stats.record(provider=provider_name, model=model, latency_ms=latency, success=True, task=task, prompt_tokens=pt, completion_tokens=ct, total_tokens=tt)

                live_benchmark.record(
                    provider=provider_name,
                    latency_ms=latency,
                    first_token_latency_ms=first_token_latency,
                    tokens=tt,
                    success=True,
                    model=model,
                )

                # Build a response-like object for hooks
                stream_response = {
                    "provider": provider_name,
                    "model": model,
                    "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt},
                }
                ap_result = await self.pipeline.execute_after_provider(request, stream_response, provider_name, model, hook_ctx_stream)
                br_result = await self.pipeline.execute_before_response(request, stream_response, context)
                await self.pipeline.execute_after_response(request, stream_response, context)

                await event_bus.emit("request.finished", request_id=request_id, provider=provider_name, model=model, success=True)

                if self._storage:
                    try:
                        await self._storage.save_provider(metrics.to_storage())
                    except Exception:
                        pass
                return

            except asyncio.CancelledError:
                latency = (time.perf_counter() - start) * 1000
                metrics.record_failure(latency)
                record_failure(provider_name, model, "Cancelled")
                record_latency(provider_name, model, latency)
                logger.log_request(request_id=request_id, provider=provider_name, model=model, task=task.value, latency_ms=latency, success=False, error="Stream cancelled")
                stats.record(provider=provider_name, model=model, latency_ms=latency, success=False, task=task)
                live_benchmark.record(provider=provider_name, latency_ms=latency, tokens=0, success=False, timeout=False, model=model)
                raise

            except Exception as e:
                latency = (time.perf_counter() - start) * 1000
                metrics.record_failure(latency)
                record_failure(provider_name, model, type(e).__name__)
                record_latency(provider_name, model, latency)
                logger.log_request(request_id=request_id, provider=provider_name, model=model, task=task.value, latency_ms=latency, success=False, error=str(e))
                stats.record(provider=provider_name, model=model, latency_ms=latency, success=False, task=task)
                is_timeout = isinstance(e, (asyncio.TimeoutError, ProviderTimeoutError))
                live_benchmark.record(provider=provider_name, latency_ms=latency, tokens=0, success=False, timeout=is_timeout, model=model)
                record_fallback(provider_name, model, from_provider="")
                await event_bus.emit("fallback.triggered", from_provider=provider_name, to_provider="", task=task.value)
                errors.append(ProviderError(f"Provider {provider_name} stream failed: {e}", provider=provider_name, model=model))
                continue

        await event_bus.emit("request.finished", request_id=request_id, success=False, error=str(errors[-1]) if errors else "All providers failed")
        raise AllProvidersFailedError(task=task, errors=errors)

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        await self.initialize()
        candidates = self._get_provider_configs("chat")
        for provider_name, model in candidates:
            provider = self.provider_manager.get(provider_name)
            if not provider:
                continue
            try:
                request.model = model
                return await provider.embeddings(request)
            except Exception:
                continue
        raise RouterError("No provider available for embeddings")

    def get_provider_stats(self) -> dict[str, Any]:
        result = {}
        for name, m in self.metrics.items():
            trend = compute_trend(m.request_history)
            reputation = compute_reputation(
                success_rate=m.success_rate,
                ewma_latency=m.ewma_latency,
                avg_cost=m.avg_cost,
                uptime_seconds=m.uptime_seconds,
                consecutive_success=m.consecutive_success,
                consecutive_failure=m.consecutive_failures,
            )
            result[name] = {
                "total_requests": m.total_requests,
                "successful": m.successful_requests,
                "failed": m.failed_requests,
                "success_rate": m.success_rate,
                "failure_rate": m.failure_rate,
                "avg_latency_ms": m.avg_latency,
                "ewma_latency_ms": round(m.ewma_latency, 2),
                "p95_latency_ms": round(m.p95_latency, 2),
                "p99_latency_ms": round(m.p99_latency, 2),
                "rolling_success_rate": round(m.rolling_success_rate, 4),
                "rolling_throughput": round(m.rolling_throughput, 2),
                "avg_cost": round(m.avg_cost, 6),
                "consecutive_success": m.consecutive_success,
                "consecutive_failures": m.consecutive_failures,
                "reputation": reputation,
                "trend": trend.trend.value,
                "uptime_seconds": m.uptime_seconds,
            }
        return result

    def get_health_summary(self) -> dict[str, Any]:
        return self.provider_manager.get_status_summary()

    async def close(self) -> None:
        self._plugin_watcher.stop()
        await self.pipeline.shutdown_plugins()
        self.plugin_registry.shutdown_all()
        await self.provider_manager.close()


router = AIRouter()
