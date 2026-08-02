import pytest

from app.orchestration.dag import WorkflowDAG, DAGExecutor, CycleError
from app.orchestration.models import WorkflowStep, WorkflowDefinition, WorkflowNodeType


class TestWorkflowDAG:
    def test_topological_sort_linear(self):
        steps = [
            WorkflowStep(id="a", type=WorkflowNodeType.TASK),
            WorkflowStep(id="b", type=WorkflowNodeType.TASK, depends_on=["a"]),
            WorkflowStep(id="c", type=WorkflowNodeType.TASK, depends_on=["b"]),
        ]
        dag = WorkflowDAG(steps)
        levels = dag.topological_sort()
        assert len(levels) == 3
        assert levels[0][0].id == "a"
        assert levels[1][0].id == "b"
        assert levels[2][0].id == "c"

    def test_topological_sort_parallel(self):
        steps = [
            WorkflowStep(id="start", type=WorkflowNodeType.TASK),
            WorkflowStep(id="b1", type=WorkflowNodeType.TASK, depends_on=["start"]),
            WorkflowStep(id="b2", type=WorkflowNodeType.TASK, depends_on=["start"]),
            WorkflowStep(id="end", type=WorkflowNodeType.TASK, depends_on=["b1", "b2"]),
        ]
        dag = WorkflowDAG(steps)
        levels = dag.topological_sort()
        assert len(levels) == 3
        assert len(levels[1]) == 2

    def test_cycle_detection(self):
        steps = [
            WorkflowStep(id="a", type=WorkflowNodeType.TASK, depends_on=["b"]),
            WorkflowStep(id="b", type=WorkflowNodeType.TASK, depends_on=["a"]),
        ]
        with pytest.raises(CycleError):
            WorkflowDAG(steps)

    def test_to_visualization_data(self):
        steps = [
            WorkflowStep(id="a", type=WorkflowNodeType.TASK),
            WorkflowStep(id="b", type=WorkflowNodeType.TASK, depends_on=["a"]),
        ]
        dag = WorkflowDAG(steps)
        viz = dag.to_visualization_data()
        assert "nodes" in viz
        assert "edges" in viz
        assert len(viz["nodes"]) == 2
        assert len(viz["edges"]) == 1

    def test_get_levels(self):
        steps = [
            WorkflowStep(id="a", type=WorkflowNodeType.TASK),
            WorkflowStep(id="b", type=WorkflowNodeType.TASK, depends_on=["a"]),
        ]
        dag = WorkflowDAG(steps)
        levels = dag.get_levels()
        assert levels == [["a"], ["b"]]

    def test_unknown_dependency(self):
        steps = [
            WorkflowStep(id="a", type=WorkflowNodeType.TASK, depends_on=["nonexistent"]),
        ]
        with pytest.raises(ValueError):
            WorkflowDAG(steps)


class TestDAGExecutor:
    @pytest.mark.asyncio
    async def test_cycle_error_handled(self):
        steps = [
            WorkflowStep(id="a", type=WorkflowNodeType.TASK, depends_on=["b"]),
            WorkflowStep(id="b", type=WorkflowNodeType.TASK, depends_on=["a"]),
        ]
        workflow = WorkflowDefinition(id="test", steps=steps)
        executor = DAGExecutor()
        result = await executor.execute(workflow, None)
        assert not result.success
        assert "cycle" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_workflow(self):
        workflow = WorkflowDefinition(id="empty", steps=[])
        executor = DAGExecutor()
        result = await executor.execute(workflow, None)
        assert result.success

    @pytest.mark.asyncio
    async def test_merge_node(self):
        steps = [
            WorkflowStep(id="m1", type=WorkflowNodeType.MERGE, merge_strategy="concat"),
        ]
        workflow = WorkflowDefinition(id="test", steps=steps)
        executor = DAGExecutor()
        result = await executor.execute(workflow, None)
        assert result.success

    @pytest.mark.asyncio
    async def test_wait_node(self):
        steps = [
            WorkflowStep(id="w1", type=WorkflowNodeType.WAIT, prompt="0.01"),
        ]
        workflow = WorkflowDefinition(id="test", steps=steps)
        executor = DAGExecutor()
        result = await executor.execute(workflow, None)
        assert result.success

    @pytest.mark.asyncio
    async def test_timeline_passthrough(self):
        steps = [
            WorkflowStep(id="s1", type=WorkflowNodeType.WAIT, prompt="0.01"),
        ]
        workflow = WorkflowDefinition(id="test", steps=steps)
        executor = DAGExecutor()
        timeline = []
        await executor.execute(workflow, None, timeline=timeline)
        assert len(timeline) >= 2
        assert timeline[0]["event"] == "s1_started"
        assert timeline[1]["event"] == "s1_finished"
