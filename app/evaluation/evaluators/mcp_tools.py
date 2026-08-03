from __future__ import annotations

from typing import Any

from ..models import EvaluationSample, MetricScore
from ..registry import BaseEvaluator


class MCPToolUsageEvaluator(BaseEvaluator):
    kind = "mcp_tools"

    def evaluate_scores(self, sample: EvaluationSample) -> list[MetricScore]:
        expected_tools = {str(t) for t in sample.expected.get("tools", [])}
        calls = sample.actual.get("calls", [])
        if not calls:
            return [
                MetricScore("tool_success_rate", 1.0),
                MetricScore("tool_error_rate", 0.0),
                MetricScore("tool_completeness", 0.0),
                MetricScore("tool_precision", 0.0),
                MetricScore("tool_correctness", 0.0),
            ]
        successful = sum(1 for c in calls if bool(c.get("success", True)) and not c.get("error"))
        success_rate = round(successful / len(calls), 4)
        called_tools = {str(c.get("tool", "")) for c in calls}
        completeness = round(len(expected_tools & called_tools) / len(expected_tools), 4) if expected_tools else 0.0
        precision = round(len(expected_tools & called_tools) / len(called_tools), 4) if called_tools else 0.0
        correct = sum(1 for c in calls if self._call_correct(c))
        correctness = round(correct / len(calls), 4)
        return [
            MetricScore("tool_success_rate", success_rate),
            MetricScore("tool_error_rate", round(1.0 - success_rate, 4)),
            MetricScore("tool_completeness", completeness),
            MetricScore("tool_precision", precision),
            MetricScore("tool_correctness", correctness),
        ]

    @staticmethod
    def _call_correct(call: dict[str, Any]) -> bool:
        if not call.get("success", True) or call.get("error"):
            return False
        arguments = call.get("arguments")
        if isinstance(arguments, dict):
            return len(arguments) > 0
        return isinstance(arguments, list) and len(arguments) > 0
