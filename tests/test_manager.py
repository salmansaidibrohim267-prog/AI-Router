import pytest
from app.providers.manager import ProviderManager, CircuitBreaker


class TestCircuitBreaker:
    def setup_method(self):
        self.cb = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)

    def test_initial_state_closed(self):
        assert self.cb.state == "closed"
        assert self.cb.is_open is False
        assert self.cb.failure_count == 0

    def test_record_failure(self):
        self.cb.record_failure()
        assert self.cb.failure_count == 1
        assert self.cb.is_open is False

    def test_opens_after_threshold(self):
        for _ in range(5):
            self.cb.record_failure()
        assert self.cb.is_open is True
        assert self.cb.state == "open"

    def test_half_open_after_timeout(self):
        for _ in range(5):
            self.cb.record_failure()
        assert self.cb.is_open is True
        self.cb._last_failure_time = 0
        assert self.cb.is_open is False
        assert self.cb.state == "half-open"

    def test_record_success_closes(self):
        for _ in range(5):
            self.cb.record_failure()
        self.cb._last_failure_time = 0
        _ = self.cb.is_open
        assert self.cb.state == "half-open"
        for _ in range(3):
            self.cb.record_success()
        assert self.cb.state == "closed"
        assert self.cb.failure_count == 0

    def test_reset(self):
        for _ in range(5):
            self.cb.record_failure()
        assert self.cb.is_open is True
        self.cb.reset()
        assert self.cb.state == "closed"
        assert self.cb.failure_count == 0
        assert self.cb.is_open is False

    def test_record_success_resets_failures(self):
        self.cb.record_failure()
        self.cb.record_success()
        assert self.cb.failure_count == 0


class TestProviderManager:
    def setup_method(self):
        self.manager = ProviderManager()

    def test_resolve_name_direct(self):
        assert self.manager.resolve_name("openrouter") == "openrouter"
        assert self.manager.resolve_name("ollama") == "ollama"

    def test_resolve_name_alias(self):
        assert self.manager.resolve_name("gemini") == "google"

    def test_resolve_name_case_insensitive(self):
        assert self.manager.resolve_name("OpenRouter") == "openrouter"
        assert self.manager.resolve_name("GEMINI") == "google"

    def test_is_disabled_default(self):
        assert self.manager.is_disabled("openrouter") is False

    def test_enable_provider(self):
        self.manager._disabled.add("openrouter")
        assert self.manager.is_disabled("openrouter") is True
        self.manager.enable_provider("openrouter")
        assert self.manager.is_disabled("openrouter") is False

    def test_track_failure(self):
        self.manager._track_failure("test_provider")
        assert "test_provider" in self.manager._circuit_breakers
        assert self.manager._circuit_breakers["test_provider"].failure_count == 1

    def test_track_failure_disables_after_threshold(self):
        for _ in range(5):
            self.manager._track_failure("test_provider2")
        assert self.manager.is_disabled("test_provider2") is True

    def test_get_disabled_providers(self):
        self.manager._disabled.add("test1")
        self.manager._disabled.add("test2")
        disabled = self.manager.get_disabled_providers()
        assert "test1" in disabled
        assert "test2" in disabled
        self.manager._disabled.clear()

    def test_get_provider_names_empty_by_default(self):
        names = self.manager.get_provider_names()
        assert isinstance(names, list)

    def test_circuit_state_closed_by_default(self):
        assert self.manager.get_circuit_state("nonexistent") == "closed"

    def test_is_circuit_open_default(self):
        assert self.manager.is_circuit_open("nonexistent") is False

    def test_get_failure_rate_zero_default(self):
        assert self.manager.get_failure_rate("nonexistent") == 0.0
