from __future__ import annotations

import threading
from typing import Any, Callable

from .exceptions import ContainerError


class Container:
    """Minimal dependency-injection container (Service Locator + Factory patterns).

    Supports instance, singleton-factory and transient-factory registrations,
    constructor dependency resolution via ``provides`` hints, and cycle
    detection.
    """

    def __init__(self) -> None:
        self._instances: dict[str, Any] = {}
        self._singletons: dict[str, Callable[..., Any]] = {}
        self._singleton_cache: dict[str, Any] = {}
        self._transients: dict[str, Callable[..., Any]] = {}
        self._provides: dict[str, list[str]] = {}
        self._resolving: set[str] = set()
        self._lock = threading.Lock()

    def register_instance(self, key: str, instance: Any) -> None:
        with self._lock:
            self._instances[key] = instance

    def register_singleton(self, key: str, factory: Callable[..., Any]) -> None:
        with self._lock:
            self._singletons[key] = factory

    def register_transient(self, key: str, factory: Callable[..., Any]) -> None:
        with self._lock:
            self._transients[key] = factory

    def register_factory(self, key: str, factory: Callable[..., Any], singleton: bool = True) -> None:
        if singleton:
            self.register_singleton(key, factory)
        else:
            self.register_transient(key, factory)

    def register_provides(self, service: str, key: str) -> None:
        with self._lock:
            self._provides.setdefault(service, []).append(key)

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._instances or key in self._singletons or key in self._transients

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._instances.keys()) + list(self._singletons.keys()) + list(self._transients.keys())

    def resolve(self, key: str, **overrides: Any) -> Any:
        with self._lock:
            if key in self._instances:
                return self._instances[key]
            if key in self._singletons and key in self._singleton_cache:
                return self._singleton_cache[key]
            if key in self._singletons:
                factory = self._singletons[key]
            elif key in self._transients:
                factory = self._transients[key]
            else:
                raise ContainerError(f"no registration for dependency {key!r}", key=key)
            if key in self._resolving:
                raise ContainerError(f"circular dependency while resolving {key!r}", key=key)
            self._resolving.add(key)
        try:
            try:
                result = factory(**overrides)
            except TypeError:
                result = factory()
        finally:
            with self._lock:
                self._resolving.discard(key)
        if key in self._singletons:
            with self._lock:
                self._singleton_cache[key] = result
        return result

    def resolve_provides(self, service: str, **overrides: Any) -> list[Any]:
        keys = self._provides.get(service, [])
        return [self.resolve(key, **overrides) for key in keys]

    def clear(self) -> None:
        with self._lock:
            self._instances.clear()
            self._singletons.clear()
            self._singleton_cache.clear()
            self._transients.clear()
            self._provides.clear()
            self._resolving.clear()
