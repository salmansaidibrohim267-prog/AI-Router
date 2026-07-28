"""Configuration management for AI Router."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from app.exceptions import ConfigurationError, ValidationError
from app.models import ProviderConfig, ReloadConfigResponse, RouterConfig, TaskConfig


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
MODELS_CONFIG = CONFIG_DIR / "models.yaml"
PROVIDERS_CONFIG = CONFIG_DIR / "providers.yaml"


class ConfigManager:
    """Manages configuration loading, validation, and hot-reloading."""

    def __init__(self):
        self._config: RouterConfig | None = None
        self._config_hash: str = ""
        self._lock = threading.RLock()
        self._last_mtime: float = 0
        self._watch_active = False
        self._reload_callbacks = []
        self._config = self._load_config()
        if self._config:
            self._config_hash = self._compute_hash()

    def _load_config(self) -> RouterConfig:
        """Load and validate configuration from YAML files."""
        try:
            if not MODELS_CONFIG.exists():
                raise ConfigurationError(f"Config file not found: {MODELS_CONFIG}")

            with open(MODELS_CONFIG, encoding="utf-8") as f:
                models_data = yaml.safe_load(f) or {}

            providers_data = {}
            if PROVIDERS_CONFIG.exists():
                with open(PROVIDERS_CONFIG, encoding="utf-8") as f:
                    providers_data = yaml.safe_load(f) or {}

            config_data = self._merge_configs(models_data, providers_data)
            config = RouterConfig(**config_data)
            self._validate_config(config)
            return config

        except PydanticValidationError as e:
            raise ConfigurationError(
                "Invalid configuration",
                details={"validation_errors": e.errors()},
            ) from e
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML: {e}") from e

    def get_task_config(self, task_name: str) -> TaskConfig | None:
        if not self._config:
            return None
        return self._config.tasks.get(task_name)

    def get_provider_config(self, provider_name: str) -> ProviderConfig | None:
        if not self._config:
            return None
        for task_config in self._config.tasks.values():
            if task_config.primary.name == provider_name:
                return task_config.primary
            for fallback in task_config.fallback:
                if fallback.name == provider_name:
                    return fallback
        return None

    def get_all_provider_configs(self) -> list[ProviderConfig]:
        if not self._config:
            return []
        providers = []
        seen = set()
        for task_config in self._config.tasks.values():
            if task_config.primary.name not in seen:
                providers.append(task_config.primary)
                seen.add(task_config.primary.name)
            for fallback in task_config.fallback:
                if fallback.name not in seen:
                    providers.append(fallback)
                    seen.add(fallback.name)
        return providers

    def get_supported_tasks(self) -> list[str]:
        if not self._config:
            return []
        return list(self._config.tasks.keys())

    def get_models_for_task(self, task: str) -> list[str]:
        task_config = self.get_task_config(task)
        if not task_config:
            return []
        models = [task_config.primary.model] if hasattr(task_config.primary, "model") else []
        for fallback in task_config.fallback:
            if hasattr(fallback, "model"):
                models.append(fallback.model)
        return models

    def get_primary_provider(self, task: str) -> ProviderConfig | None:
        task_config = self.get_task_config(task)
        return task_config.primary if task_config else None

    def get_fallback_providers(self, task: str) -> list[ProviderConfig]:
        task_config = self.get_task_config(task)
        return task_config.fallback if task_config else []

    def get_scoring(self, task: str) -> dict[str, int]:
        if not self._config:
            return {}
        return self._config.scoring.get(task, {})

    def get_cache_ttl(self) -> int:
        return self._config.cache_ttl if self._config else 300

    def get_rate_limit(self) -> tuple[int, int]:
        if not self._config:
            return 100, 60
        return self._config.rate_limit, self._config.rate_limit_window

    def get_health_check_interval(self) -> int:
        return self._config.health_check_interval if self._config else 30

    def get_timeout(self) -> float:
        return self._config.timeout if self._config else 60.0

    def _merge_configs(self, models_data: dict, providers_data: dict) -> dict[str, Any]:
        provider_configs = {}
        for provider in providers_data.get("providers", []):
            provider_configs[provider["name"]] = ProviderConfig(**provider)

        tasks = {}
        for task_name, task_data in models_data.items():
            primary_data = task_data.get("primary", {})
            fallback_data = task_data.get("fallback", [])

            primary_name = primary_data.get("provider")
            primary_model = primary_data.get("model")

            if primary_name in provider_configs:
                primary = provider_configs[primary_name].model_copy()
                primary.model = primary_model
            else:
                primary = ProviderConfig(
                    name=primary_name,
                    display_name=primary_name,
                    model=primary_model,
                )

            fallbacks = []
            for fb in fallback_data:
                fb_name = fb.get("provider")
                fb_model = fb.get("model")
                if fb_name in provider_configs:
                    fb_config = provider_configs[fb_name].model_copy()
                    fb_config.model = fb_model
                else:
                    fb_config = ProviderConfig(
                        name=fb_name,
                        display_name=fb_name,
                        model=fb_model,
                    )
                fallbacks.append(fb_config)

            tasks[task_name] = TaskConfig(primary=primary, fallback=fallbacks)

        scoring = models_data.get("scoring", {})

        return {
            "tasks": tasks,
            "default_task": models_data.get("default_task", "chat"),
            "scoring": scoring,
            "cache_ttl": models_data.get("cache_ttl", 300),
            "rate_limit": models_data.get("rate_limit", 100),
            "rate_limit_window": models_data.get("rate_limit_window", 60),
            "health_check_interval": models_data.get("health_check_interval", 30),
            "timeout": models_data.get("timeout", 60.0),
        }

    def _validate_config(self, config: RouterConfig) -> None:
        if not config.tasks:
            raise ValidationError("No tasks configured")
        for task_name, task_config in config.tasks.items():
            if not task_config.primary.name:
                raise ValidationError(f"Task '{task_name}': primary provider name is required")
            if not task_config.primary.model:
                raise ValidationError(f"Task '{task_name}': primary model is required")
            for i, fallback in enumerate(task_config.fallback):
                if not fallback.name:
                    raise ValidationError(f"Task '{task_name}': fallback[{i}] provider name is required")
                if not fallback.model:
                    raise ValidationError(f"Task '{task_name}': fallback[{i}] model is required")

    def reload(self) -> ReloadConfigResponse:
        """Reload configuration from files."""
        with self._lock:
            old_hash = self._config_hash
            try:
                self._config = self._load_config()
                self._config_hash = self._compute_hash()
                self._last_mtime = time.time()
                return ReloadConfigResponse(
                    success=True,
                    message="Configuration reloaded successfully",
                    config_hash=self._config_hash,
                )
            except Exception as e:
                self._config_hash = old_hash
                return ReloadConfigResponse(
                    success=False,
                    message=f"Failed to reload configuration: {e}",
                    config_hash=old_hash,
                )

    def _compute_hash(self) -> str:
        if not self._config:
            return ""
        config_str = self._config.model_dump_json()
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]

    @property
    def config(self) -> RouterConfig | None:
        return self._config

    @property
    def config_hash(self) -> str:
        return self._config_hash

    # Config Watcher (auto-reload on file change)
    def enable_watcher(self, callback=None):
        """Enable file watching for auto-reload."""
        self._watch_active = True
        if callback:
            self._reload_callbacks.append(callback)

        def watch_loop():
            while self._watch_active:
                try:
                    current_mtime = 0
                    if MODELS_CONFIG.exists():
                        current_mtime = max(current_mtime, os.path.getmtime(MODELS_CONFIG))
                    if PROVIDERS_CONFIG.exists():
                        current_mtime = max(current_mtime, os.path.getmtime(PROVIDERS_CONFIG))

                    if self._last_mtime > 0 and current_mtime > self._last_mtime:
                        time.sleep(0.5)
                        result = self.reload()
                        if result.success:
                            for cb in self._reload_callbacks:
                                try:
                                    cb()
                                except Exception:
                                    pass
                    self._last_mtime = current_mtime
                except Exception:
                    pass
                time.sleep(2)

        thread = threading.Thread(target=watch_loop, daemon=True)
        thread.start()

    def disable_watcher(self):
        self._watch_active = False


config_manager = ConfigManager()


class Config:
    """Legacy config class for backward compatibility."""

    def __init__(self):
        self._manager = config_manager

    def get_primary(self, task: str) -> dict:
        provider = self._manager.get_primary_provider(task)
        if provider:
            return {"provider": provider.name, "model": provider.model}
        return {"provider": "openrouter", "model": "openai/gpt-oss-20b:free"}

    def get_fallback(self, task: str) -> list[dict]:
        fallbacks = self._manager.get_fallback_providers(task)
        return [{"provider": f.name, "model": f.model} for f in fallbacks]


config = Config()
