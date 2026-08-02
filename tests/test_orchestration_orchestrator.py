import pytest
from unittest.mock import AsyncMock, patch

from app.orchestration.orchestrator import Orchestrator
from app.orchestration.models import (
    AgentResult,
    DebateResult,
    ConsensusResult,
    ExecutionPlan,
    OrchestrationRequest,
    OrchestrationResponse,
    PlanStep,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowNodeType,
    WorkflowResult,
)


class FakeChatRouter:
    async def chat(self, request):
        from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
        return ChatResponse(
            id="fake", model="test",
            choices=[ChatChoice(index=0, message=Message(role=MessageRole.ASSISTANT, content="fake response"), finish_reason="stop")],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def stream_chat(self, request):
        from app.models import StreamChunk, StreamChoice
        yield StreamChunk(id="s1", model="test", choices=[StreamChoice(index=0, delta={"content": "chunk "})])
        yield StreamChunk(id="s1", model="test", choices=[StreamChoice(index=0, delta={"content": "data"})])
        yield StreamChunk(id="s1", model="test", choices=[StreamChoice(index=0, delta={}, finish_reason="stop")])


class TestOrchestratorSingle:
    def setup_method(self):
        self.orchestrator = Orchestrator({}, router=FakeChatRouter())

    async def test_single_chat_mode(self):
        req = OrchestrationRequest(prompt="Hello", mode="single")
        resp = await self.orchestrator.orchestrate(req)
        assert isinstance(resp, OrchestrationResponse)
        assert resp.mode == "single"

    async def test_single_with_agent(self):
        req = OrchestrationRequest(prompt="Write code", agents=["coder"], mode="single")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "single"

    async def test_single_with_reflection(self):
        req = OrchestrationRequest(prompt="Test", mode="single", reflection=True)
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "single"

    async def test_single_with_messages(self):
        req = OrchestrationRequest(messages=[{"role": "user", "content": "Hello"}], mode="single")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "single"

    async def test_single_returns_plan(self):
        req = OrchestrationRequest(prompt="Hello", mode="single")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.plan is not None
        assert len(resp.plan.steps) >= 1


class TestOrchestratorMulti:
    def setup_method(self):
        self.orchestrator = Orchestrator({}, router=FakeChatRouter())

    async def test_multi_sequential(self):
        req = OrchestrationRequest(prompt="Build a web app", agents=["architect", "coder"], mode="multi", parallel=False)
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "multi"
        assert resp.plan is not None
        assert len(resp.plan.steps) == 2

    async def test_multi_parallel(self):
        req = OrchestrationRequest(prompt="Analyze and code", agents=["analyst", "coder"], mode="multi", parallel=True)
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "multi"

    async def test_multi_with_reflection(self):
        req = OrchestrationRequest(prompt="Review this", agents=["coder", "reviewer"], mode="multi", reflection=True)
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "multi"


class TestOrchestratorConsensus:
    def setup_method(self):
        self.orchestrator = Orchestrator({}, router=FakeChatRouter())

    async def test_consensus_first_success(self):
        req = OrchestrationRequest(prompt="Hello", mode="consensus", consensus_providers=["openai"], consensus_strategy="first_success")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "consensus"

    async def test_consensus_default_providers(self):
        req = OrchestrationRequest(prompt="Hello", mode="consensus")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "consensus"

    async def test_consensus_best_latency(self):
        req = OrchestrationRequest(prompt="Hello", mode="consensus", consensus_providers=["openai", "anthropic"], consensus_strategy="best_latency")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "consensus"

    async def test_consensus_flag(self):
        req = OrchestrationRequest(prompt="Hello", mode="single", consensus=True, consensus_providers=["openai"])
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "consensus"


class TestOrchestratorDebate:
    def setup_method(self):
        self.orchestrator = Orchestrator({}, router=FakeChatRouter())

    async def test_debate_basic(self):
        req = OrchestrationRequest(prompt="Debate topic", mode="debate", debate_provider_a="openai", debate_provider_b="anthropic")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "debate"

    async def test_debate_default_providers(self):
        req = OrchestrationRequest(prompt="Debate topic", mode="debate")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "debate"

    async def test_debate_flag(self):
        req = OrchestrationRequest(prompt="Debate topic", mode="single", debate=True)
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "debate"


class TestOrchestratorWorkflow:
    def setup_method(self):
        self.orchestrator = Orchestrator({}, router=FakeChatRouter())

    async def test_workflow_simple(self):
        workflow = WorkflowDefinition(
            id="test-wf",
            steps=[WorkflowStep(id="s1", type=WorkflowNodeType.TASK, agent="chat", prompt="Hello")],
        )
        req = OrchestrationRequest(mode="workflow", workflow=workflow)
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "workflow"

    async def test_workflow_empty(self):
        req = OrchestrationRequest(mode="workflow")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "workflow"

    async def test_workflow_multi_step(self):
        workflow = WorkflowDefinition(
            id="test-wf2",
            steps=[
                WorkflowStep(id="s1", type=WorkflowNodeType.TASK, agent="chat", prompt="First"),
                WorkflowStep(id="s2", type=WorkflowNodeType.TASK, agent="chat", prompt="Second"),
            ],
        )
        req = OrchestrationRequest(mode="workflow", workflow=workflow)
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "workflow"


class TestOrchestratorConfig:
    async def test_loads_yaml_config(self):
        orch = Orchestrator(router=FakeChatRouter())
        assert orch._config is not None

    async def test_empty_config(self):
        orch = Orchestrator({}, router=FakeChatRouter())
        assert orch._config == {}

    async def test_config_overrides(self):
        orch = Orchestrator({"reflection": {"threshold": 0.9, "max_retries": 5}})
        assert orch.reflection._threshold == 0.9
        assert orch.reflection._max_retries == 5


class TestOrchestratorErrors:
    def setup_method(self):
        self.orchestrator = Orchestrator({}, router=FakeChatRouter())

    async def test_invalid_mode_falls_back_to_single(self):
        req = OrchestrationRequest(prompt="Hello", mode="invalid_mode")
        resp = await self.orchestrator.orchestrate(req)
        assert resp.mode == "invalid_mode"
