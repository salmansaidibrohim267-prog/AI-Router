from __future__ import annotations

import threading
from typing import Any

from .config import PluginConfig
from .exceptions import PluginPermissionDeniedError
from .logging import PluginLogger
from .models import PermissionResource


class PermissionManager:
    """Granular permission store with deny-by-default semantics.

    A plugin only holds the permissions explicitly granted from its manifest;
    any ``check`` for an undeclared resource/action pair is denied.
    """

    def __init__(self, config: PluginConfig | None = None, logger: PluginLogger | None = None) -> None:
        self._config = config or PluginConfig()
        self._logger = logger or PluginLogger(self._config)
        self._grants: dict[str, dict[str, set[str]]] = {}
        self._lock = threading.Lock()

    def grant(self, plugin: str, resource: str, actions: list[str] | None = None) -> None:
        actions = actions or ["*"]
        with self._lock:
            bucket = self._grants.setdefault(plugin, {})
            bucket.setdefault(resource, set()).update(actions)

    def grant_from_manifest(self, plugin: str, permissions: list[dict[str, Any]]) -> None:
        for permission in permissions:
            resource = permission.get("resource")
            actions = permission.get("actions") or ["*"]
            if resource:
                self.grant(plugin, resource, actions)
        self._logger.log_event("permissions.granted", plugin=plugin, count=len(permissions))

    def revoke(self, plugin: str, resource: str | None = None, action: str | None = None) -> bool:
        with self._lock:
            if plugin not in self._grants:
                return False
            if resource is None:
                del self._grants[plugin]
                return True
            bucket = self._grants[plugin]
            if resource not in bucket:
                return False
            if action is None:
                del bucket[resource]
                return True
            bucket[resource].discard(action)
            if not bucket[resource]:
                del bucket[resource]
            return True

    def check(self, plugin: str, resource: str, action: str = "*") -> bool:
        with self._lock:
            actions = self._grants.get(plugin, {}).get(resource, set())
        return "*" in actions or action in actions

    def check_or_raise(self, plugin: str, resource: str, action: str = "*") -> None:
        if not self.check(plugin, resource, action):
            raise PluginPermissionDeniedError(
                f"plugin {plugin!r} lacks permission {resource}:{action}", plugin=plugin, resource=resource, action=action
            )

    def permissions(self, plugin: str) -> dict[str, list[str]]:
        with self._lock:
            bucket = self._grants.get(plugin, {})
            return {resource: sorted(actions) for resource, actions in bucket.items()}

    def all_permissions(self) -> dict[str, dict[str, list[str]]]:
        with self._lock:
            return {plugin: {r: sorted(a) for r, a in bucket.items()} for plugin, bucket in self._grants.items()}

    def clear(self) -> None:
        with self._lock:
            self._grants.clear()
