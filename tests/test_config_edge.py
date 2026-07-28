import pytest
import yaml
import tempfile
from pathlib import Path
from app.config import ConfigManager
from app.exceptions import ConfigurationError


class TestConfigEdgeCases:
    def test_config_loaded_without_providers_yaml(self):
        cm = ConfigManager()
        assert cm.config is not None

    def test_get_task_config_missing(self):
        cm = ConfigManager()
        assert cm.get_task_config("nonexistent") is None

    def test_get_primary_provider_missing(self):
        cm = ConfigManager()
        assert cm.get_primary_provider("nonexistent") is None

    def test_get_fallback_providers_missing(self):
        cm = ConfigManager()
        assert cm.get_fallback_providers("nonexistent") == []

    def test_get_scoring_empty_for_unknown_task(self):
        cm = ConfigManager()
        assert cm.get_scoring("nonexistent") == {}

    def test_get_rate_limit_defaults(self):
        cm = ConfigManager()
        limit, window = cm.get_rate_limit()
        assert isinstance(limit, int)
        assert isinstance(window, int)

    def test_get_health_check_interval(self):
        cm = ConfigManager()
        interval = cm.get_health_check_interval()
        assert interval > 0

    def test_get_timeout(self):
        cm = ConfigManager()
        timeout = cm.get_timeout()
        assert timeout > 0

    def test_config_hash_not_empty(self):
        cm = ConfigManager()
        assert cm.config_hash != ""

    def test_reload_successful(self):
        cm = ConfigManager()
        result = cm.reload()
        assert result.success is True

    def test_disable_watcher(self):
        cm = ConfigManager()
        cm.disable_watcher()
        assert cm._watch_active is False

    def test_enable_watcher(self):
        cm = ConfigManager()
        callback_called = [False]
        def callback():
            callback_called[0] = True
        cm.enable_watcher(callback=callback)
        assert cm._watch_active is True
        cm.disable_watcher()


class TestConfigLegacy:
    from app.config import Config

    def test_legacy_get_primary(self):
        cfg = self.Config()
        result = cfg.get_primary("chat")
        assert "provider" in result
        assert "model" in result

    def test_legacy_get_fallback(self):
        cfg = self.Config()
        result = cfg.get_fallback("chat")
        assert isinstance(result, list)

    def test_legacy_get_primary_missing_task(self):
        cfg = self.Config()
        result = cfg.get_primary("nonexistent")
        assert result["provider"] == "openrouter"

    def test_legacy_get_fallback_missing_task(self):
        cfg = self.Config()
        result = cfg.get_fallback("nonexistent")
        assert result == []


class TestConfigLegacyClass:
    """Separate class to avoid pytest collecting Config as test."""
    def test_create(self):
        from app.config import Config
        c = Config()
        assert c._manager is not None
