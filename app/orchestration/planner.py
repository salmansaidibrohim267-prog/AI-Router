from __future__ import annotations

import uuid
from typing import Any

from app.orchestration.models import (
    ExecutionPlan,
    PlanStep,
)


class Planner:
    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}
        self._default_agent_map: dict[str, str] = {
            "coding": "coder",
            "code": "coder",
            "programming": "coder",
            "architecture": "architect",
            "design": "architect",
            "system": "architect",
            "analysis": "analyst",
            "analyze": "analyst",
            "research": "analyst",
            "review": "reviewer",
            "refactor": "reviewer",
            "chat": "chat",
            "talk": "chat",
            "plan": "planner",
        }

    def create_plan(self, prompt: str, agents: list[str] | None = None, parallel: bool = False) -> ExecutionPlan:
        plan_id = uuid.uuid4().hex[:12]
        if agents:
            steps = self._plan_from_agents(prompt, agents, parallel)
        else:
            steps = self._plan_from_prompt(prompt)
        return ExecutionPlan(steps=steps, plan_id=plan_id)

    def create_single_plan(self, prompt: str, agent: str = "chat") -> ExecutionPlan:
        plan_id = uuid.uuid4().hex[:12]
        step = PlanStep(
            step="single",
            agent=agent,
            execution="sequential",
            prompt_template=prompt,
        )
        return ExecutionPlan(steps=[step], plan_id=plan_id)

    def create_multi_plan(self, prompt: str, agents: list[str], parallel: bool = False) -> ExecutionPlan:
        plan_id = uuid.uuid4().hex[:12]
        execution_mode = "parallel" if parallel else "sequential"
        steps = [
            PlanStep(
                step=f"step_{i}",
                agent=agent,
                execution=execution_mode,
                prompt_template=prompt,
            )
            for i, agent in enumerate(agents)
        ]
        if parallel:
            for step in steps:
                step.execution = "parallel"
            if len(steps) > 1:
                steps[-1].execution = "sequential"
        return ExecutionPlan(steps=steps, plan_id=plan_id)

    def _plan_from_agents(self, prompt: str, agents: list[str], parallel: bool) -> list[PlanStep]:
        if len(agents) == 1:
            return [PlanStep(step="single", agent=agents[0], prompt_template=prompt)]
        execution = "parallel" if parallel else "sequential"
        return [
            PlanStep(
                step=f"agent_{agent}",
                agent=agent,
                execution=execution,
                prompt_template=prompt,
            )
            for agent in agents
        ]

    def _plan_from_prompt(self, prompt: str) -> list[PlanStep]:
        text = prompt.lower()
        matched_agents: list[str] = []
        for keyword, agent in self._default_agent_map.items():
            if keyword in text and agent not in matched_agents:
                matched_agents.append(agent)
        if not matched_agents:
            matched_agents = ["chat"]
        if len(matched_agents) == 1:
            return [PlanStep(step="single", agent=matched_agents[0], prompt_template=prompt)]

        steps = []
        for i, agent in enumerate(matched_agents):
            steps.append(
                PlanStep(
                    step=f"step_{i + 1}",
                    agent=agent,
                    execution="sequential",
                    prompt_template=(
                        prompt
                        if i == len(matched_agents) - 1
                        else f"{prompt}\n\nFocus on this from a {agent} perspective."
                    ),  # noqa: E501
                    context_refs=[] if i == 0 else [f"step_{i}"],
                )
            )
        return steps

    def _classify_agent(self, prompt: str) -> str:
        text = prompt.lower()
        best_match = "chat"
        best_count = 0
        for keyword, agent in self._default_agent_map.items():
            count = text.count(keyword)
            if count > best_count:
                best_count = count
                best_match = agent
        return best_match
