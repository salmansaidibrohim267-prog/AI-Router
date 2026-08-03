from __future__ import annotations

import threading
from typing import Any

from .exceptions import SettingNotFoundError, SettingValidationError
from .logging import AdminLogger
from .models import SettingDefinition
from .repositories import DEFAULT_SETTINGS, SettingsRepository


class SystemSettingsManager:
    """Central system settings store with typed validation and env overrides."""

    def __init__(
        self,
        repository: SettingsRepository | None = None,
        definitions: dict[str, SettingDefinition] | None = None,
        logger: AdminLogger | None = None,
        config: Any = None,
    ) -> None:
        from .repositories import InMemorySettingsRepository

        self._repository = repository or InMemorySettingsRepository()
        self._definitions = dict(DEFAULT_SETTINGS)
        if definitions:
            self._definitions.update(definitions)
        self._logger = logger or AdminLogger()
        self._lock = threading.Lock()

    @property
    def repository(self) -> SettingsRepository:
        return self._repository

    @property
    def definitions(self) -> dict[str, SettingDefinition]:
        return dict(self._definitions)

    def register_definition(self, definition: SettingDefinition) -> None:
        self._definitions[definition.key] = definition

    def get(self, key: str) -> Any:
        definition = self._definitions.get(key)
        if definition is None:
            raise SettingNotFoundError(key)
        value = self._repository.get(key)
        if value is None:
            value = definition.default
        return value

    def set(self, key: str, value: Any, actor: str = "admin") -> Any:
        definition = self._definitions.get(key)
        if definition is None:
            raise SettingNotFoundError(key)
        if not definition.validate(value):
            raise SettingValidationError(key, f"expected {definition.type.value}")
        self._repository.set(key, value)
        self._logger.log_event(
            "setting.updated", key=key, value=value if not definition.sensitive else "***", actor=actor
        )  # noqa: E501
        return value

    def reset(self, key: str) -> Any:
        definition = self._definitions.get(key)
        if definition is None:
            raise SettingNotFoundError(key)
        return self._repository.set(key, definition.default)

    def all(self, include_sensitive: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, definition in self._definitions.items():
            value = self.get(key)
            if definition.sensitive and not include_sensitive:
                value = "***"
            result[key] = value
        return result

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "key": definition.key,
                "type": definition.type.value,
                "default": definition.default,
                "value": self.get(definition.key),
                "sensitive": definition.sensitive,
                "description": definition.description,
            }
            for definition in self._definitions.values()
        ]
