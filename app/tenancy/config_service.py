from __future__ import annotations

from typing import Any

from .config import TenancyConfig
from .exceptions import TenantNotFoundError
from .logging import TenancyLogger
from .manager import TenantManager
from .models import CONFIG_SECTIONS

DEFAULT_TENANT_CONFIG: dict[str, dict[str, Any]] = {
    "llm": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.7},
    "embeddings": {"provider": "openai", "model": "text-embedding-3-small"},
    "reranker": {"enabled": False, "model": ""},
    "prompts": {"system": ""},
    "mcp": {"enabled": True, "servers": {}},
}


class TenantConfigService:
    def __init__(
        self,
        manager: TenantManager,
        defaults: dict[str, dict[str, Any]] | None = None,
        config: TenancyConfig | None = None,
        logger: TenancyLogger | None = None,
    ):
        self._manager = manager
        self._defaults = defaults or DEFAULT_TENANT_CONFIG
        self._config = config or TenancyConfig()
        self._logger = logger or TenancyLogger()

    @property
    def sections(self) -> tuple[str, ...]:
        return CONFIG_SECTIONS

    def get(self, tenant_id: str, section: str) -> dict[str, Any]:
        if section not in CONFIG_SECTIONS:
            raise ValueError(f"Unknown tenant config section {section!r}")
        try:
            tenant = self._manager.get(tenant_id)
        except TenantNotFoundError:
            tenant = None
        merged = dict(self._defaults.get(section, {}))
        if tenant is not None:
            merged.update(tenant.config_section(section))
        return merged

    def set(self, tenant_id: str, section: str, values: dict[str, Any]) -> dict[str, Any]:
        if section not in CONFIG_SECTIONS:
            raise ValueError(f"Unknown tenant config section {section!r}")
        self._manager.set_config(tenant_id, section, values)
        self._logger.log_event("config_updated", tenant_id=tenant_id, section=section)
        return self.get(tenant_id, section)

    def effective(self, tenant_id: str) -> dict[str, dict[str, Any]]:
        return {section: self.get(tenant_id, section) for section in CONFIG_SECTIONS}

    def update_defaults(self, defaults: dict[str, dict[str, Any]]) -> None:
        for section, values in defaults.items():
            if section not in CONFIG_SECTIONS:
                raise ValueError(f"Unknown tenant config section {section!r}")
            self._defaults.setdefault(section, {}).update(values)
