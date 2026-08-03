from __future__ import annotations

import threading
import time
from typing import Callable

from .config import AdminConfig
from .exceptions import FeatureFlagInvalidError, FeatureFlagNotFoundError
from .logging import AdminLogger
from .models import FeatureFlag
from .repositories import FlagRepository


class FeatureFlagManager:
    """Feature flag registry with change notification (Observer pattern).

    Subscribers are notified whenever a flag changes so the platform can
    react (e.g. reload middleware, enable experimental routes).
    """

    def __init__(
        self,
        config: AdminConfig | None = None,
        repository: FlagRepository | None = None,
        logger: AdminLogger | None = None,
    ) -> None:
        from .repositories import InMemoryFlagRepository

        self._config = config or AdminConfig()
        self._repository = repository or InMemoryFlagRepository()
        self._logger = logger or AdminLogger(self._config)
        self._subscribers: dict[str, list[Callable[[FeatureFlag], None]]] = {}
        self._lock = threading.Lock()

    @property
    def repository(self) -> FlagRepository:
        return self._repository

    def register(
        self, name: str, enabled: bool = False, environment: str = "*", owner: str = "platform", description: str = ""
    ) -> FeatureFlag:  # noqa: E501
        flag = FeatureFlag(name=name, enabled=enabled, environment=environment, owner=owner, description=description)
        return self._repository.create(flag)

    def enable(self, name: str) -> FeatureFlag:
        flag = self._repository.get(name)
        if flag.enabled:
            return flag
        flag.enabled = True
        flag.updated_at = time.time()
        self._repository.update(flag)
        self._notify(flag)
        self._logger.log_event("feature_flag.enabled", name=name)
        return flag

    def disable(self, name: str) -> FeatureFlag:
        flag = self._repository.get(name)
        if not flag.enabled:
            return flag
        flag.enabled = False
        flag.updated_at = time.time()
        self._repository.update(flag)
        self._notify(flag)
        self._logger.log_event("feature_flag.disabled", name=name)
        return flag

    def set(self, name: str, enabled: bool) -> FeatureFlag:
        if not isinstance(enabled, bool):
            raise FeatureFlagInvalidError(name)
        return self.enable(name) if enabled else self.disable(name)

    def is_enabled(self, name: str, environment: str = "") -> bool:
        try:
            flag = self._repository.get(name)
        except FeatureFlagNotFoundError:
            default = self._config.feature_defaults.get(name, False)
            return default if environment else default
        if flag.environment != "*" and environment and flag.environment != environment:
            return False
        return flag.enabled

    def get(self, name: str) -> FeatureFlag:
        return self._repository.get(name)

    def delete(self, name: str) -> bool:
        return self._repository.delete(name)

    def list(self) -> list[FeatureFlag]:
        return self._repository.list()

    def enabled_count(self) -> int:
        return sum(1 for flag in self.list() if flag.enabled)

    def subscribe(self, name: str, callback: Callable[[FeatureFlag], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(name, []).append(callback)

    def unsubscribe(self, name: str, callback: Callable[[FeatureFlag], None]) -> bool:
        with self._lock:
            callbacks = self._subscribers.get(name, [])
            if callback not in callbacks:
                return False
            callbacks.remove(callback)
            return True

    def _notify(self, flag: FeatureFlag) -> None:
        for callback in list(self._subscribers.get(flag.name, [])):
            callback(flag)
