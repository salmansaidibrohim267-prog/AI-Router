import pytest
from app.providers.openrouter import OpenRouterProvider
from app.providers.ollama import OllamaProvider
from app.providers.groq import GroqProvider
from app.providers.base import BaseProvider


class TestProviderInterface:
    def test_openrouter_inherits_base(self):
        assert issubclass(OpenRouterProvider, BaseProvider)

    def test_ollama_inherits_base(self):
        assert issubclass(OllamaProvider, BaseProvider)

    def test_groq_inherits_base(self):
        assert issubclass(GroqProvider, BaseProvider)

    def test_all_providers_have_required_methods(self):
        required = ["chat", "stream_chat", "embeddings", "health_check", "list_models"]
        for provider_cls in [OpenRouterProvider, OllamaProvider, GroqProvider]:
            for method in required:
                assert hasattr(provider_cls, method)
                assert method in provider_cls.__dict__

    def test_provider_has_name(self):
        assert OpenRouterProvider.name == "openrouter"
        assert OllamaProvider.name == "ollama"
        assert GroqProvider.name == "groq"

    def test_provider_has_display_name(self):
        assert OpenRouterProvider.display_name == "OpenRouter"
        assert OllamaProvider.display_name == "Ollama"
        assert GroqProvider.display_name == "Groq"
