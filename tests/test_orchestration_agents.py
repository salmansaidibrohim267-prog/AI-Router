import pytest

from app.orchestration.agents import (
    AgentRegistry,
    BaseAgent,
    ChatAgent,
    CodingAgent,
    ArchitectureAgent,
    AnalysisAgent,
    ReviewerAgent,
    PlannerAgent,
)
from app.orchestration.memory import ExecutionMemory
from app.orchestration.models import PlanStep


class TestAgentRegistry:
    def test_registry_has_default_agents(self):
        registry = AgentRegistry()
        names = registry.get_all_names()
        assert "chat" in names
        assert "coder" in names
        assert "architect" in names
        assert "analyst" in names
        assert "reviewer" in names
        assert "planner" in names

    def test_get_agent(self):
        registry = AgentRegistry()
        agent = registry.get("chat")
        assert agent is not None
        assert agent.name == "chat"

    def test_get_nonexistent_agent(self):
        registry = AgentRegistry()
        agent = registry.get("nonexistent")
        assert agent is None

    def test_register_custom_agent(self):
        class CustomAgent(BaseAgent):
            name = "custom"
            specialty = "custom"
            async def execute(self, step, memory, router, request=None):
                from app.orchestration.models import AgentResult
                return AgentResult(agent="custom", step=step.step, content="done")

        registry = AgentRegistry()
        registry.register(CustomAgent)
        assert "custom" in registry.get_all_names()
        agent = registry.get("custom")
        assert agent is not None

    def test_create_agent_with_config(self):
        registry = AgentRegistry()
        agent = registry.create_agent("chat", {"custom_key": "value"})
        assert agent is not None
        assert agent._config == {"custom_key": "value"}


class TestAgentProperties:
    def test_chat_agent_properties(self):
        agent = ChatAgent()
        assert agent.name == "chat"
        assert agent.specialty == "general"
        assert agent.prompt_strategy == "direct"

    def test_coding_agent_properties(self):
        agent = CodingAgent()
        assert agent.name == "coder"
        assert agent.specialty == "coding"
        assert "anthropic" in agent.preferred_providers

    def test_architecture_agent_properties(self):
        agent = ArchitectureAgent()
        assert agent.name == "architect"
        assert agent.specialty == "architecture"

    def test_analysis_agent_properties(self):
        agent = AnalysisAgent()
        assert agent.name == "analyst"
        assert agent.specialty == "analysis"

    def test_reviewer_agent_properties(self):
        agent = ReviewerAgent()
        assert agent.name == "reviewer"
        assert agent.specialty == "review"

    def test_planner_agent_properties(self):
        agent = PlannerAgent()
        assert agent.name == "planner"
        assert agent.specialty == "planning"


class TestAgentBuildRequest:
    def test_build_request_from_prompt(self):
        agent = ChatAgent()
        step = PlanStep(step="test", agent="chat", prompt_template="Hello")
        memory = ExecutionMemory()
        prompt = agent.build_prompt(step, memory)
        assert prompt == "Hello"

    def test_build_request_with_context(self):
        agent = ChatAgent()
        step = PlanStep(
            step="test", agent="chat",
            prompt_template="Continue",
            context_refs=["previous"],
        )
        memory = ExecutionMemory()
        memory.set("last_output", "Previous output")
        prompt = agent.build_prompt(step, memory)
        assert "Previous output" in prompt
        assert "Continue" in prompt

    def test_build_request_no_context_refs(self):
        agent = ChatAgent()
        step = PlanStep(step="test", agent="chat", prompt_template="Hi")
        memory = ExecutionMemory()
        memory.set("last_output", "Should not appear")
        prompt = agent.build_prompt(step, memory)
        assert prompt == "Hi"
