import pytest

from app.orchestration.planner import Planner
from app.orchestration.models import ExecutionPlan, PlanStep


class TestPlanner:
    def setup_method(self):
        self.planner = Planner()

    def test_single_plan_creation(self):
        plan = self.planner.create_single_plan("Write code", agent="coder")
        assert len(plan.steps) == 1
        assert plan.steps[0].agent == "coder"
        assert plan.steps[0].step == "single"

    def test_multi_plan_creation(self):
        plan = self.planner.create_multi_plan(
            "Build an API",
            agents=["coder", "architect", "reviewer"],
            parallel=False,
        )
        assert len(plan.steps) == 3
        assert plan.steps[0].agent == "coder"
        assert plan.steps[1].agent == "architect"
        assert plan.steps[2].agent == "reviewer"

    def test_multi_plan_parallel(self):
        plan = self.planner.create_multi_plan(
            "Design system",
            agents=["architect", "analyst"],
            parallel=True,
        )
        assert len(plan.steps) == 2
        assert plan.steps[0].execution == "parallel"
        assert plan.steps[1].execution == "sequential"

    def test_create_plan_from_prompt_matches_coding(self):
        plan = self.planner.create_plan("Write code for sorting")
        assert len(plan.steps) >= 1
        assert plan.steps[0].agent == "coder"

    def test_create_plan_from_prompt_matches_architecture(self):
        plan = self.planner.create_plan("Design a microservices architecture")
        assert plan.steps[0].agent == "architect"

    def test_create_plan_from_prompt_matches_analysis(self):
        plan = self.planner.create_plan("Analyze the performance data")
        assert plan.steps[0].agent == "analyst"

    def test_create_plan_falls_back_to_chat(self):
        plan = self.planner.create_plan("Hello, how are you?")
        assert plan.steps[0].agent == "chat"

    def test_create_plan_with_specific_agents(self):
        plan = self.planner.create_plan(
            "Review this code",
            agents=["coder", "reviewer"],
        )
        assert len(plan.steps) == 2
        assert plan.steps[0].agent == "coder"
        assert plan.steps[1].agent == "reviewer"

    def test_create_plan_with_single_agent(self):
        plan = self.planner.create_plan(
            "Write code",
            agents=["coder"],
        )
        assert len(plan.steps) == 1

    def test_plan_has_unique_id(self):
        plan1 = self.planner.create_single_plan("Test")
        plan2 = self.planner.create_single_plan("Test")
        assert plan1.plan_id != plan2.plan_id

    def test_multi_step_prompt_template(self):
        plan = self.planner.create_plan("Design architecture and write code")
        assert len(plan.steps) == 2
        assert "coder perspective" in plan.steps[0].prompt_template
        assert plan.steps[1].prompt_template == "Design architecture and write code"

    def test_plan_step_defaults(self):
        step = PlanStep()
        assert step.step == ""
        assert step.agent == "chat"
        assert step.execution == "sequential"
        assert step.timeout == 60
        assert step.retry_count == 0
        assert step.tools == []

    def test_plan_from_prompt_matches_multiple_agents(self):
        plan = self.planner.create_plan("Design architecture and write code")
        agents = [s.agent for s in plan.steps]
        assert "architect" in agents
        assert "coder" in agents

    def test_plan_context_dict(self):
        plan = self.planner.create_single_plan("Test")
        assert isinstance(plan.context, dict)
        assert plan.context == {}
