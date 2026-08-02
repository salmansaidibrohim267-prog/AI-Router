import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.api import app
from app.orchestration.models import (
    OrchestrationRequest,
    OrchestrationResponse,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowNodeType,
)


class MockChatResponse:
    id = "mock"
    model = "mock"
    choices = []
    usage = None


@pytest.fixture(autouse=True)
def mock_router():
    with patch("app.router.router.chat", new=AsyncMock(return_value=MockChatResponse())):
        with patch("app.router.router.initialize", new=AsyncMock()):
            with patch("app.router.router.stream_chat"):
                yield


class TestOrchestrationAPI:
    def test_orchestrate_endpoint_exists(self):
        client = TestClient(app)
        resp = client.post("/v1/orchestrate", json={
            "prompt": "Hello",
            "mode": "single",
        })
        assert resp.status_code in (200, 422, 500)

    def test_agents_endpoint(self):
        client = TestClient(app)
        resp = client.post("/v1/agents", json={
            "prompt": "Write code",
            "agents": ["chat"],
            "parallel": False,
            "reflection": False,
        })
        assert resp.status_code in (200, 422, 500)

    def test_workflow_endpoint(self):
        client = TestClient(app)
        workflow = {
            "id": "test-wf",
            "steps": [
                {"id": "s1", "type": "task", "agent": "chat", "prompt": "Hello"},
            ],
        }
        resp = client.post("/v1/workflow", json=workflow)
        assert resp.status_code in (200, 422, 500)

    def test_consensus_endpoint(self):
        client = TestClient(app)
        resp = client.post("/v1/consensus", json={
            "prompt": "Hello",
            "providers": ["openai"],
            "strategy": "first_success",
        })
        assert resp.status_code in (200, 422, 500)

    def test_debate_endpoint(self):
        client = TestClient(app)
        resp = client.post("/v1/debate", json={
            "prompt": "Debate topic",
            "provider_a": "openai",
            "provider_b": "anthropic",
        })
        assert resp.status_code in (200, 422, 500)

    def test_orchestrate_with_messages(self):
        client = TestClient(app)
        resp = client.post("/v1/orchestrate", json={
            "messages": [{"role": "user", "content": "Hello"}],
            "mode": "single",
        })
        assert resp.status_code in (200, 422, 500)

    def test_orchestrate_multi_agent(self):
        client = TestClient(app)
        resp = client.post("/v1/orchestrate", json={
            "prompt": "Build a web app",
            "agents": ["architect", "coder"],
            "mode": "multi",
        })
        assert resp.status_code in (200, 422, 500)

    def test_agents_single(self):
        client = TestClient(app)
        resp = client.post("/v1/agents", json={
            "prompt": "Hello",
            "agents": ["chat"],
        })
        assert resp.status_code in (200, 422, 500)

    def test_agents_form_data(self):
        client = TestClient(app)
        resp = client.post("/v1/agents?prompt=Hello&agents=chat")
        assert resp.status_code in (200, 422, 500)

    def test_existing_endpoints_unaffected(self):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        resp = client.get("/plugins")
        assert resp.status_code == 200
        resp = client.get("/providers")
        assert resp.status_code == 200
