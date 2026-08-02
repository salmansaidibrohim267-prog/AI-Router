from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, Callable

from app.tools.models import ToolCall, ToolResponse


class ToolResult:
    def __init__(self, success: bool = True, output: str = "", error: str = ""):
        self.success = success
        self.output = output
        self.error = error
        self.duration_ms: float = 0.0
        self.tokens_used: int = 0

    def __str__(self) -> str:
        return self.output if self.success else f"Error: {self.error}"


class ToolSpec:
    def __init__(
        self,
        name: str,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        required_permissions: list[str] | None = None,
        timeout: int = 30,
        synchronous: bool = True,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters or {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input for the tool"}
            },
            "required": ["input"],
        }
        self.required_permissions = required_permissions or []
        self.timeout = timeout
        self.synchronous = synchronous

    def to_openai_format(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Tool(ABC):
    spec: ToolSpec

    @abstractmethod
    async def execute(self, call: ToolCall) -> ToolResponse:
        ...

    def get_spec(self) -> ToolSpec:
        return self.spec

    def validate_input(self, input_data: Any) -> str:
        if isinstance(input_data, str):
            return input_data
        if isinstance(input_data, dict):
            return str(input_data.get("input", input_data))
        return str(input_data)


class _SyncWrapperTool(Tool):
    def __init__(self, fn: Callable[..., Any], spec: ToolSpec):
        self._fn = fn
        self.spec = spec

    async def execute(self, call: ToolCall) -> ToolResponse:
        loop = asyncio.get_event_loop()
        start = time.perf_counter()
        try:
            result = await loop.run_in_executor(None, self._fn, call.input)
            elapsed = (time.perf_counter() - start) * 1000
            return ToolResponse(
                tool_name=call.tool_name,
                success=True,
                output=str(result),
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolResponse(
                tool_name=call.tool_name,
                success=False,
                output="",
                error=str(e),
                duration_ms=elapsed,
            )
