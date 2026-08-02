import pytest

from app.orchestration.tools import (
    BaseTool,
    ToolPipeline,
    SearchTool,
    CalculatorTool,
    DatabaseTool,
    HTTPTool,
    ToolResult,
)


class TestTools:
    async def test_search_tool(self):
        tool = SearchTool()
        assert tool.name == "search"
        assert "Search" in tool.description

    async def test_calculator_tool_addition(self):
        tool = CalculatorTool()
        result = await tool.execute("2 + 2")
        assert result.success is True
        assert result.output == "4"

    async def test_calculator_tool_multiplication(self):
        tool = CalculatorTool()
        result = await tool.execute("3 * 4")
        assert result.success is True
        assert result.output == "12"

    async def test_calculator_tool_invalid(self):
        tool = CalculatorTool()
        result = await tool.execute("invalid expression {{{")
        assert result.success is False

    async def test_database_tool(self):
        tool = DatabaseTool()
        result = await tool.execute("SELECT * FROM users")
        assert result.success is True
        assert "Database" in result.output

    async def test_http_tool_invalid_url(self):
        tool = HTTPTool()
        result = await tool.execute("not-a-url")
        assert result.success is False


class TestToolPipeline:
    def setup_method(self):
        self.pipeline = ToolPipeline()
        self.pipeline.register(CalculatorTool())
        self.pipeline.register(SearchTool())

    def test_register_and_get(self):
        assert self.pipeline.get("calculator") is not None
        assert self.pipeline.get("search") is not None

    def test_get_unknown_tool(self):
        assert self.pipeline.get("nonexistent") is None

    async def test_execute_tool(self):
        result = await self.pipeline.execute("calculator", "10 * 10")
        assert result.success is True
        assert result.output == "100"

    async def test_execute_unknown_tool(self):
        result = await self.pipeline.execute("unknown", "input")
        assert result.success is False
        assert "Unknown" in result.error

    async def test_execute_pipeline(self):
        result = await self.pipeline.execute_pipeline(["calculator", "search"], "2 + 2")
        assert result is not None

    async def test_pipeline_failure_propagates(self):
        result = await self.pipeline.execute_pipeline(["unknown"], "input")
        assert "failed" in result.lower()

    def test_get_all_tools(self):
        all_tools = self.pipeline.get_all()
        assert "calculator" in all_tools
        assert "search" in all_tools

    def test_get_definitions(self):
        defs = self.pipeline.get_definitions()
        assert len(defs) >= 2
        names = [d.name for d in defs]
        assert "calculator" in names
        assert "search" in names

    async def test_custom_tool_registration(self):
        class CustomTool(BaseTool):
            name = "custom"
            description = "Custom test tool"
            async def execute(self, input_data, **kwargs):
                return ToolResult(output=f"processed: {input_data}")

        self.pipeline.register(CustomTool())
        assert self.pipeline.get("custom") is not None
        result = await self.pipeline.execute("custom", "test")
        assert result.output == "processed: test"

    def test_tool_result_str_success(self):
        result = ToolResult(success=True, output="done")
        assert str(result) == "done"

    def test_tool_result_str_error(self):
        result = ToolResult(success=False, error="failed")
        assert "Error" in str(result)
