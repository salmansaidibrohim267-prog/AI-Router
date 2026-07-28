import pytest
from app.logger import StructuredLogger, JSONFormatter
import logging


class TestJSONFormatter:
    def setup_method(self):
        self.formatter = JSONFormatter()
        self.record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

    def test_format_contains_timestamp(self):
        output = self.formatter.format(self.record)
        assert '"timestamp"' in output

    def test_format_contains_level(self):
        output = self.formatter.format(self.record)
        assert '"INFO"' in output

    def test_format_contains_message(self):
        output = self.formatter.format(self.record)
        assert '"test message"' in output

    def test_sensitive_data_masking(self):
        self.record.__dict__["api_key"] = "sk-secret-key-12345"
        self.record.__dict__["token"] = "my-secret-token"
        output = self.formatter.format(self.record)
        import json
        parsed = json.loads(output)
        assert parsed["api_key"] != "sk-secret-key-12345"
        assert "****" in parsed["api_key"]
        assert parsed["token"] != "my-secret-token"
        assert "****" in parsed["token"]

    def test_nonsensitive_data_not_masked(self):
        self.record.__dict__["request_id"] = "req-123"
        self.record.__dict__["provider"] = "openai"
        output = self.formatter.format(self.record)
        import json
        parsed = json.loads(output)
        assert parsed["request_id"] == "req-123"
        assert parsed["provider"] == "openai"

    def test_short_sensitive_value_masked(self):
        self.record.__dict__["password"] = "12345678"
        output = self.formatter.format(self.record)
        import json
        parsed = json.loads(output)
        assert parsed["password"] == "****"


class TestStructuredLogger:
    def setup_method(self):
        self.logger = StructuredLogger(log_dir="/tmp/test_logs", max_memory_logs=100)

    def test_log_request_adds_to_memory(self):
        self.logger.log_request(
            request_id="req-1",
            provider="openai",
            model="gpt-4",
            task="chat",
            latency_ms=100.0,
            success=True,
        )
        logs = self.logger.get_recent_logs(1)
        assert len(logs) == 1
        assert logs[0].request_id == "req-1"

    def test_get_log_by_request_id(self):
        self.logger.log_request(
            request_id="find-me",
            provider="test",
            model="test",
            task="chat",
            latency_ms=50.0,
            success=True,
        )
        log = self.logger.get_log("find-me")
        assert log is not None
        assert log.request_id == "find-me"

    def test_get_log_not_found(self):
        assert self.logger.get_log("nonexistent") is None

    def test_get_logs_with_filtering(self):
        self.logger.log_request(
            request_id="r1", provider="openai", model="gpt-4", task="chat",
            latency_ms=10.0, success=True,
        )
        self.logger.log_request(
            request_id="r2", provider="ollama", model="llama2", task="chat",
            latency_ms=20.0, success=False, error="timeout",
        )
        success_logs = self.logger.get_logs(limit=10, success=True)
        assert all(l.success for l in success_logs)

        provider_logs = self.logger.get_logs(limit=10, provider="openai")
        assert all(l.provider == "openai" for l in provider_logs)

    def test_clear(self):
        self.logger.log_request(
            request_id="del-me", provider="test", model="test", task="chat",
            latency_ms=1.0, success=True,
        )
        self.logger.clear()
        assert len(self.logger.get_recent_logs(10)) == 0

    def test_now_returns_datetime(self):
        from datetime import datetime
        assert isinstance(self.logger.now(), datetime)

    def test_max_memory_logs(self):
        small = StructuredLogger(log_dir="/tmp/test_logs2", max_memory_logs=5)
        for i in range(10):
            small.log_request(
                request_id=f"req-{i}", provider="test", model="test", task="chat",
                latency_ms=1.0, success=True,
            )
        assert len(small.get_recent_logs(100)) <= 5

    def teardown_method(self):
        import shutil
        shutil.rmtree("/tmp/test_logs", ignore_errors=True)
        shutil.rmtree("/tmp/test_logs2", ignore_errors=True)
