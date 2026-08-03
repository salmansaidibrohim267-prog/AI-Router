from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from app.orchestration.models import ToolDefinition


class ToolResult:
    def __init__(self, success: bool = True, output: str = "", error: str = ""):
        self.success = success
        self.output = output
        self.error = error

    def __str__(self) -> str:
        return self.output if self.success else f"Error: {self.error}"


class BaseTool(ABC):
    name: str = "base"
    description: str = ""
    timeout: int = 30

    @abstractmethod
    async def execute(self, input_data: str, **kwargs: Any) -> ToolResult: ...

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            timeout=self.timeout,
        )


class SearchTool(BaseTool):
    name = "search"
    description = "Search the web for information"
    timeout = 15

    async def execute(self, input_data: str, **kwargs: Any) -> ToolResult:
        return ToolResult(output=f"[Search results for: {input_data[:100]}]")


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate mathematical expressions"
    timeout = 5

    async def execute(self, input_data: str, **kwargs: Any) -> ToolResult:
        try:
            result = eval(input_data, {"__builtins__": {}}, {})
            return ToolResult(output=str(result))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class DatabaseTool(BaseTool):
    name = "database"
    description = "Query a database (simulated)"
    timeout = 10

    async def execute(self, input_data: str, **kwargs: Any) -> ToolResult:
        return ToolResult(output=f"[Database query result for: {input_data[:100]}]")


class HTTPTool(BaseTool):
    name = "http"
    description = "Make HTTP requests"
    timeout = 30

    async def execute(self, input_data: str, **kwargs: Any) -> ToolResult:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(input_data)
                return ToolResult(output=resp.text[:2000])
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ToolPipeline:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_all(self) -> dict[str, BaseTool]:
        return dict(self._tools)

    def get_definitions(self) -> list[ToolDefinition]:
        return [t.get_definition() for t in self._tools.values()]

    async def execute(self, tool_name: str, input_data: str, **kwargs: Any) -> ToolResult:
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
        try:
            return await asyncio.wait_for(
                tool.execute(input_data, **kwargs),
                timeout=tool.timeout,
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Tool {tool_name} timed out after {tool.timeout}s")

    async def execute_pipeline(
        self,
        tool_names: list[str],
        initial_input: str,
    ) -> str:
        current = initial_input
        for name in tool_names:
            result = await self.execute(name, current)
            if not result.success:
                return f"Pipeline failed at tool '{name}': {result.error}"
            current = result.output
        return current


_default_pipeline = ToolPipeline()
_default_pipeline.register(SearchTool())
_default_pipeline.register(CalculatorTool())
_default_pipeline.register(DatabaseTool())
_default_pipeline.register(HTTPTool())
