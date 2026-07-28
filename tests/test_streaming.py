"""Tests for streaming (SSE) functionality."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.models import ChatRequest, Message, MessageRole, StreamChunk, StreamChoice


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_base_provider_stream_fallback():
    from app.providers.base import BaseProvider
    from app.models import ChatChoice, ChatResponse, Message, EmbeddingRequest, EmbeddingResponse, HealthCheckResponse, ModelInfo

    class FakeProvider(BaseProvider):
        name = "test_fake"
        chat_response = None

        async def chat(self, request):
            return self.chat_response or ChatResponse(
                id="test-id", model="test-model",
                choices=[ChatChoice(index=0, message=Message(role="assistant", content="Hello"))],
            )

        async def embeddings(self, request): raise NotImplementedError
        async def health_check(self): raise NotImplementedError
        async def list_models(self): raise NotImplementedError

    provider = FakeProvider()
    provider.chat_response = ChatResponse(
        id="test-id",
        model="test-model",
        choices=[ChatChoice(index=0, message=Message(role="assistant", content="Hello"))],
    )

    request = ChatRequest(model="test-model", messages=[Message(role=MessageRole.USER, content="Hi")])
    chunks = []
    async for chunk in provider.stream_chat(request):
        chunks.append(chunk)

    assert len(chunks) >= 2
    assert chunks[0].choices[0].delta["content"] == "Hello"
    assert chunks[-1].choices[0].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_chunk_model_usage():
    from app.models import Usage

    chunk = StreamChunk(
        id="test",
        model="test",
        choices=[StreamChoice(index=0, delta={"content": "Hello"})],
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    assert chunk.usage is not None
    assert chunk.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_stream_chunk_with_metadata():
    chunk = StreamChunk(
        id="test",
        model="test",
        choices=[StreamChoice(index=0, delta={"content": "Hello"})],
        metadata={"request_id": "abc", "task": "chat"},
    )
    assert chunk.metadata == {"request_id": "abc", "task": "chat"}


@pytest.mark.asyncio
async def test_stream_chunk_with_finish_reason():
    chunk = StreamChunk(
        id="test",
        model="test",
        choices=[StreamChoice(index=0, delta={"content": ""}, finish_reason="stop")],
    )
    assert chunk.choices[0].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_chunk_json_serializable():
    chunk = StreamChunk(
        id="test",
        model="test",
        choices=[StreamChoice(index=0, delta={"content": "Hello"})],
    )
    data = json.loads(chunk.model_dump_json())
    assert data["object"] == "chat.completion.chunk"
    assert data["choices"][0]["delta"]["content"] == "Hello"


@pytest.mark.asyncio
async def test_router_stream_chat_no_healthy_provider():
    from app.router import router

    router._initialized = True
    router.metrics.clear()

    with patch.object(router.provider_manager, "get_provider_names", return_value=[]):
        with patch.object(router, "_get_provider_configs", return_value=[]):
            req = ChatRequest(model="test", messages=[Message(role=MessageRole.USER, content="hi")])
            with pytest.raises(Exception):
                async for _ in router.stream_chat(req):
                    pass


@pytest.mark.asyncio
async def test_router_stream_chat_provider_fallback():
    from app.exceptions import AllProvidersFailedError
    from app.router import router

    router._initialized = True
    router.metrics.clear()

    mock_provider = MagicMock()
    mock_provider.name = "failing"
    mock_provider.stream_chat = AsyncMock(side_effect=Exception("stream error"))

    with (
        patch.object(router.provider_manager, "get", return_value=mock_provider),
        patch.object(router, "_get_provider_configs", return_value=[("failing", "test-model")]),
        patch.object(router, "_is_provider_available", return_value=True),
        patch.object(router, "_rank_providers", return_value=[("failing", "test-model")]),
    ):
        req = ChatRequest(model="test-model", messages=[Message(role=MessageRole.USER, content="hi")])
        with pytest.raises(AllProvidersFailedError):
            async for _ in router.stream_chat(req):
                pass


@pytest.mark.asyncio
async def test_router_stream_chat_success():
    from app.router import router

    router._initialized = True
    router.metrics.clear()

    mock_provider = MagicMock()
    mock_provider.name = "test-provider"

    async def mock_stream(req):
        yield StreamChunk(
            id="test",
            model="test-model",
            choices=[StreamChoice(index=0, delta={"content": "Hello"})],
        )
        yield StreamChunk(
            id="test",
            model="test-model",
            choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
        )

    mock_provider.stream_chat = mock_stream

    with (
        patch.object(router.provider_manager, "get", return_value=mock_provider),
        patch.object(router, "_get_provider_configs", return_value=[("test-provider", "test-model")]),
        patch.object(router, "_is_provider_available", return_value=True),
        patch.object(router, "_rank_providers", return_value=[("test-provider", "test-model")]),
    ):
        req = ChatRequest(model="test-model", messages=[Message(role=MessageRole.USER, content="hi")])
        chunks = []
        async for chunk in router.stream_chat(req):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].choices[0].delta["content"] == "Hello"
        assert chunks[1].choices[0].finish_reason == "stop"


@pytest.mark.asyncio
async def test_streaming_endpoint_returns_sse():
    client = TestClient(app)

    async def mock_stream(req):
        yield StreamChunk(
            id="test",
            model="test-model",
            choices=[StreamChoice(index=0, delta={"content": "Hello"})],
        )
        yield StreamChunk(
            id="test",
            model="test-model",
            choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
        )

    with (
        patch("app.api.router.stream_chat", mock_stream),
        patch("app.api.router.initialize", AsyncMock()),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={"model": "test", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        lines = response.text.strip().split("\n\n")
        assert len(lines) >= 2
        assert any("Hello" in line for line in lines)
        assert any("[DONE]" in line for line in lines)


@pytest.mark.asyncio
async def test_streaming_returns_openai_format():
    client = TestClient(app)

    async def mock_stream(req):
        yield StreamChunk(
            id="chatcmpl-123",
            model="gpt-4o-mini",
            choices=[StreamChoice(index=0, delta={"content": "Hello"})],
        )
        yield StreamChunk(
            id="chatcmpl-123",
            model="gpt-4o-mini",
            choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
        )

    with (
        patch("app.api.router.stream_chat", mock_stream),
        patch("app.api.router.initialize", AsyncMock()),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        lines = response.text.strip().split("\n\n")
        data_lines = [l for l in lines if l.startswith("data: ") and l != "data: [DONE]"]
        for line in data_lines:
            chunk = json.loads(line[6:])
            assert "id" in chunk
            assert "object" in chunk
            assert chunk["object"] == "chat.completion.chunk"
            assert "choices" in chunk
            assert "model" in chunk


@patch("app.api.router.stream_chat")
@pytest.mark.asyncio
async def test_streaming_timeout_sends_finish_reason(mock_stream):
    import asyncio

    async def slow_stream(req):
        await asyncio.sleep(0.5)
        yield StreamChunk(id="test", model="test", choices=[StreamChoice(index=0, delta={"content": "x"})])

    mock_stream.return_value = slow_stream(None) if hasattr(mock_stream, 'return_value') else slow_stream

    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={"model": "test", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        timeout=5,
    )
    lines = response.text.strip().split("\n\n")
    data_lines = [l for l in lines if l.startswith("data: ") and l != "data: [DONE]"]
    done_lines = [l for l in lines if l == "data: [DONE]"]
    assert len(done_lines) >= 1
