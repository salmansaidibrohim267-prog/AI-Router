from __future__ import annotations

from typing import Any

from app.orchestration.models import (
    PlanStep,
    WorkflowDefinition,
    WorkflowNodeType,
    WorkflowStep,
)


class WorkflowBuilder:
    def __init__(self, workflow_id: str = ""):
        self._steps: list[WorkflowStep] = []
        self._workflow_id = workflow_id

    def task(self, step_id: str, agent: str, prompt: str, **kwargs: Any) -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.TASK,
                agent=agent,
                prompt=prompt,
                **kwargs,
            )
        )
        return self

    def if_condition(self, step_id: str, condition: str, steps: list[WorkflowStep]) -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.IF,
                condition=condition,
                steps=steps,
            )
        )
        return self

    def else_branch(self, step_id: str, steps: list[WorkflowStep]) -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.ELSE,
                steps=steps,
            )
        )
        return self

    def for_loop(self, step_id: str, collection: str, variable: str, steps: list[WorkflowStep]) -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.FOR,
                collection=collection,
                variable=variable,
                steps=steps,
            )
        )
        return self

    def parallel(self, step_id: str, steps: list[WorkflowStep]) -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.PARALLEL,
                steps=steps,
            )
        )
        return self

    def wait(self, step_id: str, duration: str = "1") -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.WAIT,
                prompt=duration,
            )
        )
        return self

    def retry(self, step_id: str, retry_count: int, steps: list[WorkflowStep]) -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.RETRY,
                retry_count=retry_count,
                steps=steps,
            )
        )
        return self

    def timeout(self, step_id: str, timeout: int, steps: list[WorkflowStep]) -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.TIMEOUT,
                timeout=timeout,
                steps=steps,
            )
        )
        return self

    def merge(self, step_id: str, strategy: str = "concat") -> WorkflowBuilder:
        self._steps.append(
            WorkflowStep(
                id=step_id,
                type=WorkflowNodeType.MERGE,
                merge_strategy=strategy,
            )
        )
        return self

    def build(self) -> WorkflowDefinition:
        return WorkflowDefinition(
            id=self._workflow_id,
            steps=self._steps,
        )

    def to_plan_steps(self) -> list[PlanStep]:
        return [
            PlanStep(
                step=s.id,
                agent=s.agent,
                prompt_template=s.prompt,
                timeout=s.timeout,
                retry_count=s.retry_count,
            )
            for s in self._steps
            if s.type == WorkflowNodeType.TASK
        ]
