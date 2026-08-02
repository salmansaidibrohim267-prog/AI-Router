import pytest

from app.orchestration.executor import ExecutionEngine
from app.orchestration.agents import AgentRegistry
from app.orchestration.memory import ExecutionMemory
from app.orchestration.models import (
    AgentResult,
    ExecutionPlan,
    PlanStep,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowNodeType,
    WorkflowResult,
)


class FakeRouter:
    async def chat(self, request):
        from app.models import ChatResponse, ChatChoice, Message, MessageRole, Usage
        return ChatResponse(
            id="fake",
            model="test",
            choices=[ChatChoice(
                index=0,
                message=Message(role=MessageRole.ASSISTANT, content="fake response"),
                finish_reason="stop",
            )],
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


class TestExecutionEngine:
    def setup_method(self):
        self.engine = ExecutionEngine()
        self.router = FakeRouter()

    async def test_empty_plan(self):
        plan = ExecutionPlan(steps=[])
        results = await self.engine.execute_plan(plan, self.router)
        assert results == []

    async def test_single_step_sequential(self):
        plan = ExecutionPlan(steps=[
            PlanStep(step="test", agent="chat", prompt_template="Hello"),
        ])
        results = await self.engine.execute_plan(plan, self.router)
        assert len(results) == 1
        assert results[0].agent == "chat"

    async def test_unknown_agent_returns_error(self):
        plan = ExecutionPlan(steps=[
            PlanStep(step="test", agent="nonexistent", prompt_template="Hi"),
        ])
        results = await self.engine.execute_plan(plan, self.router)
        assert len(results) == 1
        assert results[0].success is False
        assert "Unknown agent" in results[0].error

    async def test_sequential_execution_order(self):
        plan = ExecutionPlan(steps=[
            PlanStep(step="first", agent="chat", prompt_template="First"),
            PlanStep(step="second", agent="chat", prompt_template="Second"),
            PlanStep(step="third", agent="chat", prompt_template="Third"),
        ])
        results = await self.engine.execute_plan(plan, self.router)
        assert len(results) == 3
        assert results[0].step == "first"
        assert results[1].step == "second"
        assert results[2].step == "third"

    async def test_parallel_execution(self):
        plan = ExecutionPlan(steps=[
            PlanStep(step="a", agent="chat", prompt_template="A", execution="parallel"),
            PlanStep(step="b", agent="chat", prompt_template="B", execution="parallel"),
        ])
        results = await self.engine.execute_plan(plan, self.router)
        assert len(results) == 2

    async def test_memory_passed_between_steps(self):
        plan = ExecutionPlan(steps=[
            PlanStep(step="s1", agent="chat", prompt_template="Step 1"),
            PlanStep(step="s2", agent="chat", prompt_template="Step 2", context_refs=["s1"]),
        ])
        memory = ExecutionMemory()
        results = await self.engine.execute_plan(plan, self.router, memory=memory)
        assert len(results) == 2
        assert memory.get("last_output") is not None

    async def test_timeout_returns_error(self):
        class SlowAgent:
            name = "slow"
            async def execute(self, step, memory, router, request=None):
                import asyncio
                await asyncio.sleep(10)
                return AgentResult(agent="slow", step=step.step, content="never")

        registry = AgentRegistry()
        registry._agents["slow"] = lambda: SlowAgent()
        engine = ExecutionEngine(registry)
        plan = ExecutionPlan(steps=[
            PlanStep(step="test", agent="slow", prompt_template="Hi", timeout=0.01),
        ])
        results = await engine.execute_plan(plan, self.router)
        assert len(results) == 1
        assert results[0].success is False
        assert "timed out" in results[0].error.lower()

    async def test_plan_with_context(self):
        plan = ExecutionPlan(
            steps=[PlanStep(step="s1", agent="chat", prompt_template="Hi")],
            context={"custom_key": "custom_value"},
        )
        memory = ExecutionMemory()
        await self.engine.execute_plan(plan, self.router, memory=memory)
        assert memory.get("custom_key") == "custom_value"


class TestWorkflowExecution:
    def setup_method(self):
        self.engine = ExecutionEngine()
        self.router = FakeRouter()

    async def test_workflow_task(self):
        workflow = WorkflowDefinition(
            id="wf1",
            steps=[
                WorkflowStep(id="task1", type=WorkflowNodeType.TASK, agent="chat", prompt="Hello"),
            ],
        )
        result = await self.engine.execute_workflow(workflow, self.router)
        assert result.success is True

    async def test_workflow_wait(self):
        import time
        workflow = WorkflowDefinition(
            id="wf2",
            steps=[
                WorkflowStep(id="w1", type=WorkflowNodeType.WAIT, prompt="0.01"),
                WorkflowStep(id="t1", type=WorkflowNodeType.TASK, agent="chat", prompt="After wait"),
            ],
        )
        start = time.perf_counter()
        result = await self.engine.execute_workflow(workflow, self.router)
        elapsed = time.perf_counter() - start
        assert result.success is True
        assert elapsed >= 0.01

    async def test_workflow_parallel(self):
        workflow = WorkflowDefinition(
            id="wf3",
            steps=[
                WorkflowStep(id="p1", type=WorkflowNodeType.PARALLEL, steps=[
                    WorkflowStep(id="a", type=WorkflowNodeType.TASK, agent="chat", prompt="A"),
                    WorkflowStep(id="b", type=WorkflowNodeType.TASK, agent="chat", prompt="B"),
                ]),
            ],
        )
        result = await self.engine.execute_workflow(workflow, self.router)
        assert result.success is True

    async def test_workflow_retry_success(self):
        workflow = WorkflowDefinition(
            id="wf4",
            steps=[
                WorkflowStep(id="r1", type=WorkflowNodeType.RETRY, retry_count=2, steps=[
                    WorkflowStep(id="t1", type=WorkflowNodeType.TASK, agent="chat", prompt="Retry me"),
                ]),
            ],
        )
        result = await self.engine.execute_workflow(workflow, self.router)
        assert result.success is True

    async def test_workflow_timeout(self):
        class SlowAgent:
            name = "slow"
            async def execute(self, step, memory, router, request=None):
                import asyncio
                await asyncio.sleep(10)
                return AgentResult(agent="slow", step=step.step, content="never")

        registry = AgentRegistry()
        registry._agents["slow"] = lambda: SlowAgent()
        engine = ExecutionEngine(registry)
        workflow = WorkflowDefinition(
            id="wf5",
            steps=[
                WorkflowStep(id="to1", type=WorkflowNodeType.TIMEOUT, timeout=0.01, steps=[
                    WorkflowStep(id="t1", type=WorkflowNodeType.TASK, agent="slow", prompt="Timeout test"),
                ]),
            ],
        )
        result = await engine.execute_workflow(workflow, self.router)
        assert result.success is True

    async def test_workflow_merge(self):
        workflow = WorkflowDefinition(
            id="wf6",
            steps=[
                WorkflowStep(id="t1", type=WorkflowNodeType.TASK, agent="chat", prompt="First"),
                WorkflowStep(id="t2", type=WorkflowNodeType.TASK, agent="chat", prompt="Second"),
                WorkflowStep(id="m1", type=WorkflowNodeType.MERGE, merge_strategy="concat"),
            ],
        )
        result = await self.engine.execute_workflow(workflow, self.router)
        assert result.success is True

    async def test_workflow_empty_steps(self):
        workflow = WorkflowDefinition(id="wf7", steps=[])
        result = await self.engine.execute_workflow(workflow, self.router)
        assert result.success is True
        assert result.outputs == {}

    async def test_workflow_unknown_agent(self):
        workflow = WorkflowDefinition(
            id="wf8",
            steps=[
                WorkflowStep(id="t1", type=WorkflowNodeType.TASK, agent="does_not_exist", prompt="Hi"),
            ],
        )
        result = await self.engine.execute_workflow(workflow, self.router)
        assert result.success is True
