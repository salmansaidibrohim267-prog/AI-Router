"""Tests for custom provider discovery SDK."""

from pathlib import Path

import pytest

from app.providers.discovery import discover_custom_providers
from app.providers.manager import _get_provider_registry


class TestCustomProviderDiscovery:
    def test_discover_custom_providers(self):
        providers = discover_custom_providers("providers")
        assert "custom_test" in providers

    def test_custom_provider_is_baseprovider(self):
        from app.providers.base import BaseProvider
        providers = discover_custom_providers("providers")
        assert issubclass(providers["custom_test"], BaseProvider)

    def test_custom_provider_name(self):
        providers = discover_custom_providers("providers")
        assert providers["custom_test"].name == "custom_test"

    def test_empty_dir_returns_empty(self, tmp_path):
        providers = discover_custom_providers(str(tmp_path))
        assert providers == {}

    def test_non_existent_dir_returns_empty(self):
        providers = discover_custom_providers("/nonexistent/path")
        assert providers == {}

    def test_registry_includes_custom(self):
        registry = _get_provider_registry()
        assert "custom_test" in registry

    def test_registry_includes_builtins(self):
        registry = _get_provider_registry()
        assert "openai" in registry
        assert "anthropic" in registry
        assert "google" in registry

    def test_custom_provider_has_required_methods(self):
        providers = discover_custom_providers("providers")
        from app.providers.base import BaseProvider
        assert hasattr(providers["custom_test"], "chat")
        assert hasattr(providers["custom_test"], "embeddings")
        assert hasattr(providers["custom_test"], "health_check")
        assert hasattr(providers["custom_test"], "list_models")

    def test_custom_provider_can_be_instantiated(self):
        providers = discover_custom_providers("providers")
        instance = providers["custom_test"]()
        assert instance.name == "custom_test"
        assert instance.display_name == "Custom Test Provider"
