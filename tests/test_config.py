import pytest
from app.config import ConfigManager
from app.models import TaskType


class TestConfigReload:
    def setup_method(self):
        self.cm = ConfigManager()

    def test_config_loaded(self):
        assert self.cm.config is not None
        assert len(self.cm.config.tasks) > 0

    def test_get_task_config(self):
        cfg = self.cm.get_task_config("chat")
        assert cfg is not None
        assert cfg.primary.name == "ollama"
        assert cfg.primary.model == "qwen2.5-coder:7b"
        assert len(cfg.fallback) > 0

    def test_get_primary_provider(self):
        primary = self.cm.get_primary_provider("chat")
        assert primary is not None
        assert primary.name == "ollama"

    def test_get_fallback_providers(self):
        fallbacks = self.cm.get_fallback_providers("chat")
        assert len(fallbacks) > 0
        assert fallbacks[0].name == "ollama"

    def test_get_supported_tasks(self):
        tasks = self.cm.get_supported_tasks()
        assert "chat" in tasks
        assert "coding" in tasks
        assert "architecture" in tasks
        assert "analysis" in tasks

    def test_get_provider_config(self):
        cfg = self.cm.get_provider_config("ollama")
        assert cfg is not None
        assert cfg.name == "ollama"

    def test_get_all_provider_configs(self):
        configs = self.cm.get_all_provider_configs()
        assert len(configs) > 0
        names = [c.name for c in configs]
        assert "ollama" in names

    def test_get_cache_ttl(self):
        ttl = self.cm.get_cache_ttl()
        assert ttl > 0

    def test_get_rate_limit(self):
        limit, window = self.cm.get_rate_limit()
        assert limit > 0
        assert window > 0

    def test_reload(self):
        result = self.cm.reload()
        assert result.success is True
        assert result.message != ""

    def test_config_hash(self):
        assert self.cm.config_hash != ""
