import pytest

from app.orchestration.models import (
    ExecutionPlan,
    PlanStep,
    AgentResult,
    ReflectionScore,
    ConsensusResult,
    DebateResult,
    VoteScore,
    WorkflowDefinition,
    WorkflowStep,
    WorkflowResult,
    ToolDefinition,
    OrchestrationRequest,
    OrchestrationResponse,
    ExecutionMode,
    ConsensusStrategy,
    WorkflowNodeType,
    PlanStepType,
)


class TestEnums:
    def test_execution_mode_values(self):
        assert ExecutionMode.SEQUENTIAL.value == "sequential"
        assert ExecutionMode.PARALLEL.value == "parallel"
        assert ExecutionMode.WORKFLOW.value == "workflow"

    def test_consensus_strategy_values(self):
        assert ConsensusStrategy.MAJORITY_VOTE.value == "majority_vote"
        assert ConsensusStrategy.WEIGHTED_SCORE.value == "weighted_score"
        assert ConsensusStrategy.HIGHEST_CONFIDENCE.value == "highest_confidence"
        assert ConsensusStrategy.FIRST_SUCCESS.value == "first_success"
        assert ConsensusStrategy.BEST_LATENCY.value == "best_latency"

    def test_workflow_node_type_values(self):
        assert WorkflowNodeType.TASK.value == "task"
        assert WorkflowNodeType.IF.value == "if"
        assert WorkflowNodeType.ELSE.value == "else"
        assert WorkflowNodeType.FOR.value == "for"
        assert WorkflowNodeType.PARALLEL.value == "parallel"
        assert WorkflowNodeType.WAIT.value == "wait"
        assert WorkflowNodeType.RETRY.value == "retry"
        assert WorkflowNodeType.TIMEOUT.value == "timeout"
        assert WorkflowNodeType.MERGE.value == "merge"


class TestModels:
    def test_plan_step_defaults(self):
        step = PlanStep()
        assert step.step == ""
        assert step.agent == "chat"
        assert step.execution == "sequential"
        assert step.timeout == 60
        assert step.retry_count == 0
        assert step.tools == []

    def test_plan_step_custom(self):
        step = PlanStep(
            step="code",
            agent="coder",
            execution="parallel",
            prompt_template="Write code",
            timeout=30,
            retry_count=2,
            tools=["search"],
        )
        assert step.step == "code"
        assert step.agent == "coder"
        assert step.execution == "parallel"
        assert step.timeout == 30
        assert step.retry_count == 2
        assert "search" in step.tools

    def test_execution_plan(self):
        plan = ExecutionPlan(
            steps=[PlanStep(step="s1", agent="chat")],
            plan_id="test-123",
            context={"key": "value"},
        )
        assert len(plan.steps) == 1
        assert plan.plan_id == "test-123"
        assert plan.context["key"] == "value"

    def test_agent_result_defaults(self):
        r = AgentResult(agent="test", step="s1", content="done")
        assert r.success is True
        assert r.error == ""
        assert r.latency_ms == 0.0
        assert r.tokens == 0
        assert r.cost == 0.0

    def test_agent_result_failure(self):
        r = AgentResult(agent="test", step="s1", content="", success=False, error="something failed")
        assert r.success is False
        assert r.error == "something failed"

    def test_reflection_score_defaults(self):
        s = ReflectionScore()
        assert s.correctness == 0.0
        assert s.hallucination == 0.0
        assert s.completeness == 0.0
        assert s.overall == 0.0
        assert s.should_retry is False

    def test_reflection_score_high(self):
        s = ReflectionScore(correctness=0.9, hallucination=0.8, completeness=0.95, overall=0.88, should_retry=False, reason="Good")
        assert s.overall == 0.88
        assert s.should_retry is False

    def test_consensus_result(self):
        r = ConsensusResult(provider="openai", model="gpt-4", content="result", strategy="majority_vote", scores={"quality": 0.9}, votes=3, total_votes=5)
        assert r.provider == "openai"
        assert r.strategy == "majority_vote"
        assert r.votes == 3
        assert r.total_votes == 5

    def test_debate_result(self):
        r = DebateResult(
            provider_a="openai", provider_b="anthropic",
            argument_a="arg a", argument_b="arg b",
            final_content="final", winner="openai",
            reviewer_notes="OpenAI was better",
        )
        assert r.winner == "openai"
        assert r.final_content == "final"

    def test_vote_score(self):
        s = VoteScore(quality=0.8, cost=0.7, latency=0.9, reliability=0.85, overall=0.81)
        assert s.quality == 0.8
        assert s.overall == 0.81

    def test_workflow_step_defaults(self):
        s = WorkflowStep()
        assert s.type == WorkflowNodeType.TASK
        assert s.retry_count == 0
        assert s.timeout == 60

    def test_workflow_definition(self):
        wf = WorkflowDefinition(id="wf1", steps=[WorkflowStep(id="s1", type=WorkflowNodeType.TASK)])
        assert wf.id == "wf1"
        assert len(wf.steps) == 1

    def test_workflow_result(self):
        r = WorkflowResult(workflow_id="wf1", outputs={"key": "value"}, success=True)
        assert r.success is True
        assert r.outputs["key"] == "value"

    def test_tool_definition(self):
        t = ToolDefinition(name="search", description="Search tool", timeout=15)
        assert t.name == "search"
        assert t.timeout == 15

    def test_orchestration_request_defaults(self):
        r = OrchestrationRequest()
        assert r.mode == "single"
        assert r.reflection is False
        assert r.consensus is False
        assert r.debate is False
        assert r.parallel is False
        assert r.stream is False
        assert r.timeout == 120

    def test_orchestration_request_custom(self):
        r = OrchestrationRequest(
            prompt="Test",
            agents=["coder", "reviewer"],
            mode="multi",
            reflection=True,
            consensus=False,
            parallel=True,
        )
        assert r.prompt == "Test"
        assert len(r.agents) == 2
        assert r.mode == "multi"
        assert r.reflection is True
        assert r.parallel is True

    def test_orchestration_response_defaults(self):
        r = OrchestrationResponse()
        assert r.content == ""
        assert r.mode == ""
        assert r.latency_ms == 0.0
        assert r.total_tokens == 0
        assert r.total_cost == 0.0
