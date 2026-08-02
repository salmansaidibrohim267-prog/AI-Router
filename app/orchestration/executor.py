from __future__ import annotations

import asyncio
import time
from typing import Any

from app.orchestration.agents import AgentRegistry, BaseAgent, ChatAgent
from app.orchestration.dag import DAGExecutor, WorkflowDAG
from app.orchestration.memory import ExecutionMemory
from app.orchestration.models import (
    AgentResult,
    ExecutionPlan,
    PlanStep,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStep,
    WorkflowNodeType,
)
from app.orchestration.metrics import (
    execution_latency_seconds,
    agent_latency_seconds,
)
from app.router import AIRouter
from app.models import ChatRequest


class ExecutionError(Exception):
    pass


class ExecutionEngine:
    def __init__(self, agent_registry: AgentRegistry | None = None):
        self._agent_registry = agent_registry or AgentRegistry()
        self._dag_executor = DAGExecutor(self._agent_registry)

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        router: AIRouter,
        request: ChatRequest | None = None,
        memory: ExecutionMemory | None = None,
    ) -> list[AgentResult]:
        if memory is None:
            memory = ExecutionMemory()
        memory.update(plan.context)

        results: list[AgentResult] = []
        start = time.perf_counter()

        if not plan.steps:
            return results

        is_parallel = all(s.execution == "parallel" for s in plan.steps)

        if is_parallel and len(plan.steps) > 1:
            results = await self._execute_parallel(plan.steps, router, request, memory)
        else:
            results = await self._execute_sequential(plan.steps, router, request, memory)

        latency = time.perf_counter() - start
        execution_latency_seconds.labels(mode="parallel" if is_parallel else "sequential").observe(latency)
        return results

    async def _execute_sequential(
        self,
        steps: list[PlanStep],
        router: AIRouter,
        request: ChatRequest | None,
        memory: ExecutionMemory,
    ) -> list[AgentResult]:
        results: list[AgentResult] = []
        for step in steps:
            result = await self._execute_step(step, router, request, memory)
            results.append(result)
            if not result.success:
                break
            memory.set("last_output", result.content)
            memory.set(f"step_{step.step}", result.content)
        return results

    async def _execute_parallel(
        self,
        steps: list[PlanStep],
        router: AIRouter,
        request: ChatRequest | None,
        memory: ExecutionMemory,
    ) -> list[AgentResult]:
        async def run_step(step: PlanStep) -> AgentResult:
            step_result = await self._execute_step(step, router, request, memory)
            return step_result

        tasks = [run_step(s) for s in steps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final: list[AgentResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final.append(AgentResult(
                    agent=steps[i].agent,
                    step=steps[i].step,
                    content="",
                    success=False,
                    error=str(result),
                ))
            else:
                final.append(result)
                memory.set("last_output", result.content)
                memory.set(f"step_{steps[i].step}", result.content)
        return final

    async def _execute_step(
        self,
        step: PlanStep,
        router: AIRouter,
        request: ChatRequest | None,
        memory: ExecutionMemory,
    ) -> AgentResult:
        agent = self._agent_registry.get(step.agent)
        if not agent:
            return AgentResult(
                agent=step.agent,
                step=step.step,
                content="",
                success=False,
                error=f"Unknown agent: {step.agent}",
            )

        start = time.perf_counter()
        try:
            prompt = memory.resolve_refs(step.prompt_template)
            step.prompt_template = prompt
            result = await asyncio.wait_for(
                agent.execute(step, memory, router, request),
                timeout=step.timeout,
            )
        except asyncio.TimeoutError:
            latency = time.perf_counter() - start
            agent_latency_seconds.labels(agent=step.agent).observe(latency)
            return AgentResult(
                agent=step.agent,
                step=step.step,
                content="",
                success=False,
                error=f"Agent execution timed out after {step.timeout}s",
            )
        except Exception as e:
            latency = time.perf_counter() - start
            agent_latency_seconds.labels(agent=step.agent).observe(latency)
            return AgentResult(
                agent=step.agent,
                step=step.step,
                content="",
                success=False,
                error=str(e),
            )

        latency = time.perf_counter() - start
        agent_latency_seconds.labels(agent=step.agent).observe(latency)
        return result

    async def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        router: AIRouter,
        request: ChatRequest | None = None,
        memory: ExecutionMemory | None = None,
        timeline: list[dict[str, Any]] | None = None,
    ) -> WorkflowResult:
        if memory is None:
            memory = ExecutionMemory()
        memory.update(workflow.context)

        has_deps = any(s.depends_on for s in workflow.steps)
        if has_deps:
            return await self._dag_executor.execute(workflow, router, request, memory, timeline)

        outputs: dict[str, Any] = {}
        start = time.perf_counter()

        try:
            await self._execute_workflow_steps(
                workflow.steps, router, request, memory, outputs
            )
        except Exception as e:
            return WorkflowResult(
                workflow_id=workflow.id,
                outputs=outputs,
                success=False,
                error=str(e),
            )

        latency = time.perf_counter() - start
        execution_latency_seconds.labels(mode="workflow").observe(latency)
        return WorkflowResult(workflow_id=workflow.id, outputs=outputs, success=True)

    async def _execute_workflow_steps(
        self,
        steps: list[WorkflowStep],
        router: AIRouter,
        request: ChatRequest | None,
        memory: ExecutionMemory,
        outputs: dict[str, Any],
    ) -> None:
        i = 0
        while i < len(steps):
            step = steps[i]
            wf_step = WorkflowStep(id=step.id, type=WorkflowNodeType.TASK)

            if step.type == WorkflowNodeType.TASK:
                result = await self._execute_workflow_task(step, router, request, memory)
                outputs[step.id] = result.content if hasattr(result, 'content') else str(result)

            elif step.type == WorkflowNodeType.IF:
                condition_met = self._evaluate_condition(step.condition, memory)
                if condition_met:
                    await self._execute_workflow_steps(step.steps or [], router, request, memory, outputs)
                else:
                    i += 1
                    while i < len(steps) and steps[i].type != WorkflowNodeType.ELSE:
                        i += 1
                    if i < len(steps) and steps[i].type == WorkflowNodeType.ELSE:
                        await self._execute_workflow_steps(steps[i].steps or [], router, request, memory, outputs)

            elif step.type == WorkflowNodeType.ELSE:
                pass

            elif step.type == WorkflowNodeType.FOR:
                collection = memory.get(step.collection, [])
                for item in collection:
                    memory.set(step.variable, item)
                    await self._execute_workflow_steps(step.steps or [], router, request, memory, outputs)

            elif step.type == WorkflowNodeType.PARALLEL:
                tasks = [
                    self._execute_workflow_steps([sub], router, request, memory, outputs)
                    for sub in (step.steps or [])
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

            elif step.type == WorkflowNodeType.WAIT:
                try:
                    duration = float(step.prompt or "1")
                    await asyncio.sleep(duration)
                except (ValueError, TypeError):
                    await asyncio.sleep(1)

            elif step.type == WorkflowNodeType.RETRY:
                max_attempts = max(step.retry_count, 1)
                for attempt in range(max_attempts):
                    try:
                        sub_result = await self._execute_workflow_steps(
                            step.steps or [], router, request, memory, outputs
                        )
                        break
                    except Exception:
                        if attempt == max_attempts - 1:
                            raise

            elif step.type == WorkflowNodeType.TIMEOUT:
                try:
                    sub_steps = step.steps or []
                    await asyncio.wait_for(
                        self._execute_workflow_steps(sub_steps, router, request, memory, outputs),
                        timeout=max(step.timeout, 1),
                    )
                except asyncio.TimeoutError:
                    pass

            elif step.type == WorkflowNodeType.MERGE:
                merged = self._merge_outputs(outputs, step.merge_strategy)
                outputs[step.id] = merged

            i += 1

    async def _execute_workflow_task(
        self,
        step: WorkflowStep,
        router: AIRouter,
        request: ChatRequest | None,
        memory: ExecutionMemory,
    ) -> AgentResult:
        if not step.agent:
            step.agent = "chat"
        agent = self._agent_registry.get(step.agent)
        if not agent:
            return AgentResult(
                agent=step.agent,
                step=step.id,
                content="",
                success=False,
                error=f"Unknown workflow agent: {step.agent}",
            )
        plan_step = PlanStep(
            step=step.id,
            agent=step.agent,
            prompt_template=memory.resolve_refs(step.prompt),
            timeout=step.timeout,
            retry_count=step.retry_count,
        )
        return await agent.execute(plan_step, memory, router, request)

    def _evaluate_condition(self, condition: str, memory: ExecutionMemory) -> bool:
        if not condition:
            return True
        resolved = memory.resolve_refs(condition)
        try:
            return bool(eval(resolved, {"__builtins__": {}}, {"memory": memory, "len": len, "str": str, "int": int, "float": float, "bool": bool, "dict": dict, "list": list}))
        except Exception:
            return bool(resolved) if resolved else False

    def _merge_outputs(self, outputs: dict[str, Any], strategy: str = "concat") -> str:
        values = [str(v) for v in outputs.values() if v]
        if strategy == "concat":
            return "\n\n".join(values)
        elif strategy == "first":
            return values[0] if values else ""
        elif strategy == "last":
            return values[-1] if values else ""
        return "\n\n".join(values)
