import pytest
from datetime import datetime
from pydantic import ValidationError
from app.models import (
    TaskType,
    ProviderStatus,
    MessageRole,
    Message,
    ChatRequest,
    ChatResponse,
    ChatChoice,
    Usage,
    StreamChunk,
    StreamChoice,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingData,
    ModelInfo,
    HealthCheckResponse,
    ProviderConfig,
    TaskConfig,
    RouterConfig,
    LogEntry,
    StatsSummary,
    CacheEntry,
    ReloadConfigResponse,
)


class TestEnums:
    def test_task_type_values(self):
        assert TaskType.CHAT.value == "chat"
        assert TaskType.CODING.value == "coding"
        assert TaskType.ANALYSIS.value == "analysis"
        assert TaskType.ARCHITECTURE.value == "architecture"

    def test_provider_status_values(self):
        assert ProviderStatus.HEALTHY.value == "healthy"
        assert ProviderStatus.UNHEALTHY.value == "unhealthy"
        assert ProviderStatus.UNKNOWN.value == "unknown"

    def test_message_role_values(self):
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"


class TestMessage:
    def test_valid_message(self):
        m = Message(role="user", content="hello")
        assert m.role == MessageRole.USER
        assert m.content == "hello"

    def test_message_with_name(self):
        m = Message(role="user", content="hi", name="alice")
        assert m.name == "alice"


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(
            model="gpt-4",
            messages=[Message(role="user", content="hello")],
        )
        assert req.model == "gpt-4"
        assert req.temperature == 0.7

    def test_request_with_all_fields(self):
        req = ChatRequest(
            model="gpt-4",
            messages=[Message(role="user", content="hello")],
            temperature=0.5,
            max_tokens=100,
            stream=True,
            metadata={"key": "val"},
        )
        assert req.temperature == 0.5
        assert req.stream is True
        assert req.metadata["key"] == "val"


class TestChatResponse:
    def test_valid_response(self):
        resp = ChatResponse(
            id="test-id",
            model="gpt-4",
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content="hi"),
                )
            ],
        )
        assert resp.object == "chat.completion"
        assert len(resp.choices) == 1

    def test_with_usage(self):
        resp = ChatResponse(
            id="test",
            model="gpt-4",
            choices=[
                ChatChoice(
                    index=0,
                    message=Message(role="assistant", content="hi"),
                )
            ],
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )
        assert resp.usage.total_tokens == 30


class TestStreamChunk:
    def test_valid_chunk(self):
        chunk = StreamChunk(
            id="chunk-1",
            model="gpt-4",
            choices=[
                StreamChoice(
                    index=0,
                    delta={"content": "Hello"},
                )
            ],
        )
        assert chunk.object == "chat.completion.chunk"


class TestEmbeddingRequest:
    def test_valid_request(self):
        req = EmbeddingRequest(model="text-embedding-3-small", input="hello")
        assert req.input == "hello"

    def test_with_list_input(self):
        req = EmbeddingRequest(model="test", input=["a", "b"])
        assert len(req.input) == 2


class TestEmbeddingResponse:
    def test_valid_response(self):
        resp = EmbeddingResponse(
            data=[
                EmbeddingData(embedding=[0.1, 0.2, 0.3], index=0),
            ],
            model="test",
            usage=Usage(prompt_tokens=5),
        )
        assert resp.object == "list"
        assert len(resp.data) == 1


class TestModelInfo:
    def test_valid_info(self):
        info = ModelInfo(
            id="gpt-4",
            created=1234567890,
            owned_by="openai",
            provider="openai",
        )
        assert info.supports_streaming is True
        assert info.supports_embeddings is False


class TestHealthCheckResponse:
    def test_valid_response(self):
        health = HealthCheckResponse(
            status=ProviderStatus.HEALTHY,
            provider="openai",
            latency_ms=100.0,
        )
        assert health.status == ProviderStatus.HEALTHY


class TestProviderConfig:
    def test_defaults(self):
        cfg = ProviderConfig(name="test", display_name="Test")
        assert cfg.timeout == 60.0
        assert cfg.max_retries == 3
        assert cfg.enabled is True


class TestTaskConfig:
    def test_valid_config(self):
        primary = ProviderConfig(name="openai", display_name="OpenAI")
        cfg = TaskConfig(primary=primary)
        assert cfg.primary.name == "openai"


class TestRouterConfig:
    def test_defaults(self):
        cfg = RouterConfig()
        assert cfg.default_task == "chat"
        assert cfg.cache_ttl == 300
        assert cfg.rate_limit == 100


class TestLogEntry:
    def test_valid_entry(self):
        entry = LogEntry(
            request_id="req-1",
            provider="openai",
            model="gpt-4",
            task="chat",
            latency_ms=100.0,
            success=True,
        )
        assert entry.success is True
        assert entry.error is None


class TestStatsSummary:
    def test_defaults(self):
        s = StatsSummary()
        assert s.total_requests == 0
        assert s.success_rate == 0.0


class TestCacheEntry:
    def test_valid_entry(self):
        entry = CacheEntry(key="k", value="v")
        assert entry.ttl == 300


class TestReloadConfigResponse:
    def test_valid_response(self):
        resp = ReloadConfigResponse(success=True, message="ok", config_hash="abc")
        assert resp.success is True
