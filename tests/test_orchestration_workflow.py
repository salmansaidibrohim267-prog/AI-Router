import pytest

from app.orchestration.workflow import WorkflowBuilder
from app.orchestration.models import (
    WorkflowDefinition,
    WorkflowNodeType,
    WorkflowStep,
    PlanStep,
)


class TestWorkflowBuilder:
    def test_build_empty_workflow(self):
        builder = WorkflowBuilder("test-empty")
        wf = builder.build()
        assert wf.id == "test-empty"
        assert wf.steps == []

    def test_add_task(self):
        builder = WorkflowBuilder("wf1")
        builder.task("step1", "chat", "Hello")
        wf = builder.build()
        assert len(wf.steps) == 1
        assert wf.steps[0].id == "step1"
        assert wf.steps[0].type == WorkflowNodeType.TASK
        assert wf.steps[0].agent == "chat"
        assert wf.steps[0].prompt == "Hello"

    def test_add_task_with_kwargs(self):
        builder = WorkflowBuilder("wf2")
        builder.task("s1", "coder", "Write code", timeout=30, retry_count=2)
        wf = builder.build()
        assert wf.steps[0].timeout == 30
        assert wf.steps[0].retry_count == 2

    def test_if_condition(self):
        builder = WorkflowBuilder("wf3")
        inner = [WorkflowStep(id="inner", type=WorkflowNodeType.TASK, agent="chat", prompt="Do something")]
        builder.if_condition("cond1", "memory.get('score', 0) > 0.5", inner)
        wf = builder.build()
        assert wf.steps[0].type == WorkflowNodeType.IF
        assert wf.steps[0].condition == "memory.get('score', 0) > 0.5"
        assert len(wf.steps[0].steps) == 1

    def test_else_branch(self):
        builder = WorkflowBuilder("wf4")
        inner = [WorkflowStep(id="else_inner", type=WorkflowNodeType.TASK, agent="chat", prompt="Else action")]
        builder.else_branch("else1", inner)
        wf = builder.build()
        assert wf.steps[0].type == WorkflowNodeType.ELSE

    def test_for_loop(self):
        builder = WorkflowBuilder("wf5")
        inner = [WorkflowStep(id="loop_body", type=WorkflowNodeType.TASK, agent="chat", prompt="Process {{item}}")]
        builder.for_loop("loop1", "items", "item", inner)
        wf = builder.build()
        assert wf.steps[0].type == WorkflowNodeType.FOR
        assert wf.steps[0].collection == "items"
        assert wf.steps[0].variable == "item"

    def test_parallel(self):
        builder = WorkflowBuilder("wf6")
        branches = [
            WorkflowStep(id="a", type=WorkflowNodeType.TASK, agent="chat", prompt="A"),
            WorkflowStep(id="b", type=WorkflowNodeType.TASK, agent="chat", prompt="B"),
        ]
        builder.parallel("par1", branches)
        wf = builder.build()
        assert wf.steps[0].type == WorkflowNodeType.PARALLEL
        assert len(wf.steps[0].steps) == 2

    def test_wait(self):
        builder = WorkflowBuilder("wf7")
        builder.wait("wait1", "2")
        wf = builder.build()
        assert wf.steps[0].type == WorkflowNodeType.WAIT
        assert wf.steps[0].prompt == "2"

    def test_retry(self):
        builder = WorkflowBuilder("wf8")
        inner = [WorkflowStep(id="retry_task", type=WorkflowNodeType.TASK, agent="chat", prompt="Retry me")]
        builder.retry("retry1", 3, inner)
        wf = builder.build()
        assert wf.steps[0].type == WorkflowNodeType.RETRY
        assert wf.steps[0].retry_count == 3

    def test_timeout(self):
        builder = WorkflowBuilder("wf9")
        inner = [WorkflowStep(id="timeout_task", type=WorkflowNodeType.TASK, agent="chat", prompt="Slow")]
        builder.timeout("to1", 5, inner)
        wf = builder.build()
        assert wf.steps[0].type == WorkflowNodeType.TIMEOUT
        assert wf.steps[0].timeout == 5

    def test_merge(self):
        builder = WorkflowBuilder("wf10")
        builder.merge("merge1", "concat")
        wf = builder.build()
        assert wf.steps[0].type == WorkflowNodeType.MERGE
        assert wf.steps[0].merge_strategy == "concat"

    def test_to_plan_steps(self):
        builder = WorkflowBuilder("wf11")
        builder.task("s1", "chat", "Hello")
        builder.task("s2", "coder", "Write code")
        plan_steps = builder.to_plan_steps()
        assert len(plan_steps) == 2
        assert isinstance(plan_steps[0], PlanStep)
        assert plan_steps[0].agent == "chat"
        assert plan_steps[1].agent == "coder"

    def test_chained_builder(self):
        builder = WorkflowBuilder("chained")
        wf = (builder
            .task("t1", "chat", "First")
            .task("t2", "coder", "Second")
            .wait("w1", "0.5")
            .merge("m1")
            .build())
        assert len(wf.steps) == 4
        assert wf.steps[0].type == WorkflowNodeType.TASK
        assert wf.steps[1].type == WorkflowNodeType.TASK
        assert wf.steps[2].type == WorkflowNodeType.WAIT
        assert wf.steps[3].type == WorkflowNodeType.MERGE
