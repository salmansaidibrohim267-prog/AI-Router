"""Provider manager for dynamic provider loading and health monitoring."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config import config_manager
from app.exceptions import ProviderError, ProviderUnavailableError
from app.models import HealthCheckResponse, ModelInfo, ProviderStatus
from app.metrics import set_provider_health, set_provider_latency, set_circuit_breaker_state
from app.secrets import get_secret
from app.providers.base import BaseProvider
from app.providers.openrouter import OpenRouterProvider
from app.providers.ollama import OllamaProvider
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.google import GoogleProvider
from app.providers.mistral import MistralProvider
from app.providers.groq import GroqProvider
from app.providers.discovery import discover_custom_providers

BUILTIN_PROVIDERS = {
    "openrouter": OpenRouterProvider,
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "mistral": MistralProvider,
    "groq": GroqProvider,
}

def _get_provider_registry() -> dict[str, type[BaseProvider]]:
    registry = dict(BUILTIN_PROVIDERS)
    try:
        custom = discover_custom_providers()
        registry.update(custom)
    except Exception:
        pass
    return registry

logger = logging.getLogger(__name__)

PROVIDER_ALIASES = {
    "gemini": "google",
}


class CircuitBreaker:
    """Circuit breaker for provider failure handling."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._state = "closed"  # closed, open, half-open
        self._last_failure_time = 0.0
        self._half_open_successes = 0

    @property
    def is_open(self) -> bool:
        if self._state == "open":
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = "half-open"
                self._half_open_successes = 0
                return False
            return True
        return False

    def record_success(self):
        if self._state == "half-open":
            self._half_open_successes += 1
            if self._half_open_successes >= 3:
                self._state = "closed"
                self._failure_count = 0
        elif self._state == "closed":
            self._failure_count = 0

    def record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = "open"

    def reset(self):
        self._state = "closed"
        self._failure_count = 0
        self._half_open_successes = 0

    @property
    def state(self) -> str:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count


class ProviderManager:
    """Manages AI providers with health checks, circuit breakers, and dynamic loading."""

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}
        self._health_status: dict[str, HealthCheckResponse] = {}
        self._health_check_task: asyncio.Task | None = None
        self._disabled: set[str] = set()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
        self._aliases = PROVIDER_ALIASES
        self._health_check_interval: int = 30

    async def initialize(self) -> None:
        """Initialize providers from configuration."""
        await self.reload()
        self._start_health_check_loop()

    async def reload(self) -> None:
        """Reload providers from configuration."""
        async with self._lock:
            for provider in self._providers.values():
                await provider.close()

            self._providers.clear()
            self._health_status.clear()

            provider_configs = config_manager.get_all_provider_configs()

            for provider_config in provider_configs:
                if not provider_config.enabled:
                    logger.info(f"Provider {provider_config.name} is disabled, skipping")
                    continue
                await self._load_provider(provider_config)

            logger.info(f"Initialized {len(self._providers)} providers: {list(self._providers.keys())}")

    async def reload_from_yaml(self) -> None:
        """Reload providers directly from providers.yaml."""
        import yaml
        from pathlib import Path
        from app.config import CONFIG_DIR

        providers_file = CONFIG_DIR / "providers.yaml"
        if not providers_file.exists():
            return

        async with self._lock:
            for provider in self._providers.values():
                await provider.close()

            self._providers.clear()
            self._health_status.clear()

            with open(providers_file) as f:
                data = yaml.safe_load(f) or {}

            for pcfg in data.get("providers", []):
                if not pcfg.get("enabled", True):
                    continue
                provider_class = _get_provider_registry().get(pcfg["name"].lower())
                if not provider_class:
                    logger.warning(f"Unknown provider: {pcfg['name']}")
                    continue
                api_key_env = pcfg.get("api_key_env", "")
                api_key = get_secret(api_key_env) if api_key_env else None
                try:
                    provider = provider_class(
                        api_key=api_key,
                        base_url=pcfg.get("base_url"),
                        timeout=pcfg.get("timeout", 60.0),
                        max_retries=pcfg.get("max_retries", 3),
                    )
                    self._providers[pcfg["name"]] = provider
                except Exception as e:
                    logger.error(f"Failed to load provider {pcfg['name']}: {e}")

            logger.info(f"Reloaded {len(self._providers)} providers from YAML")

    async def _load_provider(self, provider_config) -> None:
        """Load a single provider from config."""
        provider_class = _get_provider_registry().get(provider_config.name.lower())
        if not provider_class:
            logger.warning(f"Unknown provider: {provider_config.name}")
            return

        try:
            api_key = None
            if provider_config.api_key_env:
                api_key = get_secret(provider_config.api_key_env)

            provider = provider_class(
                api_key=api_key,
                base_url=provider_config.base_url,
                timeout=provider_config.timeout,
                max_retries=provider_config.max_retries,
            )
            self._providers[provider_config.name] = provider
            logger.info(f"Loaded provider: {provider_config.name}")

            try:
                health = await provider.health_check()
                self._health_status[provider_config.name] = health
                set_provider_health(provider_config.name, health.status == ProviderStatus.HEALTHY)
                if health.latency_ms is not None:
                    set_provider_latency(provider_config.name, health.latency_ms)
            except Exception as e:
                logger.warning(f"Initial health check failed for {provider_config.name}: {e}")
                self._health_status[provider_config.name] = HealthCheckResponse(
                    status=ProviderStatus.UNKNOWN,
                    provider=provider_config.name,
                    error=str(e),
                )
                set_provider_health(provider_config.name, False)
        except Exception as e:
            logger.error(f"Failed to load provider {provider_config.name}: {e}")

    def resolve_name(self, name: str) -> str:
        return self._aliases.get(name.lower(), name.lower())

    def get(self, name: str) -> BaseProvider | None:
        resolved = self.resolve_name(name)
        return self._providers.get(resolved)

    def get_all(self) -> dict[str, BaseProvider]:
        return self._providers.copy()

    def get_healthy(self) -> list[BaseProvider]:
        healthy = []
        for name, provider in self._providers.items():
            status = self._health_status.get(name)
            if status and status.status == ProviderStatus.HEALTHY and not self.is_circuit_open(name):
                healthy.append(provider)
        return healthy

    def get_provider_names(self) -> list[str]:
        return list(self._providers.keys())

    def get_health_status(self, name: str | None = None) -> dict[str, HealthCheckResponse] | HealthCheckResponse | None:
        if name:
            return self._health_status.get(name.lower())
        return self._health_status.copy()

    async def check_health(self, name: str | None = None, max_concurrency: int = 5, timeout: float = 10.0) -> dict[str, HealthCheckResponse]:
        """Run health checks in parallel using asyncio.gather with concurrency limiting.

        Args:
            name: Specific provider to check, or None for all.
            max_concurrency: Maximum parallel health checks.
            timeout: Timeout per health check in seconds.
        """
        results = {}
        if name:
            resolved = self.resolve_name(name)
            provider = self._providers.get(resolved)
            providers = [provider] if provider else []
        else:
            providers = list(self._providers.values())

        targets = []
        for provider in providers:
            if not provider:
                continue
            cb = self._circuit_breakers.get(provider.name)
            if cb and cb.is_open:
                continue
            targets.append(provider)

        semaphore = asyncio.Semaphore(max_concurrency)

        async def check_one(provider: BaseProvider) -> tuple[str, HealthCheckResponse]:
            async with semaphore:
                start = time.perf_counter()
                try:
                    health = await asyncio.wait_for(provider.health_check(), timeout=timeout)
                    health.latency_ms = (time.perf_counter() - start) * 1000
                    return provider.name, health
                except Exception as e:
                    latency = (time.perf_counter() - start) * 1000
                    health = HealthCheckResponse(
                        status=ProviderStatus.UNHEALTHY,
                        provider=provider.name,
                        latency_ms=latency,
                        error=str(e),
                    )
                    return provider.name, health

        if targets:
            gathered = await asyncio.gather(*[check_one(p) for p in targets], return_exceptions=False)
            for provider_name, health in gathered:
                self._health_status[provider_name] = health
                results[provider_name] = health
                is_healthy = health.status == ProviderStatus.HEALTHY
                set_provider_health(provider_name, is_healthy)
                if health.latency_ms is not None:
                    set_provider_latency(provider_name, health.latency_ms)
                if is_healthy:
                    if provider_name in self._circuit_breakers:
                        self._circuit_breakers[provider_name].record_success()
                        set_circuit_breaker_state(provider_name, self._circuit_breakers[provider_name].state)
                    self._disabled.discard(provider_name)
                else:
                    self._track_failure(provider_name)

        return results

    def _track_failure(self, name: str) -> None:
        """Track failure with circuit breaker."""
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60.0,
            )
        self._circuit_breakers[name].record_failure()
        set_circuit_breaker_state(name, self._circuit_breakers[name].state)
        if self._circuit_breakers[name].is_open:
            self._disabled.add(name)
            logger.warning(f"Provider {name} disabled by circuit breaker after {self._circuit_breakers[name].failure_count} failures")

    def is_circuit_open(self, name: str) -> bool:
        cb = self._circuit_breakers.get(name)
        return cb is not None and cb.is_open

    def get_circuit_state(self, name: str) -> str:
        cb = self._circuit_breakers.get(name)
        return cb.state if cb else "closed"

    def _start_health_check_loop(self) -> None:
        """Start background health check loop with fixed 30s interval."""
        if self._health_check_task:
            self._health_check_task.cancel()

        async def loop():
            while True:
                try:
                    await asyncio.sleep(self._health_check_interval)
                    await self.check_health()
                    await self._recovery_check()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Health check loop error: {e}")

        self._health_check_task = asyncio.create_task(loop())

    async def _recovery_check(self) -> None:
        """Check disabled providers for recovery."""
        for name in list(self._disabled):
            provider = self._providers.get(name)
            if not provider:
                self._disabled.discard(name)
                continue
            try:
                health = await provider.health_check()
                if health.status == ProviderStatus.HEALTHY:
                    self._disabled.discard(name)
                    self._health_status[name] = health
                    set_provider_health(name, True)
                    if health.latency_ms is not None:
                        set_provider_latency(name, health.latency_ms)
                    cb = self._circuit_breakers.get(name)
                    if cb:
                        cb.reset()
                        set_circuit_breaker_state(name, "closed")
                    logger.info(f"Provider {name} recovered and re-enabled")
            except Exception:
                pass

    def is_disabled(self, name: str) -> bool:
        resolved = self.resolve_name(name)
        return resolved in self._disabled

    def get_disabled_providers(self) -> list[str]:
        return list(self._disabled)

    def enable_provider(self, name: str) -> None:
        resolved = self.resolve_name(name)
        self._disabled.discard(resolved)
        cb = self._circuit_breakers.get(resolved)
        if cb:
            cb.reset()

    async def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        """List models from provider(s)."""
        if provider:
            p = self.get(provider)
            if p:
                return await p.list_models()
            return []

        all_models = []
        for p in self._providers.values():
            try:
                models = await p.list_models()
                all_models.extend(models)
            except Exception as e:
                logger.warning(f"Failed to list models for {p.name}: {e}")
        return all_models

    def get_provider_latency(self, name: str) -> float | None:
        """Get latest latency for a provider from health status."""
        health = self._health_status.get(self.resolve_name(name))
        return health.latency_ms if health else None

    def get_failure_rate(self, name: str) -> float:
        """Get failure rate for a provider based on circuit breaker state."""
        cb = self._circuit_breakers.get(self.resolve_name(name))
        if not cb:
            return 0.0
        return cb.failure_count / 5.0 if cb.failure_count > 0 else 0.0

    async def close(self) -> None:
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        for provider in self._providers.values():
            await provider.close()

        self._providers.clear()
        self._health_status.clear()
        self._disabled.clear()
        self._circuit_breakers.clear()

    def is_healthy(self, name: str) -> bool:
        resolved = self.resolve_name(name)
        health = self._health_status.get(resolved)
        return health is not None and health.status == ProviderStatus.HEALTHY and not self.is_circuit_open(resolved)

    def get_status_summary(self) -> dict[str, Any]:
        return {
            name: {
                "status": health.status.value,
                "latency_ms": health.latency_ms,
                "error": health.error,
                "checked_at": health.checked_at.isoformat() if health.checked_at else None,
                "circuit_state": self.get_circuit_state(name),
                "disabled": name in self._disabled,
            }
            for name, health in self._health_status.items()
        }


provider_manager = ProviderManager()
