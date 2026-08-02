from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from app.orchestration.planner import Planner
from app.orchestration.agents import AgentRegistry
from app.orchestration.executor import ExecutionEngine
from app.orchestration.reflection import ReflectionEngine
from app.orchestration.consensus import ConsensusEngine
from app.orchestration.debate import DebateEngine
from app.orchestration.tools import ToolPipeline
from app.orchestration.memory import ExecutionMemory
from app.orchestration.workflow import WorkflowBuilder
from app.orchestration.models import (
    AgentResult,
    ConsensusResult,
    DebateResult,
    ExecutionPlan,
    OrchestrationRequest,
    OrchestrationResponse,
    ReflectionScore,
    WorkflowDefinition,
    WorkflowNodeType,
    WorkflowResult,
)
from app.orchestration.metrics import (
    orchestrator_requests_total,
    orchestrator_active_requests,
)
from app.models import ChatRequest, Message, MessageRole, StreamChunk, StreamChoice
from app.router import router as _default_router

try:
    from app.config import config_manager
except ImportError:
    config_manager = None


class Orchestrator:
    def __init__(self, config: dict[str, Any] | None = None, router: Any | None = None):
        self._config = self._load_config() if config is None else config
        self._router = router or _default_router
        self._pipeline = getattr(self._router, "pipeline", None)
        self._init_engines()

    def _init_engines(self) -> None:
        self.planner = Planner(self._config.get("planner", {}))
        self.agent_registry = AgentRegistry()
        self.executor = ExecutionEngine(self.agent_registry)
        self.reflection = ReflectionEngine(self._config.get("reflection", {}))
        self.consensus = ConsensusEngine(self._config.get("consensus", {}))
        self.debate = DebateEngine(self._config.get("debate", {}))
        self.tools = ToolPipeline()
        self.memory = ExecutionMemory()

    def enable_hot_reload(self) -> None:
        if config_manager:
            config_manager.register_reload_callback(self.reload_config)

    def reload_config(self) -> None:
        self._config = self._load_config()
        self._init_engines()

    async def _run_hook(self, hook: str, *args: Any, **kwargs: Any) -> None:
        if self._pipeline:
            method = getattr(self._pipeline, f"execute_{hook}", None)
            if method:
                await method(*args, **kwargs)

    @staticmethod
    def _add_timeline(timeline: list[dict[str, Any]], event: str, **kwargs: Any) -> None:
        timeline.append({
            "event": event,
            "timestamp": time.time(),
            **kwargs,
        })

    @staticmethod
    def _load_config() -> dict[str, Any]:
        import os
        try:
            import yaml
            path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "orchestrator.yaml")
            if os.path.isfile(path):
                with open(path) as f:
                    data = yaml.safe_load(f)
                    return data.get("orchestrator", data) if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    async def orchestrate(self, request: OrchestrationRequest) -> OrchestrationResponse:
        orchestrator_requests_total.labels(mode=request.mode).inc()
        orchestrator_active_requests.labels(mode=request.mode).inc()
        response_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        timeline: list[dict[str, Any]] = []
        self._add_timeline(timeline, "orchestration_started", mode=request.mode)

        try:
            chat_request = self._build_chat_request(request)

            if request.mode == "consensus" or request.consensus:
                resp = await self._run_consensus_mode(request, chat_request, response_id, start)
                resp.timeline = timeline
                self._add_timeline(timeline, "orchestration_completed", latency_ms=resp.latency_ms)
                return resp

            if request.mode == "debate" or request.debate:
                resp = await self._run_debate_mode(request, chat_request, response_id, start)
                resp.timeline = timeline
                self._add_timeline(timeline, "orchestration_completed", latency_ms=resp.latency_ms)
                return resp

            if request.mode == "workflow" and request.workflow:
                resp = await self._run_workflow_mode(request, chat_request, response_id, start, timeline)
                resp.timeline = timeline
                self._add_timeline(timeline, "orchestration_completed", latency_ms=resp.latency_ms)
                return resp

            plan: ExecutionPlan
            if request.mode == "multi" or (request.agents and len(request.agents) > 1):
                plan = self.planner.create_multi_plan(
                    request.prompt,
                    request.agents,
                    parallel=request.parallel,
                )
            elif request.agents:
                plan = self.planner.create_single_plan(request.prompt, request.agents[0])
            else:
                plan = self.planner.create_plan(request.prompt, parallel=request.parallel)

            self._add_timeline(timeline, "plan_created", steps=len(plan.steps), mode=request.mode)
            resp = await self._run_plan_mode(request, chat_request, plan, response_id, start, timeline)
            resp.timeline = timeline
            self._add_timeline(timeline, "orchestration_completed", latency_ms=resp.latency_ms)
            return resp

        finally:
            orchestrator_active_requests.labels(mode=request.mode).dec()

    async def orchestrate_stream(
        self, request: OrchestrationRequest,
    ) -> AsyncIterator[StreamChunk]:
        orchestrator_requests_total.labels(mode=request.mode).inc()
        orchestrator_active_requests.labels(mode=request.mode).inc()
        response_id = uuid.uuid4().hex[:12]
        stream_id = f"orch_{response_id}"
        hook_ctx = {"request_id": response_id, "mode": request.mode, "stream": True}

        try:
            chat_request = self._build_chat_request(request)

            if request.mode == "single" and (not request.agents or request.agents == ["chat"]):
                await self._run_hook("before_plan", request, hook_ctx)
                async for chunk in self._router.stream_chat(chat_request):
                    yield chunk
                return

            if request.mode == "consensus" or request.consensus:
                await self._run_hook("before_plan", request, hook_ctx)
                providers = request.consensus_providers or ["openai", "anthropic", "google"]
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={"content": f"[consensus] Querying {len(providers)} providers...\n"})],
                )
                result = await self.consensus.run_consensus(chat_request, providers, self._router, strategy=request.consensus_strategy)
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={"content": result.content})],
                )
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
                )
                return

            if request.mode == "debate" or request.debate:
                await self._run_hook("before_plan", request, hook_ctx)
                provider_a = request.debate_provider_a or "openai"
                provider_b = request.debate_provider_b or "anthropic"
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={"content": f"[debate] {provider_a} vs {provider_b}...\n"})],
                )
                result = await self.debate.run_debate(chat_request, provider_a, provider_b, self._router)
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={"content": result.final_content})],
                )
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
                )
                return

            plan: ExecutionPlan
            if request.mode == "multi" or (request.agents and len(request.agents) > 1):
                plan = self.planner.create_multi_plan(request.prompt, request.agents, parallel=request.parallel)
            elif request.agents:
                plan = self.planner.create_single_plan(request.prompt, request.agents[0])
            else:
                plan = self.planner.create_plan(request.prompt, parallel=request.parallel)

            await self._run_hook("before_plan", request, hook_ctx)

            for step in plan.steps:
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={"content": f"[{step.agent}] {step.step}...\n"})],
                )

            results = await self.executor.execute_plan(plan, self._router, chat_request, self.memory)

            for r in results:
                await self._run_hook("after_agent", r, r.agent_name if hasattr(r, "agent_name") else "", hook_ctx)
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={"content": r.content})],
                )

            if request.reflection and results:
                last = results[-1]
                await self._run_hook("before_reflection", last, hook_ctx)
                final_result, reflection_score = await self.reflection.reflect_and_retry(last, self._router, chat_request)
                if reflection_score and reflection_score.should_retry:
                    yield StreamChunk(
                        id=stream_id, model=request.model or "",
                        choices=[StreamChoice(index=0, delta={"content": f"[reflection] {reflection_score.reason}, retrying...\n"})],
                    )
                yield StreamChunk(
                    id=stream_id, model=request.model or "",
                    choices=[StreamChoice(index=0, delta={"content": final_result.content})],
                )

            yield StreamChunk(
                id=stream_id, model=request.model or "",
                choices=[StreamChoice(index=0, delta={}, finish_reason="stop")],
            )

        finally:
            orchestrator_active_requests.labels(mode=request.mode).dec()

    async def _run_plan_mode(
        self,
        request: OrchestrationRequest,
        chat_request: ChatRequest,
        plan: ExecutionPlan,
        response_id: str,
        start: float,
        timeline: list[dict[str, Any]] | None = None,
    ) -> OrchestrationResponse:
        hook_ctx = {"request_id": response_id, "mode": request.mode, "plan": plan}
        await self._run_hook("before_plan", request, hook_ctx)
        self._add_timeline(timeline, "plan_execution_started", mode=request.mode)

        results = await self.executor.execute_plan(plan, self._router, chat_request, self.memory)

        for r in results:
            await self._run_hook("after_agent", r, r.agent_name if hasattr(r, "agent_name") else "", hook_ctx)
            self._add_timeline(timeline, f"agent_{r.agent}_completed",
                               agent=r.agent, step=r.step, tokens=r.tokens, cost=r.cost)

        final_content = ""
        total_tokens = 0
        total_cost = 0.0
        reflection_score: ReflectionScore | None = None

        if results:
            last = results[-1]
            final_content = last.content
            total_tokens = last.tokens
            total_cost = last.cost

            if request.reflection:
                await self._run_hook("before_reflection", last, hook_ctx)
                self._add_timeline(timeline, "reflection_started")
                final_result, reflection_score = await self.reflection.reflect_and_retry(
                    last, self._router, chat_request
                )
                final_content = final_result.content
                self._add_timeline(timeline, "reflection_completed",
                                   should_retry=reflection_score.should_retry if reflection_score else False)

        latency = (time.perf_counter() - start) * 1000
        graph = self._build_graph_from_plan(plan, results)
        response = OrchestrationResponse(
            id=response_id,
            content=final_content,
            plan=plan,
            results=results,
            reflection=reflection_score,
            latency_ms=latency,
            total_tokens=total_tokens,
            total_cost=total_cost,
            mode=request.mode,
            timeline=timeline or [],
            graph=graph,
        )
        await self._run_hook("after_orchestrate", response, hook_ctx)
        return response

    def _build_graph_from_plan(
        self, plan: ExecutionPlan, results: list[AgentResult]
    ) -> dict[str, Any]:
        nodes = []
        edges = []
        for i, step in enumerate(plan.steps):
            nodes.append({
                "id": step.step or f"step_{i}",
                "type": "agent",
                "agent": step.agent,
                "label": step.step or step.agent,
                "status": results[i].success if i < len(results) else "unknown",
            })
            if i > 0:
                edges.append({"from": plan.steps[i - 1].step or f"step_{i-1}", "to": step.step or f"step_{i}"})
        return {"nodes": nodes, "edges": edges}

    async def _run_consensus_mode(
        self,
        request: OrchestrationRequest,
        chat_request: ChatRequest,
        response_id: str,
        start: float,
    ) -> OrchestrationResponse:
        providers = request.consensus_providers
        if not providers:
            providers = ["openai", "anthropic", "google"]

        hook_ctx = {"request_id": response_id, "mode": "consensus", "providers": providers}
        await self._run_hook("before_plan", request, hook_ctx)

        result = await self.consensus.run_consensus(
            chat_request,
            providers,
            self._router,
            strategy=request.consensus_strategy,
        )

        latency = (time.perf_counter() - start) * 1000
        response = OrchestrationResponse(
            id=response_id,
            content=result.content,
            consensus=result,
            latency_ms=latency,
            mode="consensus",
        )
        await self._run_hook("after_orchestrate", response, hook_ctx)
        return response

    async def _run_debate_mode(
        self,
        request: OrchestrationRequest,
        chat_request: ChatRequest,
        response_id: str,
        start: float,
    ) -> OrchestrationResponse:
        provider_a = request.debate_provider_a or "openai"
        provider_b = request.debate_provider_b or "anthropic"

        hook_ctx = {"request_id": response_id, "mode": "debate", "provider_a": provider_a, "provider_b": provider_b}
        await self._run_hook("before_plan", request, hook_ctx)

        result = await self.debate.run_debate(
            chat_request,
            provider_a,
            provider_b,
            self._router,
        )

        latency = (time.perf_counter() - start) * 1000
        response = OrchestrationResponse(
            id=response_id,
            content=result.final_content,
            debate=result,
            latency_ms=latency,
            mode="debate",
        )
        await self._run_hook("after_orchestrate", response, hook_ctx)
        return response

    async def _run_workflow_mode(
        self,
        request: OrchestrationRequest,
        chat_request: ChatRequest,
        response_id: str,
        start: float,
        timeline: list[dict[str, Any]] | None = None,
    ) -> OrchestrationResponse:
        workflow = request.workflow
        if not workflow:
            return OrchestrationResponse(
                id=response_id,
                content="",
                latency_ms=0,
                mode="workflow",
            )

        hook_ctx = {"request_id": response_id, "mode": "workflow", "workflow": workflow.name if hasattr(workflow, "name") else ""}
        await self._run_hook("before_plan", request, hook_ctx)

        self._add_timeline(timeline, "workflow_execution_started", workflow_id=workflow.id)
        result = await self.executor.execute_workflow(workflow, self._router, chat_request, self.memory, timeline)
        self._add_timeline(timeline, "workflow_execution_completed", success=result.success)

        final_content = str(result.outputs.get("final", list(result.outputs.values())[-1] if result.outputs else ""))

        latency = (time.perf_counter() - start) * 1000
        graph = self._build_graph_from_workflow(workflow)
        response = OrchestrationResponse(
            id=response_id,
            content=final_content,
            workflow=result,
            latency_ms=latency,
            mode="workflow",
            timeline=timeline or [],
            graph=graph,
        )
        await self._run_hook("after_orchestrate", response, hook_ctx)
        return response

    def _build_graph_from_workflow(self, workflow: WorkflowDefinition) -> dict[str, Any]:
        nodes = []
        edges = []
        for step in workflow.steps:
            nodes.append({
                "id": step.id,
                "type": step.type.value if isinstance(step.type, WorkflowNodeType) else str(step.type),
                "agent": step.agent,
                "label": step.id or step.type,
            })
            for dep in step.depends_on:
                if dep != "START":
                    edges.append({"from": dep, "to": step.id})
        return {"nodes": nodes, "edges": edges, "steps": len(workflow.steps)}

    def _build_chat_request(self, request: OrchestrationRequest) -> ChatRequest:
        if request.messages:
            messages = [Message(**m) if isinstance(m, dict) else m for m in request.messages]
        else:
            messages = [Message(role=MessageRole.USER, content=request.prompt)]
        return ChatRequest(
            messages=messages,
            model=request.model or "",
            stream=request.stream,
            metadata=request.metadata,
        )

    async def chat(self, chat_request: ChatRequest) -> Any:
        return await self._router.chat(chat_request)


orchestrator = Orchestrator()
