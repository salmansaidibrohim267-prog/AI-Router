from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Any

from app.orchestration.agents import AgentRegistry
from app.orchestration.memory import ExecutionMemory
from app.orchestration.models import (
    AgentResult,
    PlanStep,
    WorkflowDefinition,
    WorkflowNodeType,
    WorkflowResult,
    WorkflowStep,
)
from app.orchestration.metrics import execution_latency_seconds, agent_latency_seconds
from app.router import AIRouter
from app.models import ChatRequest


class CycleError(Exception):
    pass


class WorkflowDAG:
    def __init__(self, steps: list[WorkflowStep]):
        self.steps = steps
        self._validate()

    def _validate(self) -> None:
        ids = {s.id for s in self.steps}
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in ids and dep != "START":
                    raise ValueError(f"Step '{s.id}' depends on unknown step '{dep}'")
        cycle = self._detect_cycle()
        if cycle:
            raise CycleError(f"Cycle detected in workflow DAG: {' -> '.join(cycle)}")

    def _detect_cycle(self) -> list[str]:
        graph = {s.id: list(s.depends_on) for s in self.steps}
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {s.id: WHITE for s in self.steps}
        parent = {}

        def dfs(node: str) -> list[str] | None:
            color[node] = GRAY
            for dep in graph.get(node, []):
                if dep == "START":
                    continue
                if color.get(dep) == GRAY:
                    cycle = [dep, node]
                    cur = node
                    while cur != dep:
                        cur = parent.get(cur, dep)
                        cycle.append(cur)
                    return cycle
                if color.get(dep) == WHITE:
                    parent[dep] = node
                    result = dfs(dep)
                    if result:
                        return result
            color[node] = BLACK
            return None

        for s in self.steps:
            if color[s.id] == WHITE:
                result = dfs(s.id)
                if result:
                    return result
        return []

    def topological_sort(self) -> list[list[WorkflowStep]]:
        in_degree: dict[str, int] = {}
        graph: dict[str, list[str]] = defaultdict(list)
        step_map = {s.id: s for s in self.steps}

        for s in self.steps:
            if s.id not in in_degree:
                in_degree[s.id] = 0
            for dep in s.depends_on:
                if dep == "START":
                    continue
                graph[dep].append(s.id)
                in_degree[s.id] = in_degree.get(s.id, 0) + 1

        levels: list[list[WorkflowStep]] = []
        queue = deque(
            [s.id for s in self.steps if in_degree.get(s.id, 0) == 0]
        )
        visited = set()

        while queue:
            level = []
            for _ in range(len(queue)):
                node_id = queue.popleft()
                if node_id in visited:
                    continue
                visited.add(node_id)
                level.append(step_map[node_id])
                for neighbor in graph.get(node_id, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            if level:
                levels.append(level)

        unvisited = [s.id for s in self.steps if s.id not in visited]
        if unvisited:
            levels.append([step_map[s] for s in unvisited])

        return levels

    def to_visualization_data(self) -> dict[str, Any]:
        nodes = []
        edges = []
        for s in self.steps:
            node_type = s.type.value if isinstance(s.type, WorkflowNodeType) else str(s.type)
            nodes.append({
                "id": s.id,
                "type": node_type,
                "agent": s.agent,
                "label": s.id or node_type,
            })
            for dep in s.depends_on:
                if dep != "START":
                    edges.append({"from": dep, "to": s.id})
        return {"nodes": nodes, "edges": edges, "steps": len(self.steps)}

    def get_levels(self) -> list[list[str]]:
        return [[s.id for s in level] for level in self.topological_sort()]


class DAGExecutor:
    def __init__(self, agent_registry: AgentRegistry | None = None):
        self._agent_registry = agent_registry or AgentRegistry()

    async def execute(
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

        outputs: dict[str, Any] = {}
        start = time.perf_counter()

        try:
            dag = WorkflowDAG(workflow.steps)
            levels = dag.topological_sort()

            for level in levels:
                if len(level) == 1:
                    step = level[0]
                    result = await self._execute_dag_step(step, router, request, memory, outputs, timeline)
                    if result is not None:
                        outputs[step.id] = result
                else:
                    tasks = [
                        self._execute_dag_step(s, router, request, memory, outputs, timeline)
                        for s in level
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, step in enumerate(level):
                        r = results[i]
                        if isinstance(r, Exception):
                            outputs[step.id] = f"Error: {r}"
                        elif r is not None:
                            outputs[step.id] = r

        except CycleError as e:
            return WorkflowResult(
                workflow_id=workflow.id,
                outputs=outputs,
                success=False,
                error=f"DAG cycle detected: {e}",
            )
        except Exception as e:
            return WorkflowResult(
                workflow_id=workflow.id,
                outputs=outputs,
                success=False,
                error=str(e),
            )

        latency = time.perf_counter() - start
        execution_latency_seconds.labels(mode="dag_workflow").observe(latency)
        return WorkflowResult(workflow_id=workflow.id, outputs=outputs, success=True)

    async def _execute_dag_step(
        self,
        step: WorkflowStep,
        router: AIRouter,
        request: ChatRequest | None,
        memory: ExecutionMemory,
        outputs: dict[str, Any],
        timeline: list[dict[str, Any]] | None = None,
    ) -> Any:
        step_start = time.perf_counter()

        if timeline is not None:
            timeline.append({
                "event": f"{step.id}_started",
                "step": step.id,
                "type": step.type.value,
                "timestamp": step_start,
            })

        try:
            if step.type == WorkflowNodeType.TASK:
                result = await self._execute_task(step, router, request, memory)
                return result.content if hasattr(result, "content") else str(result)

            elif step.type == WorkflowNodeType.CONDITIONAL:
                condition_met = self._evaluate_condition(step.condition, memory)
                if condition_met:
                    if step.steps:
                        inner_dag = WorkflowDAG(step.steps)
                        inner_levels = inner_dag.topological_sort()
                        for inner_level in inner_levels:
                            if len(inner_level) == 1:
                                inner_result = await self._execute_dag_step(
                                    inner_level[0], router, request, memory, outputs, timeline
                                )
                                if inner_result is not None:
                                    outputs[inner_level[0].id] = inner_result
                            else:
                                tasks = [
                                    self._execute_dag_step(s, router, request, memory, outputs, timeline)
                                    for s in inner_level
                                ]
                                inner_results = await asyncio.gather(*tasks, return_exceptions=True)
                                for j, s in enumerate(inner_level):
                                    r = inner_results[j]
                                    if isinstance(r, Exception):
                                        outputs[s.id] = f"Error: {r}"
                                    elif r is not None:
                                        outputs[s.id] = r
                return condition_met

            elif step.type == WorkflowNodeType.PARALLEL:
                if step.steps:
                    tasks = [
                        self._execute_dag_step(s, router, request, memory, outputs, timeline)
                        for s in step.steps
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, s in enumerate(step.steps):
                        r = results[i]
                        if isinstance(r, Exception):
                            outputs[s.id] = f"Error: {r}"
                        elif r is not None:
                            outputs[s.id] = r
                return None

            elif step.type == WorkflowNodeType.MERGE:
                merged = self._merge_outputs(outputs, step.merge_strategy)
                return merged

            elif step.type == WorkflowNodeType.RETRY:
                max_attempts = max(step.retry_count, 1)
                last_error = None
                for attempt in range(max_attempts):
                    try:
                        if step.steps:
                            retry_dag = WorkflowDAG(step.steps)
                            retry_levels = retry_dag.topological_sort()
                            for retry_level in retry_levels:
                                for retry_step in retry_level:
                                    inner = await self._execute_dag_step(
                                        retry_step, router, request, memory, outputs, timeline
                                    )
                                    if inner is not None:
                                        outputs[retry_step.id] = inner
                        break
                    except Exception as e:
                        last_error = e
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(1)
                if last_error and max_attempts > 0:
                    raise last_error  # type: ignore
                return None

            elif step.type == WorkflowNodeType.TIMEOUT:
                timeout = max(step.timeout, 1)
                try:
                    if step.steps:
                        inner_dag = WorkflowDAG(step.steps)
                        inner_levels = inner_dag.topological_sort()
                        for inner_level in inner_levels:
                            for inner_step in inner_level:
                                inner = await asyncio.wait_for(
                                    self._execute_dag_step(
                                        inner_step, router, request, memory, outputs, timeline
                                    ),
                                    timeout=timeout,
                                )
                                if inner is not None:
                                    outputs[inner_step.id] = inner
                except asyncio.TimeoutError:
                    pass
                return None

            elif step.type == WorkflowNodeType.WAIT:
                try:
                    duration = float(step.prompt or "1")
                    await asyncio.sleep(duration)
                except (ValueError, TypeError):
                    await asyncio.sleep(1)
                return None

            else:
                result = await self._execute_task(step, router, request, memory)
                return result.content if hasattr(result, "content") else str(result)

        finally:
            if timeline is not None:
                timeline.append({
                    "event": f"{step.id}_finished",
                    "step": step.id,
                    "type": step.type.value,
                    "timestamp": time.perf_counter(),
                    "duration_ms": (time.perf_counter() - step_start) * 1000,
                })

    async def _execute_task(
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
            return bool(eval(
                resolved,
                {"__builtins__": {}},
                {
                    "memory": memory,
                    "len": len,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "dict": dict,
                    "list": list,
                },
            ))
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
