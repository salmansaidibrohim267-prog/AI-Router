from __future__ import annotations

import sys
import traceback
from typing import Any

from app.tools.base import Tool, ToolCall, ToolResponse, ToolSpec


class PythonTool(Tool):
    spec = ToolSpec(
        name="python",
        description="Execute Python code and return the result",
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Python code to execute"},
            },
            "required": ["input"],
        },
        required_permissions=["python_exec"],
        timeout=30,
    )

    async def execute(self, call: ToolCall) -> ToolResponse:
        code = call.input.strip()
        if not code:
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error="No code provided",
            )
        globs = {"__builtins__": __builtins__}
        try:
            compile(code, "<tool>", "exec")
            exec(code, globs)
            result = globs.get("_result", "Code executed successfully (no _result variable set)")
            return ToolResponse(
                tool_name=self.spec.name,
                success=True,
                output=str(result),
            )
        except Exception as e:
            tb = traceback.format_exc()
            return ToolResponse(
                tool_name=self.spec.name,
                success=False,
                error=f"{type(e).__name__}: {e}\n{tb}",
            )
