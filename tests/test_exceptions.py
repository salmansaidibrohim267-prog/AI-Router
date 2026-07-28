import pytest
from app.exceptions import (
    AIRouterError,
    ConfigurationError,
    ValidationError,
    ProviderError,
    ProviderUnavailableError,
    ProviderTimeoutError,
    ProviderAuthError,
    ProviderRateLimitError,
    RouterError,
    NoHealthyProviderError,
    AllProvidersFailedError,
    CacheError,
    RateLimitError,
)


class TestBaseException:
    def test_airouter_error_defaults(self):
        e = AIRouterError("test error")
        assert e.message == "test error"
        assert e.code == "INTERNAL_ERROR"
        assert e.status_code == 500
        assert e.details == {}

    def test_to_dict(self):
        e = AIRouterError("test", code="TEST", status_code=400, details={"key": "val"})
        d = e.to_dict()
        assert d["error"]["code"] == "TEST"
        assert d["error"]["message"] == "test"
        assert d["error"]["details"]["key"] == "val"


class TestConfigurationError:
    def test_default_code(self):
        e = ConfigurationError("bad config")
        assert e.code == "CONFIGURATION_ERROR"
        assert e.status_code == 500


class TestValidationError:
    def test_default_code_and_status(self):
        e = ValidationError("invalid input")
        assert e.code == "VALIDATION_ERROR"
        assert e.status_code == 400


class TestProviderError:
    def test_with_provider_and_model(self):
        e = ProviderError("failed", provider="openai", model="gpt-4")
        assert e.provider == "openai"
        assert e.model == "gpt-4"
        assert e.code == "PROVIDER_ERROR"
        assert e.status_code == 502
        assert e.details["provider"] == "openai"
        assert e.details["model"] == "gpt-4"


class TestProviderUnavailableError:
    def test_default_code_and_status(self):
        e = ProviderUnavailableError("down", provider="ollama")
        assert e.code == "PROVIDER_UNAVAILABLE"
        assert e.status_code == 503


class TestProviderTimeoutError:
    def test_with_timeout(self):
        e = ProviderTimeoutError("timeout", provider="openai", timeout=30.0)
        assert e.code == "PROVIDER_TIMEOUT"
        assert e.status_code == 504
        assert e.details["timeout"] == 30.0


class TestProviderAuthError:
    def test_default_code_and_status(self):
        e = ProviderAuthError("auth failed", provider="anthropic")
        assert e.code == "PROVIDER_AUTH_ERROR"
        assert e.status_code == 401


class TestProviderRateLimitError:
    def test_with_retry_after(self):
        e = ProviderRateLimitError("rate limited", provider="groq", retry_after=30)
        assert e.code == "PROVIDER_RATE_LIMIT"
        assert e.status_code == 429
        assert e.details["retry_after"] == 30


class TestRouterError:
    def test_default(self):
        e = RouterError("router issue")
        assert e.code == "ROUTER_ERROR"
        assert e.status_code == 500


class TestNoHealthyProviderError:
    def test_with_task(self):
        e = NoHealthyProviderError(task="chat", tried_providers=["openai", "ollama"])
        assert e.code == "NO_HEALTHY_PROVIDER"
        assert e.status_code == 503
        assert e.details["task"] == "chat"
        assert e.details["tried_providers"] == ["openai", "ollama"]


class TestAllProvidersFailedError:
    def test_with_task_and_errors(self):
        errors = [ProviderError("fail", provider="openai")]
        e = AllProvidersFailedError(task="chat", errors=errors)
        assert e.code == "ALL_PROVIDERS_FAILED"
        assert e.status_code == 502
        assert e.details["task"] == "chat"


class TestCacheError:
    def test_default(self):
        e = CacheError("cache issue")
        assert e.code == "CACHE_ERROR"
        assert e.status_code == 500


class TestRateLimitError:
    def test_with_retry_after(self):
        e = RateLimitError(retry_after=60)
        assert e.code == "RATE_LIMIT_EXCEEDED"
        assert e.status_code == 429
        assert e.details["retry_after"] == 60

    def test_default_message(self):
        e = RateLimitError()
        assert e.message == "Rate limit exceeded"
