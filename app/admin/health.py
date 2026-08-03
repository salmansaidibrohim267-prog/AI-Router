from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from .exceptions import ComponentUnavailableError, HealthCheckFailedError
from .models import ComponentHealth, ComponentName, HealthStatus


class HealthCheck(ABC):
    """Strategy: probes one platform component and reports its health."""

    name: str = ""
    component: str = ""

    @abstractmethod
    def check(self) -> ComponentHealth:
        raise NotImplementedError

    def check_async(self) -> ComponentHealth:
        return self.check()


class _ProbeHealthCheck(HealthCheck):
    """Base for checks backed by a probe callable returning truthy when healthy."""

    component: str = ""

    def __init__(self, probe: Any = None, name: str = "", message: str = "") -> None:
        self._probe = probe
        self._name = name
        self._message = message
        self.name = name or f"{self.component}_check"
        self._checked: bool = False
        self._healthy: bool = True
        self._latency: float = 0.0

    def check(self) -> ComponentHealth:
        started = time.time()
        try:
            healthy = self._probe() if self._probe is not None else self._default_probe()
            status = HealthStatus.OK if healthy else HealthStatus.DOWN
        except Exception as exc:
            status = HealthStatus.DOWN
            self._message = str(exc)
        self._latency = (time.time() - started) * 1000.0
        return ComponentHealth(
            name=self.name,
            status=status,
            latency_ms=self._latency,
            message=self._message,
        )

    def _default_probe(self) -> bool:
        return True


class CallableHealthCheck(_ProbeHealthCheck):
    component = "custom"


class GatewayHealthCheck(_ProbeHealthCheck):
    component = ComponentName.GATEWAY.value

    def _default_probe(self) -> bool:
        return True


class BillingHealthCheck(_ProbeHealthCheck):
    component = ComponentName.BILLING.value


class TenancyHealthCheck(_ProbeHealthCheck):
    component = ComponentName.TENANCY.value


class OrganizationsHealthCheck(_ProbeHealthCheck):
    component = ComponentName.ORGANIZATIONS.value


class AuthHealthCheck(_ProbeHealthCheck):
    component = ComponentName.AUTH.value


class ModelsHealthCheck(_ProbeHealthCheck):
    component = ComponentName.MODELS.value


class KnowledgeHealthCheck(_ProbeHealthCheck):
    component = ComponentName.KNOWLEDGE.value


class MemoryHealthCheck(_ProbeHealthCheck):
    component = ComponentName.MEMORY.value


class MCPHealthCheck(_ProbeHealthCheck):
    component = ComponentName.MCP.value


class PluginsHealthCheck(_ProbeHealthCheck):
    component = ComponentName.PLUGINS.value


class StorageHealthCheck(_ProbeHealthCheck):
    component = ComponentName.STORAGE.value


class RateLimiterHealthCheck(_ProbeHealthCheck):
    component = ComponentName.RATE_LIMITER.value


class HealthCheckRegistry:
    """Registry of component health checks (Repository + Strategy)."""

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self._checks: dict[str, HealthCheck] = {}
        self._timeout = timeout_seconds
        self._lock = threading.Lock()

    @property
    def timeout_seconds(self) -> float:
        return self._timeout

    def register(self, check: HealthCheck) -> None:
        with self._lock:
            self._checks[check.name] = check

    def unregister(self, name: str) -> bool:
        with self._lock:
            if name not in self._checks:
                return False
            del self._checks[name]
        return True

    def names(self) -> list[str]:
        with self._lock:
            return list(self._checks.keys())

    def get(self, name: str) -> HealthCheck:
        with self._lock:
            check = self._checks.get(name)
        if check is None:
            raise HealthCheckFailedError(name, "no check registered")
        return check

    def run(self, component: str = "") -> list[ComponentHealth]:
        results: list[ComponentHealth] = []
        for _, check in list(self._checks.items()):
            if component and check.component != component:
                continue
            results.append(check.check())
        return results

    def run_component(self, component: str) -> ComponentHealth:
        matches = [check for check in self._checks.values() if check.component == component]
        if not matches:
            raise ComponentUnavailableError(component)
        results = [check.check() for check in matches]
        statuses = [result.status for result in results]
        worst = (
            HealthStatus.DOWN
            if HealthStatus.DOWN in statuses
            else (HealthStatus.DEGRADED if HealthStatus.DEGRADED in statuses else HealthStatus.OK)
        )  # noqa: E501
        failed = [result for result in results if result.status == worst]
        return ComponentHealth(
            name=component,
            status=worst,
            latency_ms=max(result.latency_ms for result in results),
            message=failed[0].message if failed else "",
        )


def create_default_registry(
    probes: dict[str, Any] | None = None,
    timeout_seconds: float = 5.0,
) -> HealthCheckRegistry:
    probes = probes or {}
    registry = HealthCheckRegistry(timeout_seconds=timeout_seconds)
    for check_cls in (
        GatewayHealthCheck,
        BillingHealthCheck,
        TenancyHealthCheck,
        OrganizationsHealthCheck,
        AuthHealthCheck,
        ModelsHealthCheck,
        KnowledgeHealthCheck,
        MemoryHealthCheck,
        MCPHealthCheck,
        PluginsHealthCheck,
        StorageHealthCheck,
        RateLimiterHealthCheck,
    ):
        registry.register(check_cls(probe=probes.get(check_cls.component), name=check_cls.component))
    return registry
