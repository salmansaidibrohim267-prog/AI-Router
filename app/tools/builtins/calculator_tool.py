from __future__ import annotations

from app.tools.base import Tool, ToolCall, ToolResponse, ToolSpec


class CalculatorTool(Tool):
    spec = ToolSpec(
        name="calculator",
        description="Evaluate mathematical expressions",
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Mathematical expression to evaluate"},
            },
            "required": ["input"],
        },
        required_permissions=[],
        timeout=5,
    )

    async def execute(self, call: ToolCall) -> ToolResponse:
        expr = call.input.strip()
        if not expr:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error="No expression provided",
            )
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            return ToolResponse(
                tool_name=self.spec.name,
                success=True,
                output=str(result),
            )
        except Exception as e:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error=str(e),
            )
