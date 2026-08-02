from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.orchestration.models import AgentResult, PlanStep
from app.orchestration.memory import ExecutionMemory
from app.router import AIRouter
from app.models import ChatRequest, ChatResponse, Message, MessageRole


class BaseAgent(ABC):
    name: str = "base"
    specialty: str = ""
    preferred_providers: list[str] = []
    prompt_strategy: str = "direct"

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}

    @abstractmethod
    async def execute(
        self,
        step: PlanStep,
        memory: ExecutionMemory,
        router: AIRouter,
        request: ChatRequest | None = None,
    ) -> AgentResult:
        ...

    def build_prompt(self, step: PlanStep, memory: ExecutionMemory) -> str:
        prompt = step.prompt_template
        if memory:
            previous = memory.get("last_output", "")
            if previous and step.context_refs:
                prompt = f"Previous output:\n{previous}\n\n{prompt}"
        return prompt

    def build_request(self, prompt: str, original: ChatRequest | None = None) -> ChatRequest:
        if original:
            req = original.model_copy()
            req.messages = [Message(role=MessageRole.USER, content=prompt)]
            return req
        return ChatRequest(
            messages=[Message(role=MessageRole.USER, content=prompt)],
            model=original.model if original else "",
        )


class PlannerAgent(BaseAgent):
    name = "planner"
    specialty = "planning"
    preferred_providers = ["openai", "anthropic"]
    prompt_strategy = "structured"

    async def execute(
        self,
        step: PlanStep,
        memory: ExecutionMemory,
        router: AIRouter,
        request: ChatRequest | None = None,
    ) -> AgentResult:
        agent_prompt = (
            "You are a planning agent. Break down the following request into steps.\n"
            "Return a numbered list of steps in order.\n\n"
            f"{step.prompt_template}"
        )
        req = self.build_request(agent_prompt, request)
        response = await router.chat(req)
        content = response.choices[0].message.content if response.choices else ""
        memory.set("plan", content)
        return AgentResult(
            agent=self.name,
            step=step.step,
            content=content,
            provider=getattr(response, "provider", ""),
            model=getattr(response, "model", ""),
        )


class CodingAgent(BaseAgent):
    name = "coder"
    specialty = "coding"
    preferred_providers = ["anthropic", "openai"]
    prompt_strategy = "code"

    async def execute(
        self,
        step: PlanStep,
        memory: ExecutionMemory,
        router: AIRouter,
        request: ChatRequest | None = None,
    ) -> AgentResult:
        agent_prompt = (
            "You are a coding agent. Write production-ready code.\n"
            "Include type hints, docstrings, and error handling.\n\n"
            f"{step.prompt_template}"
        )
        req = self.build_request(agent_prompt, request)
        response = await router.chat(req)
        content = response.choices[0].message.content if response.choices else ""
        memory.set("code_output", content)
        return AgentResult(
            agent=self.name,
            step=step.step,
            content=content,
            provider=getattr(response, "provider", ""),
            model=getattr(response, "model", ""),
        )


class ArchitectureAgent(BaseAgent):
    name = "architect"
    specialty = "architecture"
    preferred_providers = ["openai", "anthropic"]
    prompt_strategy = "structured"

    async def execute(
        self,
        step: PlanStep,
        memory: ExecutionMemory,
        router: AIRouter,
        request: ChatRequest | None = None,
    ) -> AgentResult:
        agent_prompt = (
            "You are an architecture agent. Design system architecture.\n"
            "Include components, data flow, and technology choices.\n\n"
            f"{step.prompt_template}"
        )
        req = self.build_request(agent_prompt, request)
        response = await router.chat(req)
        content = response.choices[0].message.content if response.choices else ""
        memory.set("architecture_output", content)
        return AgentResult(
            agent=self.name,
            step=step.step,
            content=content,
            provider=getattr(response, "provider", ""),
            model=getattr(response, "model", ""),
        )


class AnalysisAgent(BaseAgent):
    name = "analyst"
    specialty = "analysis"
    preferred_providers = ["openai", "anthropic", "google"]
    prompt_strategy = "analytical"

    async def execute(
        self,
        step: PlanStep,
        memory: ExecutionMemory,
        router: AIRouter,
        request: ChatRequest | None = None,
    ) -> AgentResult:
        agent_prompt = (
            "You are an analysis agent. Analyze thoroughly.\n"
            "Provide data-driven insights with pros and cons.\n\n"
            f"{step.prompt_template}"
        )
        req = self.build_request(agent_prompt, request)
        response = await router.chat(req)
        content = response.choices[0].message.content if response.choices else ""
        memory.set("analysis_output", content)
        return AgentResult(
            agent=self.name,
            step=step.step,
            content=content,
            provider=getattr(response, "provider", ""),
            model=getattr(response, "model", ""),
        )


class ReviewerAgent(BaseAgent):
    name = "reviewer"
    specialty = "review"
    preferred_providers = ["openai", "anthropic"]
    prompt_strategy = "critical"

    async def execute(
        self,
        step: PlanStep,
        memory: ExecutionMemory,
        router: AIRouter,
        request: ChatRequest | None = None,
    ) -> AgentResult:
        previous = memory.get("last_output", "")
        agent_prompt = (
            "You are a reviewer agent. Review the following output critically.\n"
            "Check for correctness, security issues, and improvements.\n"
            f"Output to review:\n{previous}\n\n"
            f"{step.prompt_template}"
        )
        req = self.build_request(agent_prompt, request)
        response = await router.chat(req)
        content = response.choices[0].message.content if response.choices else ""
        memory.set("review_output", content)
        return AgentResult(
            agent=self.name,
            step=step.step,
            content=content,
            provider=getattr(response, "provider", ""),
            model=getattr(response, "model", ""),
        )


class ChatAgent(BaseAgent):
    name = "chat"
    specialty = "general"
    preferred_providers: list[str] = []
    prompt_strategy = "direct"

    async def execute(
        self,
        step: PlanStep,
        memory: ExecutionMemory,
        router: AIRouter,
        request: ChatRequest | None = None,
    ) -> AgentResult:
        if request:
            response = await router.chat(request)
        else:
            req = self.build_request(step.prompt_template, request)
            response = await router.chat(req)
        content = response.choices[0].message.content if response.choices else ""
        memory.set("last_output", content)
        return AgentResult(
            agent=self.name,
            step=step.step,
            content=content,
            provider=getattr(response, "provider", ""),
            model=getattr(response, "model", ""),
        )


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, type[BaseAgent]] = {}
        self.register(PlannerAgent)
        self.register(CodingAgent)
        self.register(ArchitectureAgent)
        self.register(AnalysisAgent)
        self.register(ReviewerAgent)
        self.register(ChatAgent)

    def register(self, agent_class: type[BaseAgent]) -> None:
        instance = agent_class()
        self._agents[instance.name] = agent_class

    def get(self, name: str) -> BaseAgent | None:
        cls = self._agents.get(name)
        if cls:
            return cls()
        return None

    def get_all_names(self) -> list[str]:
        return list(self._agents.keys())

    def create_agent(self, name: str, config: dict[str, Any] | None = None) -> BaseAgent | None:
        cls = self._agents.get(name)
        if cls:
            return cls(config)
        return None


_agent_registry = AgentRegistry()

coding_agent = CodingAgent
architecture_agent = ArchitectureAgent
analysis_agent = AnalysisAgent
chat_agent = ChatAgent
planner_agent = PlannerAgent
reviewer_agent = ReviewerAgent
