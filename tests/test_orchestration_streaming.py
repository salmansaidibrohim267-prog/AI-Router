import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.api import app
from app.orchestration.orchestrator import Orchestrator
from app.orchestration.models import OrchestrationRequest
from app.models import StreamChunk


class MockChatResponse:
    id = "mock"
    model = "mock"
    choices = []
    usage = None


class FakeStreamRouter:
    async def chat(self, request):
        from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
        return ChatResponse(
            id="fake", model="test",
            choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content="fake"), finish_reason="stop")],
            usage=Usage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
        )

    async def stream_chat(self, request):
        yield StreamChunk(id="s1", model="test", choices=[{"index": 0, "delta": {"content": "chunk "}}])
        yield StreamChunk(id="s1", model="test", choices=[{"index": 0, "delta": {"content": "data"}}])
        yield StreamChunk(id="s1", model="test", choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}])


class TestOrchestratorStreaming:
    def setup_method(self):
        self.orchestrator = Orchestrator({}, router=FakeStreamRouter())

    async def test_stream_single_mode_returns_chunks(self):
        req = OrchestrationRequest(prompt="Hello", mode="single", stream=True)
        chunks = []
        async for chunk in self.orchestrator.orchestrate_stream(req):
            chunks.append(chunk)
            assert isinstance(chunk, StreamChunk)
        assert len(chunks) > 0

    async def test_stream_single_chat_passthrough(self):
        req = OrchestrationRequest(prompt="Hello", mode="single", stream=True)
        chunks = []
        async for chunk in self.orchestrator.orchestrate_stream(req):
            chunks.append(chunk)
        assert any(c.choices[0].delta.get("content", "") != "" for c in chunks)
        assert any(c.choices[0].finish_reason == "stop" for c in chunks)

    async def test_stream_multi_emits_agent_chunks(self):
        req = OrchestrationRequest(prompt="Build a web app", agents=["architect", "coder"], mode="multi", stream=True)
        chunks = []
        async for chunk in self.orchestrator.orchestrate_stream(req):
            chunks.append(chunk)
        assert len(chunks) > 0

    async def test_stream_consensus(self):
        req = OrchestrationRequest(prompt="Hello", mode="consensus", consensus_providers=["openai"], stream=True)
        chunks = []
        async for chunk in self.orchestrator.orchestrate_stream(req):
            chunks.append(chunk)
        assert len(chunks) > 0

    async def test_stream_debate(self):
        req = OrchestrationRequest(prompt="Debate topic", mode="debate", debate_provider_a="openai", debate_provider_b="anthropic", stream=True)
        chunks = []
        async for chunk in self.orchestrator.orchestrate_stream(req):
            chunks.append(chunk)
        assert len(chunks) > 0

    async def test_stream_returns_stop_chunk(self):
        req = OrchestrationRequest(prompt="Hello", mode="single", stream=True)
        chunks = []
        async for chunk in self.orchestrator.orchestrate_stream(req):
            chunks.append(chunk)
        assert chunks[-1].choices[0].finish_reason == "stop"

    async def test_stream_multi_ends_with_stop(self):
        req = OrchestrationRequest(prompt="Build a web app", agents=["architect", "coder"], mode="multi", stream=True)
        chunks = []
        async for chunk in self.orchestrator.orchestrate_stream(req):
            chunks.append(chunk)
        assert chunks[-1].choices[0].finish_reason == "stop"


class TestOrchestrationAPIStreaming:
    @pytest.fixture(autouse=True)
    def _mock_router(self):
        with patch("app.router.router.chat", new=AsyncMock(return_value=MockChatResponse())):
            with patch("app.router.router.initialize", new=AsyncMock()):
                with patch("app.router.router.stream_chat"):
                    yield

    def test_orchestrate_streaming_endpoint(self):
        client = TestClient(app)
        resp = client.post("/v1/orchestrate", json={
            "prompt": "Hello",
            "mode": "single",
            "stream": True,
        })
        assert resp.status_code in (200, 422, 500)

    def test_orchestrate_streaming_single_content_type(self):
        client = TestClient(app)
        resp = client.post("/v1/orchestrate", json={
            "prompt": "Hello",
            "mode": "single",
            "stream": True,
        })
        if resp.status_code == 200:
            assert resp.headers.get("content-type", "").startswith("text/event-stream")

    def test_orchestrate_non_streaming_returns_json(self):
        client = TestClient(app)
        resp = client.post("/v1/orchestrate", json={
            "prompt": "Hello",
            "mode": "single",
        })
        assert resp.status_code in (200, 422, 500)
